# Composed animation math

This is the layer the manual deliberately does **not** provide — it documents `time`, `sin`,
`iif`, `Point()`, and the rest as primitives, and leaves composing "make it bounce" on top of
them to the animator. Everything here is standard procedural-animation math, translated into the
Lua/SimpleExpression syntax verified in `SKILL.md` (`^` for power, `..` for string concat, `iif`
for branching, `sin`/`cos`/`atan2`/`sqrt`/`pi` confirmed available).

**Caveat on `exp` and `abs`**: the manual excerpt pulled so far confirms `sin`, `cos`, `sqrt`,
`atan2`, and `pi` as bare (non-namespaced) functions — consistent with Lua's `math` library being
exposed without the `math.` prefix. `exp(x)` and `abs(x)` almost certainly work the same way, but
aren't directly confirmed yet. If `exp` errors in practice, substitute `2.718281828^x`. If `abs`
errors, substitute `sqrt(x^2)`.

All patterns below assume `time` is in frames (as the manual's own `sin(time/20)/2+.5` example
implies) and a `StartFrame` you set to whatever frame the animation should begin — subtract it so
the curve starts at zero rather than wherever the timeline happens to be.

## Damped spring

Settles toward `Target` with oscillation that decays over time — the general-purpose "give this
motion some life" pattern, good for camera settle, UI pop-ins, follow-through on a stopped motion.

```lua
-- Parameters you choose per use: Target, Amplitude, Decay, Frequency, StartFrame
Target + Amplitude * exp(-Decay * (time - StartFrame)) * cos(Frequency * (time - StartFrame))
```

- `Decay` controls how fast it settles (higher = snappier, less oscillation visible).
- `Frequency` controls oscillation speed (higher = more wobbles before settling).
- Before `StartFrame`, this still evaluates (cos(0)=1, exp(0)=1 → returns `Target + Amplitude`) —
  wrap in `iif(time < StartFrame, Target, ...)` if you need it flat before the trigger frame.

**Critically damped** (settles with no overshoot — use when "spring" should read as "smooth
arrival," not "bouncy"): drop the `cos` term and decay linearly instead —

```lua
Target + Amplitude * (1 + Decay*(time - StartFrame)) * exp(-Decay * (time - StartFrame))
```

## Bounce

A decaying-amplitude periodic curve — good for a dropped object settling, or a UI element that
bounces to rest. This is a continuous approximation (real gravity-driven bounce is piecewise
parabolic per bounce); it reads correctly for motion graphics and is far simpler to tune.

```lua
-- BaseHeight: resting position. Amplitude: initial bounce height. Decay, Frequency as above.
BaseHeight + Amplitude * abs(cos(Frequency * (time - StartFrame))) * exp(-Decay * (time - StartFrame))
```

`abs(cos(...))` produces the repeated touch-down shape (each period, the curve returns to 0 and
reflects rather than going negative) — this is what reads as "bouncing" rather than "oscillating."

## Ease curves (normalized 0→1 over a duration)

Use these to drive a parameter smoothly between two values over `Duration` frames starting at
`StartFrame`, instead of relying on keyframe interpolation. First compute normalized time, then
shape it, then lerp:

```lua
-- t: normalized progress, clamped to [0, 1]
-- (SimpleExpressions don't have a built-in clamp; iif-chain it)
iif(time < StartFrame, 0, iif(time > StartFrame + Duration, 1, (time - StartFrame) / Duration))
```

Assume the expression above is assigned to a helper concept `t` — in practice, inline it or
build it via a Publish/Calculation modifier so it can be reused across several parameters instead
of repeating the `iif` chain everywhere.

**easeInOutCubic** — smooth start and end, standard default for most motion:
```lua
iif(t < 0.5, 4*t^3, 1 - ((-2*t + 2)^3) / 2)
```

**easeOutBack** — overshoots past the target then settles, good for a "pop" or attention-getting
entrance:
```lua
-- Overshoot: how far past 1.0 it swings before settling, e.g. 1.70158 is the conventional default
1 + Overshoot * (t - 1)^3 + (t - 1)^2 * (Overshoot + 1) * (t - 1)
```

Then lerp into the actual parameter range: `StartValue + (EndValue - StartValue) * <eased t>`.

## Squash-and-stretch (volume preservation)

Classic animation principle: as an object stretches along one axis, it should compress on the
others so it reads as having mass rather than rubber-banding arbitrarily. For a Transform-family
node with separate X/Y (and optionally Z) scale inputs, drive the secondary axes off whichever
axis is doing the "acting" (e.g. `Size` or a Y-scale you're already animating with a spring or
bounce above):

```lua
-- 2D, preserving area: if YScale is your driven/animated value
XScale = 1 / sqrt(YScale)
```

```lua
-- 3D, preserving volume: if YScale is driven, X and Z compensate equally
XScale = 1 / sqrt(YScale)
ZScale = 1 / sqrt(YScale)
```

For an impact-driven squash (object flattens on contact, e.g. a ball hitting the ground at the
bottom of a bounce), drive `YScale` from the bounce pattern above scaled into a 0..1-ish squash
factor, then feed that same value into the volume-preservation formula — the squash and the
stretch stay physically consistent because they're driven by the same underlying curve rather
than animated independently by hand.
