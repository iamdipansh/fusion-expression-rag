# Node / parameter reference — verification status

**Status: partial.** This file only lists names actually confirmed against the *DaVinci Resolve
21 Reference Manual*. It is not a general Fusion node reference — do not extend it from memory.
Extend it only by pulling exact input names from the manual (ideally once the project's RAG index
over the manual exists, milestone 1 of the parent project).

## Confirmed syntax elements

Source: Chapter 73, "Using Modifiers, Expressions, and Custom Controls," pp. 1629–1641.

| Node.Parameter seen in manual examples | Context |
|---|---|
| `Merge1.Blend` | Merge node's Blend parameter, used in an `iif()` example, p.1635 |
| `Merge1.Background.Metadata.ColorSpaceID` | nested member access through a node's input image's metadata, p.1635 |
| `Text1.Center` | Text+ node's Center point parameter, p.1635 |
| `Input.Metadata.ColorSpaceID` | `Input` on its own means the current node's own Input, equivalent to `self.Input`, p.1635 |
| `self.Input.XScale`, `self.Input.YScale`, `self.Input.Height`, `self.Input.Width` | image-level members readable off an Input, p.1638 |
| `Center.X`, `Center.Y` | Point member access pattern — applies generally to any Point-type parameter, p.1638 |

## Transform [XF] — fully verified

Source: "Fusion Page Effects > Transform Nodes > Transform [XF]," pp. 2929–2933 of the Resolve 21
manual (extracted via milestone 1's ingestion pipeline, cross-checked in milestone 2's gold eval
set — see `server/eval/gold_set.jsonl` ids 1-7). This is the node the fusion-expressions math
patterns most often target, so it's worth having fully confirmed rather than "likely correct":

| Input | Notes |
|---|---|
| `Center` | Point (X, Y). Default `0.5, 0.5` (image center). Value shown is the normalized position multiplied by the Reference Size. |
| `Pivot` | Point (X, Y). Axis of rotation and scaling. Default `0.5, 0.5`. |
| `Size` | Number. Range 0–5 in the slider, any value > 0 valid. Scales both axes equally when `Use Size and Aspect` is on; X/Y become independent when it's off. |
| `Aspect` | Number. Only active when `Use Size and Aspect` is on. >1.0 stretches X, 0.0–1.0 stretches Y. |
| `Angle` | Number, degrees. Increasing rotates **counterclockwise**. |
| `Edges` | Menu: `Canvas`, `Wrap`, `Duplicate`, `Mirror`. |
| `Input` | Orange, primary 2D image. |
| `Effect Mask` | Blue, optional mask limiting the transformed area. |

Not yet pulled into this table but present in the same source pages: Flip Horizontally/Vertically,
Filter Method (Box/Linear/Quadratic/Cubic/Catmull-Rom/Gaussian/Mitchell/Lanczos/Sinc/Bessel),
Window Method (Sinc/Bessel only), Invert Transform, Flatten Transform, Reference Size/Width/Height,
Auto Resolution.

## General pattern (verified, not node-specific)

`NodeName.ParameterName` — dot access into any other node's parameter by the node's name as it
appears in the Node Editor (e.g. `Transform1`, `Merge1`). Omitting `NodeName.` and just writing
`Input` or `Output` refers to the current node's own Input/Output. This pattern itself is
confirmed; the specific parameter names available per node type are what still need auditing.

## Known gap

The manual devotes an entire "Fusion Page Effects" section to per-node-category parameter
tables (3D Nodes, Blur Nodes, Color Nodes, Composite Nodes, Filter Nodes, Generator Nodes, Layer
Nodes, Mask Nodes, Position Nodes, Shape Nodes, Tracking Nodes, Transform Nodes, Warp Nodes, and
more — see the manual's top-level bookmarks). None of that has been extracted into this file yet.

When a user's request needs an exact input name beyond what's listed above (e.g. "what's the
exact input name for a Transform node's anti-aliasing setting"), the correct behavior is:

1. Retrieve it from the manual (via the RAG index once built, or by searching the PDF directly
   if working in this repo pre-RAG).
2. If that's not possible in the moment, tell the user the name is unverified rather than
   stating it as fact.

Commonly-recalled names like `Size`, `Angle`, `Pivot`, `Aspect` on Transform-family nodes, or
`Red`/`Green`/`Blue`/`Alpha` on channel-related nodes, are very likely correct (they're stable
across Resolve versions and match Fusion's long-standing UI labels) but are still **unverified
by this file** — flag them as such if precision matters for the user's use case.
