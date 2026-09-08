"""Structure-aware chunking: split on heading hierarchy, then break oversized sections at
paragraph boundaries with ~15% overlap. Target 400-800 tokens. Tables flatten to markdown and
never split mid-row. See config.py for the exact thresholds.
"""

import re
from collections.abc import Iterable, Iterator
from pathlib import Path

import pypdfium2 as pdfium
import tiktoken
from pydantic import BaseModel

from config import ContentType, settings
from ingestion.parse import (
    HeadingCheckpoint,
    PageRecord,
    breadcrumb_before_page,
    extract_heading_checkpoints,
    find_heading_start,
)

_ENCODING = tiktoken.get_encoding("cl100k_base")

# CLAUDE.md's regex flag for Fusion expression syntax presence.
_EXPRESSION_TOKEN_RE = re.compile(r":GetValue\(|Point\(|iif\(|sin\(|\btime\b")

_PARAMETER_HEADER_RE = re.compile(r"\b(input|parameter|default|type|range)\b", re.IGNORECASE)
_UI_CUE_RE = re.compile(
    r"\b(right-click|contextual menu|the inspector|choose|click)\b", re.IGNORECASE
)
_NUMBERED_STEP_RE = re.compile(r"(?m)^\s*\d+\s+\S")
# Resolve's parameter docs are written as "Term: description" definition lists in flowing prose,
# not as PDF tables (e.g. "Color Temp: Adjusts color balance...") — this is the dominant shape
# for control/parameter documentation in this manual, not the table-based one _PARAMETER_HEADER_RE
# catches. Missing this was why parameter_reference was ~9 chunks out of ~6000 on the first pass.
_DEFINITION_TERM_RE = re.compile(r"(?<![\w.])([A-Z][\w][\w /()'-]{1,45}):\s(?=[A-Z])")


class Chunk(BaseModel):
    chunk_id: str
    breadcrumb: str
    page_start: int
    page_end: int
    content_type: ContentType
    has_expression_syntax: bool
    text: str


class _Segment(BaseModel):
    breadcrumb: str
    page_start: int
    page_end: int
    text: str


def estimate_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def has_expression_syntax(text: str) -> bool:
    return bool(_EXPRESSION_TOKEN_RE.search(text))


def _classify_content_type(text: str, is_table: bool) -> ContentType:
    if is_table:
        header_line = text.split("\n", 1)[0]
        if _PARAMETER_HEADER_RE.search(header_line):
            return "parameter_reference"
        return "table"
    numbered_steps = len(_NUMBERED_STEP_RE.findall(text))
    ui_cue_matches = len(_UI_CUE_RE.findall(text))
    definition_terms = len(_DEFINITION_TERM_RE.findall(text))
    if has_expression_syntax(text) and text.count("(") >= 3:
        return "code_example"
    if definition_terms >= 2:
        return "parameter_reference"
    if numbered_steps >= 2 or ui_cue_matches >= 2:
        return "ui_description"
    return "prose"


def _split_page_by_inpage_headings(
    page: PageRecord, inpage_checkpoints: list[HeadingCheckpoint], page_start_breadcrumb: str
) -> list[tuple[str, str]]:
    """Returns [(breadcrumb, text_piece), ...] for one page. Headings that start on this page
    split it into pieces; text before the first found heading gets `page_start_breadcrumb` — the
    section carried over from the previous page, NOT this page's own last heading (a page can
    carry several headings, e.g. p.1630 has four; text before the first of them belongs to
    whatever section was active before any of them started)."""
    if not inpage_checkpoints:
        return [(page_start_breadcrumb, page.raw_text)]

    positions: list[tuple[int, str]] = []
    search_from = 0
    for cp in inpage_checkpoints:
        match = find_heading_start(page.raw_text, cp.title, search_from)
        if match is None:
            continue
        start, end = match
        positions.append((start, cp.breadcrumb))
        search_from = end

    if not positions:
        return [(page_start_breadcrumb, page.raw_text)]

    pieces: list[tuple[str, str]] = []
    if positions[0][0] > 0:
        pieces.append((page_start_breadcrumb, page.raw_text[: positions[0][0]]))
    for i, (start, breadcrumb) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(page.raw_text)
        piece = page.raw_text[start:end]
        if piece.strip():
            pieces.append((breadcrumb, piece))
    return pieces


def _merge_into_sections(pages: Iterable[PageRecord], pdf_path: Path) -> list[_Segment]:
    pdf = pdfium.PdfDocument(str(pdf_path))
    checkpoints = extract_heading_checkpoints(pdf)
    checkpoints_by_page: dict[int, list[HeadingCheckpoint]] = {}
    for cp in checkpoints:
        checkpoints_by_page.setdefault(cp.page, []).append(cp)
    all_pages = [cp.page for cp in checkpoints]
    all_breadcrumbs = [cp.breadcrumb for cp in checkpoints]

    sections: list[_Segment] = []
    current: _Segment | None = None

    for page in pages:
        page_start_breadcrumb = breadcrumb_before_page(all_pages, all_breadcrumbs, page.page_number)
        pieces = _split_page_by_inpage_headings(
            page, checkpoints_by_page.get(page.page_number, []), page_start_breadcrumb
        )
        for breadcrumb, text in pieces:
            if not text.strip():
                continue
            if current is not None and current.breadcrumb == breadcrumb:
                current.text = current.text.rstrip() + "\n\n" + text.strip()
                current.page_end = page.page_number
            else:
                if current is not None:
                    sections.append(current)
                current = _Segment(
                    breadcrumb=breadcrumb,
                    page_start=page.page_number,
                    page_end=page.page_number,
                    text=text.strip(),
                )
    if current is not None:
        sections.append(current)
    return _merge_tiny_sections(sections)


