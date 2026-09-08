---
name: fusion-expressions
description: Use this whenever the user wants to animate, move, bounce, spring, ease, squash-and-stretch, wiggle, or otherwise procedurally drive a parameter inside DaVinci Resolve's Fusion page (or standalone Fusion Studio) — even if they never say "expression," "Fusion," or "SimpleExpression" explicitly. Phrases like "make this text bounce," "add some spring to this transform," "animate opacity with a sine wave," "link these two parameters," or "write a Fusion expression for X" should all trigger this. Covers SimpleExpression syntax, the Modifiers system, and FusionScript, plus verified node/parameter reference syntax and composed animation math (springs, bounces, ease curves, squash-and-stretch). Ground every node/input name you use against `references/node-inputs.md` or live retrieval — never guess Fusion syntax from general training knowledge.
---

# Fusion Expressions

Fusion (DaVinci Resolve's node-based compositor, also shipped standalone as Fusion Studio) has
three distinct mechanisms for procedural/custom behavior. Picking the right one — and getting the
syntax exactly right — is the whole point of this skill.

**Source of truth:** everything under `references/` that carries a page citation (e.g. `[Ch.73,
p.1635]`) is copied or paraphrased directly from the *DaVinci Resolve 21 Reference Manual*,
Chapter 73, "Using Modifiers, Expressions, and Custom Controls" (pp. 1629–1641). Content without
a citation is composed animation math — sound, but not manual-verified syntax. Never present
composed math as if it were a documented Fusion feature; the two are labeled separately for a
reason (see "Answer tiering" in the project's `CLAUDE.md` — GROUNDED vs SYNTHESIZED vs
UNVERIFIED).

## The three mechanisms

1. **SimpleExpression** — a single inline formula on one parameter. Type `=` into any numeric,
   point, or text field and press Return; a formula field with a yellow indicator appears below
   the parameter, pre-filled with its current value. Fastest, most common, what most "make X
   bounce" requests need. `[Ch.73, p.1634]`

2. **Modifiers** (Expression, Calculation, Publish, Anim Curves, etc.) — right-click a parameter
   name → **Modify With**. These live in the Inspector's Modifiers tab, get more room than a
   SimpleExpression field, and can be chained/branched like nodes. Reach for these when a
   SimpleExpression field feels cramped, or when you need to *publish* a value so multiple
   parameters can connect to it. `[Ch.73, pp.1630–1633]`

3. **FusionScript** (Lua or Python) — full scripting: rearranging nodes, batch operations,
   external integrations, Fuses, ViewShaders. Overkill for a single animated parameter; reach for
   it only when the user is asking to automate the *comp itself*, not animate one value.
   `[Ch.73, pp.1640–1641]`

Default to SimpleExpression unless the request clearly needs one of the other two.

## SimpleExpression grammar (verified)

The expression language is Lua. Confirmed primitives, all `[Ch.73, pp.1634–1636]`:

| Syntax | Meaning |
|---|---|
| `time` | current frame/time value |
| `sin(x)`, `cos(x)`, `sqrt(x)`, `atan2(y, x)`, `pi` | standard math functions |
| `^` | power operator (e.g. `x^2`), not `**` |
| `..` | string concatenation (Lua-style), not `+` |
| `iif(condition, a, b)` | conditional — shorthand if-then-else |
| `Point(x, y)` | constructs a Point value; a parameter expecting a Point (not a Number) must return one |
| `Text("...")` | constructs a Text value for text-type parameters |
| `NodeName.ParameterName` | reference another node's parameter, e.g. `Merge1.Blend` |
| `self` | the current node — `self.Input` is equivalent to omitting the node name on `Input` |
| `.X`, `.Y` | member access on a Point (e.g. `Text1.Center.X`) |
| `Input.Metadata.<Key>` | read image metadata (e.g. `ColorSpaceID`) |
| `os.date("%b %d, %Y")` | Lua os library is available for things like timestamps |

**Type matters.** A field that expects a Number and gets a Point (or vice versa) will error or
misbehave. Look at what the target parameter's control type is (Number field vs. point-picker
onscreen control vs. text field) before choosing what the expression returns.

