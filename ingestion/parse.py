"""Milestone 1: PDF -> one JSONL record per page.

pypdfium2 for text + layout, pdfplumber for tables. Pull the embedded bookmark tree for the
chapter/section hierarchy — confirmed on the DaVinci Resolve 21 manual to go down to level-3
subsections with per-page anchors (e.g. "Using SimpleExpressions" -> page 1634), which is why
it's treated as the primary source of chunk breadcrumbs rather than a font-size heuristic.
No OCR. Parse once, never re-parse. Never use PyMuPDF (AGPL, this project is publicly hosted).
"""

import re
from bisect import bisect_left, bisect_right
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
from pydantic import BaseModel

_WHITESPACE_RE = re.compile(r"[ \t\xa0]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_ANY_WHITESPACE_RE = re.compile(r"\s+")
# InDesign's discretionary/soft hyphen glyph resolves to U+FFFE through this PDF's ToUnicode
# CMap instead of a real hyphen or nothing (e.g. "right-click" extracts as "right￾click").
_BROKEN_HYPHEN_RE = re.compile("￾")
# Dot-leaders in mini per-chapter "Contents" listings have no valid glyph mapping and decode as
# a run of U+FFFD replacement characters (e.g. "Preferences Overview��...� 1643").
_REPLACEMENT_CHAR_RE = re.compile("�+")
# Running page footer, e.g. "Fusion Fundamentals | Chapter 73 Using Modifiers, Expressions, and
# Custom Controls 1632\nFUSION" — repeated on every page, pure layout furniture, no content value.
_FOOTER_RE = re.compile(r"\n\s*\n?[^\n]*\|\s*Chapter\s+\d+\s.*\s\d+\s*\n[A-Z][A-Z ]*$")
# Bare "Chapter 73" label preceding the real chapter title on a chapter's opening page — the
# title itself is kept (it's a real bookmark/heading), this is just the redundant number stub.
_CHAPTER_STUB_RE = re.compile(r"^Chapter\s+\d+\s*\n", re.MULTILINE)
# Mini per-chapter/section "Contents" listing (heading name + page number per line, dot-leaders
# already stripped above). Pure navigation furniture that duplicates the bookmark tree — and
# worse, a heading's own name reappearing here (pointing at wherever it *actually* starts) can
# fool the bounded-search bookmark resolver below into anchoring the heading to this listing
# instead of its real content. Strip before that resolution runs. Part-opener pages use an
# all-caps "CONTENTS" variant with a leading chapter number per line instead of the per-chapter
# "Contents" — both end each line in a trailing page number, so one pattern covers both.
_CONTENTS_BLOCK_RE = re.compile(r"\n(?:Contents|CONTENTS)\n(?:[^\n]+ \d{1,5}\n)+")


class TableRecord(BaseModel):
    markdown: str
    caption: str | None = None


class PageRecord(BaseModel):
    page_number: int
    breadcrumb: str
    raw_text: str
    heading_spans: list[str]
    tables: list[TableRecord]
    figure_captions: list[str]


@dataclass
class HeadingCheckpoint:
    page: int
    level: int
    title: str
    breadcrumb: str


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _BROKEN_HYPHEN_RE.sub("-", text)
    text = _REPLACEMENT_CHAR_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _CONTENTS_BLOCK_RE.sub("\n", text)
    text = _FOOTER_RE.sub("", text)
    text = _CHAPTER_STUB_RE.sub("", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def find_normalized(haystack: str, needle: str, start: int = 0) -> tuple[int, int] | None:
    """Whitespace-insensitive substring search. Headings sometimes wrap across lines in the
    extracted text (a bookmark title becomes "Using Modifiers, \\nExpressions, and \\nCustom
    Controls"), so a literal search for the bookmark's title as one line would miss it. Returns
    (start, end) as indices into the *original* haystack, or None. `start` is an original-text
    index to resume searching from."""
    norm_chars: list[str] = []
    mapping: list[int] = []
    for i, ch in enumerate(haystack):
        if ch.isspace():
            if norm_chars and norm_chars[-1] == " ":
                continue
            norm_chars.append(" ")
        else:
            norm_chars.append(ch)
        mapping.append(i)
    norm_haystack = "".join(norm_chars)
    norm_needle = _ANY_WHITESPACE_RE.sub(" ", needle).strip()
    if not norm_needle:
        return None

    norm_start = 0
    for ni, oi in enumerate(mapping):
        if oi >= start:
            norm_start = ni
            break
    else:
        norm_start = len(mapping)

    idx = norm_haystack.find(norm_needle, norm_start)
    if idx == -1:
        return None
    end_norm = idx + len(norm_needle) - 1
    return mapping[idx], mapping[end_norm] + 1


def find_heading_start(haystack: str, title: str, start: int = 0) -> tuple[int, int] | None:
    """Like find_normalized, but only accepts a match that begins its own line. A section's
    title can legitimately reappear in the very next sentence describing it (e.g. "Image
    Scaling\\nThe Image Scaling panel contains settings...", where "Image Scaling" the heading
    is immediately followed by a sentence that happens to repeat the same phrase) — without this
    constraint, the search for a *second*, distinct heading of the same name on one page would
    latch onto that incidental mid-sentence mention instead of the real next heading."""
    pos = start
    while True:
        match = find_normalized(haystack, title, pos)
        if match is None:
            return None
        match_start, match_end = match
        preceding = haystack[:match_start].rstrip(" ")
        if match_start == 0 or preceding.endswith("\n"):
            return match_start, match_end
        pos = match_end


def extract_heading_checkpoints(pdf: pdfium.PdfDocument) -> list[HeadingCheckpoint]:
    """Walk the bookmark tree in document order, carrying a breadcrumb stack. About 1 in 8
    bookmarks in this manual has no PDF destination at all — mostly chapter/part-title entries
    (their first subsection has a destination; the title itself doesn't). Losing those means a
    chapter's opening page (title + intro text, before its first subsection) wrongly inherits
    the breadcrumb of whatever the *previous* chapter's last subsection was.

    Fix: for an unresolved bookmark, search for its title text (whitespace-insensitive, since
    titles sometimes wrap across lines) in the page window between its nearest resolved
    neighbors — bounded, so this stays cheap even though ~500 bookmarks need it.
    """
    stack: dict[int, str] = {}
    entries: list[tuple[int, str, str, int | None]] = []  # level, title, breadcrumb, page

    for bookmark in pdf.get_toc():
        title = bookmark.get_title().strip()
        level = bookmark.level

        stack = {lvl: t for lvl, t in stack.items() if lvl < level}
        stack[level] = title
        breadcrumb = " > ".join(stack[lvl] for lvl in sorted(stack))

        dest = bookmark.get_dest()
        page_index = dest.get_index() if dest is not None else None
        page = page_index + 1 if page_index is not None else None
        entries.append((level, title, breadcrumb, page))

    n_pages = len(pdf)
    resolved_pages: list[int | None] = [p for _, _, _, p in entries]
    page_text_cache: dict[int, str] = {}

    def page_text(page_number: int) -> str:
        if page_number not in page_text_cache:
            raw = pdf[page_number - 1].get_textpage().get_text_range()
            # Cleaned (not raw) so a heading's own name in a stripped Contents listing can't
            # be mistaken for its real content start (see _CONTENTS_BLOCK_RE above).
            page_text_cache[page_number] = _clean_text(raw)
        return page_text_cache[page_number]

    for idx, (_, title, _, page) in enumerate(entries):
        if page is not None:
            continue

        prev_page = 1
        for j in range(idx - 1, -1, -1):
            candidate_prev = resolved_pages[j]
            if candidate_prev is not None:
                prev_page = candidate_prev
                break

        next_page = n_pages
        for j in range(idx + 1, len(entries)):
            candidate_next = resolved_pages[j]
            if candidate_next is not None:
                next_page = candidate_next
                break

        for candidate in range(prev_page, next_page + 1):
            if find_heading_start(page_text(candidate), title) is not None:
                resolved_pages[idx] = candidate
                break

    checkpoints: list[HeadingCheckpoint] = []
    for i, (level, title, breadcrumb, _) in enumerate(entries):
        page = resolved_pages[i]
        if page is not None:
            checkpoints.append(
                HeadingCheckpoint(page=page, level=level, title=title, breadcrumb=breadcrumb)
            )
    checkpoints.sort(key=lambda c: c.page)
    return checkpoints


def _breadcrumb_lookup(checkpoints: list[HeadingCheckpoint]) -> tuple[list[int], list[str]]:
    pages = [c.page for c in checkpoints]
    breadcrumbs = [c.breadcrumb for c in checkpoints]
    return pages, breadcrumbs


def breadcrumb_for_page(pages: list[int], breadcrumbs: list[str], page_number: int) -> str:
    idx = bisect_right(pages, page_number) - 1
    if idx < 0:
        return "Front Matter"
    return breadcrumbs[idx]


def breadcrumb_before_page(pages: list[int], breadcrumbs: list[str], page_number: int) -> str:
    """Like breadcrumb_for_page, but strictly before this page — the section that was active
    coming *into* this page, before any of this page's own headings apply. Needed when a page
    itself has multiple headings and we want to attribute its leading text (before the first of
    them) to the section carried over from the previous page, not to the page's own last
    heading."""
    idx = bisect_left(pages, page_number) - 1
    if idx < 0:
        return "Front Matter"
    return breadcrumbs[idx]


def extract_bookmark_tree(pdf_path: Path) -> dict[int, str]:
    """Page number -> breadcrumb, forward-filled so every page (including ones with no heading
    of its own) inherits whatever section it falls inside."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    checkpoints = extract_heading_checkpoints(pdf)
    pages, breadcrumbs = _breadcrumb_lookup(checkpoints)
    return {
        page_number: breadcrumb_for_page(pages, breadcrumbs, page_number)
        for page_number in range(1, len(pdf) + 1)
    }


def _extract_tables_by_page(pdf_path: Path) -> dict[int, list[TableRecord]]:
    tables_by_page: dict[int, list[TableRecord]] = {}
    with pdfplumber.open(pdf_path) as plumber_pdf:
        for i, page in enumerate(plumber_pdf.pages):
            raw_tables = page.extract_tables()
            if not raw_tables:
                continue
            records = [
                TableRecord(markdown=_table_to_markdown(t))
                for t in raw_tables
                if t and _is_real_table(t)
            ]
            if records:
                tables_by_page[i + 1] = records
    return tables_by_page


def _is_real_table(table: list[list[str | None]]) -> bool:
    """pdfplumber's default grid detector fires on plain page layout (image borders, two-column
    captions) as often as on real tables — those come back almost entirely empty cells. Require
    enough actual content that this is worth treating as a table chunk rather than noise."""
    cells = [(cell or "").strip() for row in table for cell in row]
    non_empty = [c for c in cells if c]
    if len(non_empty) < 3:
        return False
    return len(non_empty) / len(cells) >= 0.4


def _table_to_markdown(table: list[list[str | None]]) -> str:
    rows = [[(cell or "").strip().replace("\n", " ") for cell in row] for row in table]
    header, *body = rows
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


def parse_pdf(pdf_path: Path) -> Iterator[PageRecord]:
    pdf = pdfium.PdfDocument(str(pdf_path))
    checkpoints = extract_heading_checkpoints(pdf)
    pages, breadcrumbs = _breadcrumb_lookup(checkpoints)
    checkpoints_by_page: dict[int, list[HeadingCheckpoint]] = {}
    for c in checkpoints:
        checkpoints_by_page.setdefault(c.page, []).append(c)

    tables_by_page = _extract_tables_by_page(pdf_path)

    for i in range(len(pdf)):
        page_number = i + 1
        raw_text = _clean_text(pdf[i].get_textpage().get_text_range())
        breadcrumb = breadcrumb_for_page(pages, breadcrumbs, page_number)
        heading_spans = [c.title for c in checkpoints_by_page.get(page_number, [])]

        yield PageRecord(
            page_number=page_number,
            breadcrumb=breadcrumb,
            raw_text=raw_text,
            heading_spans=heading_spans,
            tables=tables_by_page.get(page_number, []),
            figure_captions=[],  # not extracted in v1 — see server/README.md known limitations
        )


def write_pages_jsonl(pages: Iterator[PageRecord], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for page in pages:
            f.write(page.model_dump_json() + "\n")