_MIN_SECTION_TOKENS = 15


def _merge_tiny_sections(sections: list[_Segment]) -> list[_Segment]:
    """Fold near-empty sections into a neighbor rather than emitting them as their own chunk.
    These show up for a few different reasons (an unstripped Contents-listing remnant, a bare
    heading whose real content is separated by an image the text extraction can't see through,
    two headings with almost nothing between them) — regardless of cause, a 1-6 word chunk has
    no retrieval value on its own and just adds noise to the index. Merges forward (into the
    next section) since a tiny fragment is usually a heading stub leading into real content;
    the last section in the document merges backward instead, having no "next" to join."""
    merged: list[_Segment] = []
    for section in sections:
        if merged and estimate_tokens(merged[-1].text) < _MIN_SECTION_TOKENS:
            tiny = merged.pop()
            section.text = tiny.text.rstrip() + "\n\n" + section.text
            section.page_start = min(tiny.page_start, section.page_start)
        merged.append(section)

    if len(merged) >= 2 and estimate_tokens(merged[-1].text) < _MIN_SECTION_TOKENS:
        tiny = merged.pop()
        merged[-1].text = merged[-1].text.rstrip() + "\n\n" + tiny.text
        merged[-1].page_end = max(merged[-1].page_end, tiny.page_end)

    return merged


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_long_paragraph(paragraph: str, max_tokens: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for sentence in sentences:
        sentence_tokens = estimate_tokens(sentence)
        if buf and buf_tokens + sentence_tokens > max_tokens:
            pieces.append(" ".join(buf))
            buf, buf_tokens = [], 0
        buf.append(sentence)
        buf_tokens += sentence_tokens
    if buf:
        pieces.append(" ".join(buf))
    return pieces


def _pack_paragraphs_with_overlap(paragraphs: list[str]) -> list[str]:
    target = settings.chunk_target_tokens
    max_tokens = settings.chunk_max_tokens
    overlap_tokens = int(target * settings.chunk_overlap_ratio)

    expanded: list[str] = []
    for p in paragraphs:
        if estimate_tokens(p) > max_tokens:
            expanded.extend(_split_long_paragraph(p, max_tokens))
        else:
            expanded.append(p)

    chunks: list[str] = []
    i = 0
    n = len(expanded)
    while i < n:
        buf: list[str] = []
        buf_tokens = 0
        j = i
        while j < n:
            p_tokens = estimate_tokens(expanded[j])
            if buf and buf_tokens + p_tokens > max_tokens:
                break
            buf.append(expanded[j])
            buf_tokens += p_tokens
            j += 1
            if buf_tokens >= target:
                break
        chunks.append("\n\n".join(buf))

        if j >= n:
            break
        # Walk back from j so the next chunk overlaps by ~chunk_overlap_ratio of target tokens.
        back_tokens = 0
        k = j
        while k > i and back_tokens < overlap_tokens:
            k -= 1
            back_tokens += estimate_tokens(expanded[k])
        i = max(k, i + 1)  # always make forward progress
    return chunks


def chunk_pages(
    pages: Iterator[PageRecord], pdf_path: Path = settings.manual_pdf_path
) -> Iterator[Chunk]:
    pages_list = list(pages)
    sections = _merge_into_sections(pages_list, pdf_path)
    tables_seen: set[tuple[int, str]] = set()
    seq = 0

    for section in sections:
        paragraphs = _split_paragraphs(section.text)
        if not paragraphs:
            continue
        packed = _pack_paragraphs_with_overlap(paragraphs)
        for text in packed:
            seq += 1
            yield Chunk(
                chunk_id=f"chunk-{section.page_start:05d}-{seq:04d}",
                breadcrumb=section.breadcrumb,
                page_start=section.page_start,
                page_end=section.page_end,
                content_type=_classify_content_type(text, is_table=False),
                has_expression_syntax=has_expression_syntax(text),
                text=text,
            )

    for page in pages_list:
        for table in page.tables:
            key = (page.page_number, table.markdown)
            if key in tables_seen:
                continue
            tables_seen.add(key)
            seq += 1
            yield Chunk(
                chunk_id=f"chunk-{page.page_number:05d}-{seq:04d}",
                breadcrumb=page.breadcrumb,
                page_start=page.page_number,
                page_end=page.page_number,
                content_type=_classify_content_type(table.markdown, is_table=True),
                has_expression_syntax=has_expression_syntax(table.markdown),
                text=table.markdown,
            )


def write_chunks_jsonl(chunks: Iterator[Chunk], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for chunk in chunks:
            f.write(chunk.model_dump_json() + "\n")


def read_chunks_jsonl(path: Path) -> list[Chunk]:
    chunks = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(Chunk.model_validate_json(line))
    return chunks