**Worked examples from the manual**, `[Ch.73, p.1635]`:

```lua
sin(time/20)/2+.5                              -- sine wave normalized to 0..1
iif(Merge1.Blend == 0, 0, 1)                    -- 0 if Blend is 0, else 1
iif(Input.Metadata.ColorSpaceID == "sRGB", 0, 1) -- branch on image metadata
Point(Text1.Center.X, Text1.Center.Y - .1)      -- Point offset below another node's Center
Text1.Center - Point(0, .1)                     -- equivalent, more compact
Text("Colorspace: " .. (Merge1.Background.Metadata.ColorSpaceID))
```

A more involved example driving a DirectionalBlur's Length/Angle from its Center control,
`[Ch.73, p.1638]` — note the reference frame is `self.Input` for the incoming image's dimensions:

```lua
-- Length:
sqrt(((Center.X-.5)*(self.Input.XScale))^2 +
     ((Center.Y-.5)*(self.Input.YScale)*(self.Input.Height/self.Input.Width))^2)
-- Angle:
atan2(.5-Center.Y, .5-Center.X) * 180 / pi
```

**Pick whipping**: with a SimpleExpression field open, drag its `+` button onto another
control to link them — equivalent to hand-writing a `NodeName.Parameter` reference, but
editable afterward unlike a plain Connect To link. `[Ch.73, p.1636]`

## Verifying node and parameter names

The table above is everything this skill currently has manual-verified. It does **not** cover
per-node input names (e.g. the exact input list for Transform, Merge, Text+, BSpline...) — those
live in the "Fusion Page Effects" chapters of the manual, organized by node category (Transform
Nodes, Composite Nodes, Filter Nodes, etc.), not yet extracted into this skill.

Before naming a specific node input in an answer:

1. Check `references/node-inputs.md` — it only contains names actually confirmed against the
   manual, and says so.
2. If it's not there, retrieve it from the project's RAG index over the manual (once that's
   built) rather than recalling it from general training knowledge.
3. If neither is available, say so explicitly and mark the answer's node/input names as
   unverified — do not present a guessed input name as fact. This project exists specifically
   to prevent that failure mode; see `CLAUDE.md` at the repo root.

Common, extremely stable names that are safe to use even before full verification: `Center`,
`Angle`, `Size` on Transform-family nodes; `Blend` on Merge; `Red`/`Green`/`Blue`/`Alpha` channel
switches. These are stable across many Resolve versions and appear directly in the verified
examples above — but a full audit is still pending milestone 1 of the RAG project.

## Composing animation math

For spring physics, bounce, ease curves, and squash-and-stretch — math the manual documents
primitives for but not recipes — see `references/math-patterns.md`. Translate the formulas there
into the Lua syntax verified above (`^` not `**`, `..` not `+` for strings, etc.).

## Common failure modes

- **Wrong return type.** Writing a Number-only formula (e.g. plain arithmetic) into a Point
  field, or vice versa. Wrap in `Point(x, y)` when the target expects one.
- **Forgetting evaluation order.** `NodeName.Parameter` reads that node's *current evaluated*
  value for the frame being processed — referencing a node that hasn't been positioned/keyframed
  yet, or that sits downstream in the flow, can silently produce stale or wrong values.
- **`+` for string concatenation.** This is Lua — use `..`. A stray `+` on two Text values will
  error or coerce unexpectedly.
- **Degrees vs. radians.** `sin`/`cos`/`atan2` are radian-based; multiply/divide by `pi/180` when
  the surrounding UI (like an Angle field) is in degrees, as the manual's own Angle example does:
  `atan2(...) * 180 / pi`.
- **Assuming an input name instead of checking it.** See "Verifying node and parameter names"
  above — this is the single highest-value thing this skill exists to prevent.
