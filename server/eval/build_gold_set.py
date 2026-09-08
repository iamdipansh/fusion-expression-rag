"""Milestone 2: generates gold_set.jsonl. Every question here is grounded against real
chunk_ids from data/parsed/chunks.jsonl (produced by milestone 1's ingestion run against the
actual Resolve 21 manual) rather than hand-typed page numbers — `expected_breadcrumbs` and
`expected_pages` are derived from those chunks, not guessed. `out_of_scope` items intentionally
have no source_chunk_ids: they test the UNVERIFIED gate, so there is nothing to ground.

Re-run whenever chunks.jsonl changes (ingestion fix, manual re-parse) so page numbers stay
correct:
    python -m eval.build_gold_set
"""

from pathlib import Path

from config import settings
from eval.run_eval import GoldExample

CHUNKS_PATH = settings.chunks_path
OUT_PATH = Path(__file__).parent / "gold_set.jsonl"


def _load_chunks_by_id() -> dict[str, dict]:
    import json

    chunks = {}
    with CHUNKS_PATH.open() as f:
        for line in f:
            c = json.loads(line)
            chunks[c["chunk_id"]] = c
    return chunks


# Each item: (category, question, expected_tier, source_chunk_ids, answer)
# expected_breadcrumbs/expected_pages are derived from source_chunk_ids at build time.
RAW_ITEMS: list[tuple[str, str, str, list[str], str]] = [
    # ---------------- parameter_lookup ----------------
    (
        "parameter_lookup",
        "What are the exact names of the Transform node's two inputs?",
        "GROUNDED",
        ["chunk-02929-3609"],
        "Input (orange, the primary 2D image) and Effect Mask (blue, limits the transformed area).",
    ),
    (
        "parameter_lookup",
        "What is the default value of the Transform node's Center parameter?",
        "GROUNDED",
        ["chunk-02929-3609"],
        "0.5, 0.5 — the center of the image.",
    ),
    (
        "parameter_lookup",
        "What does the Transform node's Pivot parameter control, and what's its default?",
        "GROUNDED",
        ["chunk-02929-3609"],
        "Pivot X and Y position the axis of rotation and scaling; default is 0.5, 0.5 "
        "(image center).",
    ),
    (
        "parameter_lookup",
        "On the Transform node, what's the difference in behavior between Size when 'Use Size "
        "and Aspect' is on vs. off?",
        "GROUNDED",
        ["chunk-02929-3609"],
        "With 'Use Size and Aspect' on, Size scales the image equally on both axes (paired with a "
        "separate Aspect control). With it off, Size provides independent X and Y scale controls "
        "instead.",
    ),
    (
        "parameter_lookup",
        "In the Transform node, which rotation direction does increasing the Angle value produce?",
        "GROUNDED",
        ["chunk-02929-3611"],
        "Counterclockwise. Decreasing Angle rotates clockwise.",
    ),
    (
        "parameter_lookup",
        "What are the four options on the Transform node's Edges menu, and what does each do?",
        "GROUNDED",
        ["chunk-02929-3611"],
        "Canvas (reveals the current Canvas Color), Wrap (edges wrap to the opposite side), "
        "Duplicate (edge pixels are repeated outward), Mirror (edge pixels are mirrored).",
    ),
    (
        "parameter_lookup",
        "What does 'Flatten Transform' do on the Transform node?",
        "GROUNDED",
        ["chunk-02929-3611"],
        "It prevents the node from concatenating its transformation with the node at its output "
        "(it may still concatenate transforms from its input).",
    ),
    (
        "parameter_lookup",
        "On the Merge node, what does the 'Center X and Y' control under Foreground Sizing "
        "actually control, and what's its default?",
        "GROUNDED",
        ["chunk-02264-2987"],
        "The position of the foreground image in the composite; default 0.5, 0.5 centers it over "
        "the background.",
    ),
    (
        "parameter_lookup",
        "Which input on the Merge node determines the resolution of the output image?",
        "GROUNDED",
        ["chunk-02264-2986"],
        "The background input.",
    ),
    (
        "parameter_lookup",
        "On the Merge node, what value of the Size control (under Foreground Sizing) gives a "
        "pixel-for-pixel composite?",
        "GROUNDED",
        ["chunk-02264-2987"],
        "1.0 — a single foreground pixel matches a single background pixel.",
    ),
    (
        "parameter_lookup",
        "What are the six options on the Background node's Gradient Type menu?",
        "GROUNDED",
        ["chunk-02410-3120"],
        "Linear, Reflect, Square, Cross, Radial, and Angle.",
    ),
    (
        "parameter_lookup",
        "What are the three options on the Background node's gradient Repeat menu, and what "
        "does each do?",
        "GROUNDED",
        ["chunk-02410-3120"],
        "Once (offset stays continuous past the end color), Repeat (loops back to the start "
        "color), Ping-pong (repeats the pattern in reverse).",
    ),
    (
        "parameter_lookup",
        "What are the three Frequency Method options on the Camera Shake node, and how does "
        "Square Wave differ from Sine?",
        "GROUNDED",
        ["chunk-02909-3590"],
        "Sine, Rectified Sine, and Square Wave. Square Wave produces a much more mechanical-"
        "looking motion than Sine.",
    ),
    (
        "parameter_lookup",
        "What value range is permitted for the Camera Shake node's Deviation X and Y controls, "
        "and what does a value of 1.0 mean?",
        "GROUNDED",
        ["chunk-02909-3590"],
        "0.0 to 1.0. A value of 1.0 lets the shake generate positions anywhere within the image's "
        "boundaries.",
    ),
    (
        "parameter_lookup",
        "What are the four Type options on the Directional Blur node?",
        "GROUNDED",
        ["chunk-02167-2896"],
        "Linear, Radial, Centered, and Zoom.",
    ),
    (
        "parameter_lookup",
        "On the Directional Blur node, what happens if you set the Length control to a value "
        "below zero?",
        "GROUNDED",
        ["chunk-02167-2896"],
        "Blurs head in the opposite direction from the Angle control.",
    ),
    (
        "parameter_lookup",
        "What are the three Clipping Mode options on the Directional Blur node, and which is "
        "the default?",
        "GROUNDED",
        ["chunk-02167-2896"],
        "Frame (default — uses the full frame as the domain of definition), Domain (respects the "
        "upstream domain of definition), and None (no source-image clipping at all).",
    ),
    (
        "parameter_lookup",
        "On the sEllipse shape node, when is the Position parameter displayed, and what does it "
        "do together with Length?",
        "GROUNDED",
        ["chunk-02788-3476"],
        "Only when the Solid checkbox is disabled. Position sets the starting point of the "
        "outline; combined with Length (which controls how closed the outline is, 1.0 = fully "
        "closed), it positions the gap in the ellipse outline.",
    ),
    (
        "parameter_lookup",
        "What does the Shake modifier's Smoothness control do, and what happens at a value of "
        "zero?",
        "GROUNDED",
        ["chunk-03077-3731"],
        "It smooths the overall randomness of the shake — higher values look smoother. A value of "
        "zero produces completely random results with no smoothing.",
    ),
    (
        "parameter_lookup",
        "What noise algorithm does the Perturb modifier use to generate its random values?",
        "GROUNDED",
        ["chunk-03072-3727"],
        "Perlin noise.",
    ),
    # ---------------- node_lookup ----------------
    (
        "node_lookup",
        "Which Fusion node combines two images based on the foreground's Alpha channel?",
        "GROUNDED",
        ["chunk-02264-2985"],
        "The Merge node.",
    ),
    (
        "node_lookup",
        "Which Fusion node produces gradient or solid-color backgrounds?",
        "GROUNDED",
        ["chunk-02410-3119"],
        "The Background node.",
    ),
    (
        "node_lookup",
        "Which Fusion node simulates camera shake motion, and how is it different from the "
        "Shake modifier?",
        "GROUNDED",
        ["chunk-02909-3589"],
        "The Camera Shake node. It's not the same as the Shake Modifier, which generates "
        "random number values for parameters generally — Camera Shake is a dedicated "
        "transform-style node.",
    ),
    (
        "node_lookup",
        "Which node would you use to apply perspective distortion from Planar Tracker data onto "
        "a mask or image?",
        "GROUNDED",
        ["chunk-02921-3601"],
        "The Planar Transform node.",
    ),
    (
        "node_lookup",
        "Which Fusion node generates rectangular shapes, and what node do you need to actually "
        "view its output?",
        "GROUNDED",
        ["chunk-02806-3487"],
        "The sRectangle node. Like most shape nodes, its output must go through an sRender node "
        "to be viewed.",
    ),
    (
        "node_lookup",
        "Which node generates circular/elliptical shapes in Fusion?",
        "GROUNDED",
        ["chunk-02788-3475"],
        "The sEllipse node.",
    ),
    (
        "node_lookup",
        "What's the difference between the Resize node and the Scale node?",
        "GROUNDED",
        ["chunk-02923-3603", "chunk-02926-3606"],
        "Resize uses exact pixel dimensions to change an image's resolution; Scale is almost "
        "identical but uses relative dimensions instead of exact ones.",
    ),
    (
        "node_lookup",
        "Which modifier lets you link two non-animated parameters together without keyframing "
        "either one directly?",
        "GROUNDED",
        ["chunk-01632-2326"],
        "The Publish modifier — it publishes a parameter so others can link to it via the Connect "
        "To submenu.",
    ),
    (
        "node_lookup",
        "Which modifier creates an indirect link between two parameters using a mathematical "
        "expression?",
        "GROUNDED",
        ["chunk-01632-2326"],
        "The Calculation modifier.",
    ),
    (
        "node_lookup",
        "What are the node abbreviations for the Blur-category nodes in Fusion, and which one is "
        "for simulating an out-of-focus lens rather than a directional/motion blur?",
        "GROUNDED",
        ["chunk-02161-2888"],
        "Blur [Blur], Defocus [Dfo], Directional Blur [DrBl], Glow [Glo], Sharpen [Shrp], "
        "Soft Glow [SGlo], Unsharp Mask [USM], Vari Blur [VBL], Vector Motion Blur [VMB]. "
        "Defocus [Dfo] is the one for simulated out-of-focus blur.",
    ),
    (
        "node_lookup",
        "Which node lets you alternate between multiple input sources, selecting one output from "
        "several choices?",
        "GROUNDED",
        ["chunk-02655-3352"],
        "The Switch node.",
    ),
    (
        "node_lookup",
        "Which modifier is described as 'one of the most versatile modifiers in Fusion,' "
        "letting you control a numeric parameter from the color or luminosity of a pixel "
        "region in an image?",
        "GROUNDED",
        ["chunk-03074-3728"],
        "The Probe modifier.",
    ),
    (
        "node_lookup",
        "Besides the standalone Tracker node, is there a way to attach tracking directly to a "
        "single parameter without using a full Tracker node?",
        "GROUNDED",
        ["chunk-03078-3732"],
        "Yes — the Track modifier, applied via the Modify With contextual menu on the parameter.",
    ),
    (
        "node_lookup",
        "Which node type applies color-space conversions using the OCIO (OpenColorIO) system, "
        "and what are its two inputs?",
        "GROUNDED",
        ["chunk-02246-2970"],
        "OCIO Color Space [OCS]. Its two inputs are the main image input and an effect mask input "
        "to limit where the conversion is applied.",
    ),
    # ---------------- expression_syntax ----------------
    (
        "expression_syntax",
        "How do you open a SimpleExpression field on a parameter in the Inspector?",
        "GROUNDED",
        ["chunk-01634-2329"],
        "Type an equals sign (=) directly in the parameter's number field and press Return.",
    ),
    (
        "expression_syntax",
        "What does the SimpleExpression `sin(time/20)/2+.5` evaluate to?",
        "GROUNDED",
        ["chunk-01635-5726"],
        "A sine wave normalized to the range 0 to 1.",
    ),
    (
        "expression_syntax",
        "What does `iif(Merge1.Blend == 0, 0, 1)` do, and what is `iif` short for?",
        "GROUNDED",
        ["chunk-01635-5726"],
        "It's a shorthand if-then-else conditional: returns 0 if Merge1's Blend value is 0, "
        "otherwise returns 1.",
    ),
    (
        "expression_syntax",
        "In a SimpleExpression, what does writing just `Input` (with no node name) refer to?",
        "GROUNDED",
        ["chunk-01635-5726"],
        "The current node's own Input — equivalent to writing `self.Input`.",
    ),
    (
        "expression_syntax",
        "Why does `Point(Text1.Center.X, Text1.Center.Y-.1)` need to be wrapped in `Point(...)` "
        "instead of just written as a formula?",
        "GROUNDED",
        ["chunk-01635-5726"],
        "Because the target parameter expects a Point value (with X and Y members), not a plain "
        "Number — Point() constructs that composite value.",
    ),
    (
        "expression_syntax",
        "How do you concatenate strings in a Fusion SimpleExpression?",
        "GROUNDED",
        ["chunk-01635-5726"],
        'With the `..` operator (Lua-style concatenation), e.g. inside a '
        'Text("..."..variable) call.',
    ),
    (
        "expression_syntax",
        'What does `Merge1:GetValue("Blend", time-5)` do differently from just writing '
        "`Merge1.Blend`?",
        "GROUNDED",
        ["chunk-01634-5725"],
        "It samples the Blend input's value at a different frame (5 frames before the current one) "
        "instead of the current frame's value.",
    ),
    (
        "expression_syntax",
        "How do you insert a newline inside a Text() SimpleExpression?",
        "GROUNDED",
        ["chunk-01635-5726"],
        "With `\\n`.",
    ),
    (
        "expression_syntax",
        "How can a SimpleExpression read an environment variable, and what function is used?",
        "GROUNDED",
        ["chunk-01635-5726"],
        'With `os.getenv("VARNAME")`, e.g. `os.getenv("COMPUTERNAME")`.',
    ),
    (
        "expression_syntax",
        "What does the `comp` variable give a SimpleExpression access to?",
        "GROUNDED",
        ["chunk-01635-5726"],
        "Attributes of the current composition, such as `comp.Filename` (which can be passed "
        "through `ToUNC()` for a UNC path).",
    ),
    (
        "expression_syntax",
        "What is 'pick whipping' in Fusion, and how do you do it?",
        "GROUNDED",
        ["chunk-01636-2332"],
        "With a SimpleExpression field open, drag the '+' button on the left onto another control "
        "to link the two parameters — similar to Connect To, but the resulting expression can be "
        "further edited afterward.",
    ),
    (
        "expression_syntax",
        "Besides the Inspector, where else can you create or edit a SimpleExpression?",
        "GROUNDED",
        ["chunk-01636-2332"],
        "In the Spline Editor — right-click the parameter and choose Set SimpleExpression.",
    ),
    (
        "expression_syntax",
        "How do you remove a SimpleExpression from a parameter?",
        "GROUNDED",
        ["chunk-01637-2333"],
        "Right-click the parameter's name and choose Remove Expression from the contextual menu.",
    ),
    (
        "expression_syntax",
        "In the manual's DirectionalBlur example, what's the exact SimpleExpression used to "
        "drive the Length parameter from the node's Center onscreen control?",
        "GROUNDED",
        ["chunk-01637-2334"],
        "sqrt(((Center.X-.5)*(self.Input.XScale))^2+((Center.Y-.5)*(self.Input.YScale)*"
        "(self.Input.Height/self.Input.Width))^2)",
    ),
    (
        "expression_syntax",
        "In that same DirectionalBlur example, what's the Angle SimpleExpression, and why is "
        "the result multiplied by 180/pi?",
        "GROUNDED",
        ["chunk-01637-2334"],
        "atan2(.5-Center.Y, .5-Center.X) * 180 / pi — the multiplication converts atan2's radian "
        "result into degrees, since the Angle field is in degrees.",
    ),
    (
        "expression_syntax",
        "What does `iif(TypeNew==0, 0, 2)` do in the custom-checkbox Edit Controls example?",
        "GROUNDED",
        ["chunk-01637-2336"],
        "It drives a Type menu's index from a new checkbox control: if the checkbox (TypeNew) is "
        "0, the Type is set to index 0; otherwise it's set to index 2.",
    ),
    (
        "expression_syntax",
        "What's the difference between the Expression modifier and a plain SimpleExpression?",
        "GROUNDED",
        ["chunk-01632-2326"],
        "The Expression modifier provides its own controls in the Modifiers tab, giving more room "
        "and parameters than a SimpleExpression field does.",
    ),
    (
        "expression_syntax",
        "Can you perform a calculation directly in a numeric field without opening a full "
        "SimpleExpression? Give an example.",
        "GROUNDED",
        ["chunk-01634-2328"],
        "Yes — typing a simple equation like `2.0 + 4.0` directly into most number fields "
        "calculates the result (6.0) without needing the `=` SimpleExpression syntax.",
    ),
    (
        "expression_syntax",
        "What are the three mechanisms Fusion provides for going beyond its standard keyframed "
        "tools, per the manual's own introduction to this topic?",
        "GROUNDED",
        ["chunk-01629-2317"],
        "Modifiers, Expressions, and Scripting.",
    ),
    (
        "expression_syntax",
        "How do you add a modifier to a parameter in the Inspector?",
        "GROUNDED",
        ["chunk-01630-2320"],
        "Right-click the parameter and choose from the Modify With submenu — the available "
        "modifiers are filtered based on the parameter's type (numeric, text, polyline, gradient, "
        "point, etc.).",
    ),
    # ---------------- composed_animation ----------------
    (
        "composed_animation",
        "How do I make a layer bounce like a rubber ball hitting the ground, using a Fusion "
        "expression?",
        "SYNTHESIZED",
        ["chunk-01635-5726", "chunk-02929-3609"],
        "The manual documents the primitives (sin/time expressions on p.1635, Transform's Center "
        "Y on p.2929) but has no built-in 'bounce' recipe — compose a decaying periodic curve like "
        "`abs(cos(Frequency*time))*exp(-Decay*time)` driving Transform1.Center.Y, per the "
        "fusion-expressions skill's math-patterns.md.",
    ),
    (
        "composed_animation",
        "How do I add a spring-like overshoot to a keyframed move in Fusion?",
        "SYNTHESIZED",
        ["chunk-01635-5726", "chunk-01631-2322"],
        "No built-in spring feature exists. The manual shows combining a keyframed motion path "
        "with an auto-animating modifier (p.1631) as the closest documented pattern; for a literal "
        "spring, compose a damped-oscillator SimpleExpression (e.g. "
        "Target+Amplitude*exp(-Decay*t)*cos(Frequency*t)) using the primitives on p.1635.",
    ),
    (
        "composed_animation",
        "How do I add a subtle wiggle to a Text+ layer's position?",
        "GROUNDED",
        ["chunk-01631-2322", "chunk-03072-3727"],
        "Apply the Perturb modifier (Modify With > Perturb) to the Center parameter and tune "
        "Strength/Wobble/Speed — this is a directly documented primitive (Perlin-noise-based "
        "jitter), not something that needs a hand-written expression.",
    ),
    (
        "composed_animation",
        "How do I make an object squash and stretch as it bounces, using the Transform node?",
        "SYNTHESIZED",
        ["chunk-02929-3609"],
        "Not a documented recipe. Turn off 'Use Size and Aspect' to get independent X/Y Size "
        "controls (p.2929), then drive one axis from your bounce curve and the other from a "
        "volume-preserving compensation like `1/sqrt(YScale)` — see math-patterns.md.",
    ),
    (
        "composed_animation",
        "How do I ease a keyframed animation smoothly in and out instead of linearly, without "
        "writing an expression?",
        "GROUNDED",
        ["chunk-01604-2290"],
        "Use the Spline Editor's built-in interpolation modes — select the keyframe(s) and apply "
        "Smooth (Shift-S) for a gentle ease in/out, as opposed to Linear (Shift-L) or the Step "
        "In/Out modes. This is directly documented, not something to compose.",
    ),
    (
        "composed_animation",
        "Write a Fusion SimpleExpression for an ease-in-out cubic curve between two values over "
        "a fixed duration.",
        "SYNTHESIZED",
        ["chunk-01635-5726"],
        "Not documented as a recipe — compose it from the verified `iif` and `^` primitives "
        "(p.1635): normalize progress to t in [0,1], then "
        "`iif(t<0.5, 4*t^3, 1-((-2*t+2)^3)/2)` lerped between the start and end values.",
    ),
    (
        "composed_animation",
        "How do I make an object rotate continuously and indefinitely using an expression, "
        "rather than keyframing rotation?",
        "SYNTHESIZED",
        ["chunk-01635-5726", "chunk-02929-3611"],
        "Drive the Transform node's Angle parameter (p.2929) directly with an expression using "
        "the `time` primitive (p.1635), e.g. `time * RotationsPerFrame * 360`.",
    ),
    (
        "composed_animation",
        "How do I pulse a parameter's value back and forth between two numbers repeatedly?",
        "GROUNDED",
        ["chunk-01635-5726"],
        "This is essentially the manual's own worked example: `sin(time/20)/2+.5` (p.1635) "
        "produces a repeating 0-1 wave; scale and offset it to pulse between any two values.",
    ),
    (
        "composed_animation",
        "How do I create a damped oscillation that settles to a resting value over time, using "
        "SimpleExpressions?",
        "SYNTHESIZED",
        ["chunk-01635-5726"],
        "No built-in feature — compose it from the verified `sin`/`cos`/`time` primitives "
        "(p.1635): `Target + Amplitude * exp(-Decay*time) * cos(Frequency*time)` decays the "
        "oscillation toward Target as time increases.",
    ),
    (
        "composed_animation",
        "How do I offset one layer's position from another's by a fixed amount, so it follows "
        "with a consistent spacing?",
        "GROUNDED",
        ["chunk-01635-5726"],
        "This is directly documented: `Point(Text1.Center.X, Text1.Center.Y-.1)` or the equivalent "
        "`Text1.Center - Point(0,.1)` (p.1635) offsets one node's position from another's.",
    ),
    (
        "composed_animation",
        "How do I control a Directional Blur's length and angle from a single onscreen point "
        "instead of two separate sliders?",
        "GROUNDED",
        ["chunk-01637-2334"],
        "This is a fully worked example in the manual (p.1637-1638): drive Length with "
        "sqrt(((Center.X-.5)*(self.Input.XScale))^2+((Center.Y-.5)*(self.Input.YScale)*"
        "(self.Input.Height/self.Input.Width))^2) and Angle with "
        "atan2(.5-Center.Y,.5-Center.X)*180/pi.",
    ),
    (
        "composed_animation",
        "How do I create an elastic 'overshoot' pop-in entrance animation for a Transform's "
        "Size parameter, similar to CSS's easeOutBack?",
        "SYNTHESIZED",
        ["chunk-01635-5726", "chunk-02929-3609"],
        "Not documented. Compose an overshoot easing formula (e.g. "
        "1 + Overshoot*(t-1)^3 + (t-1)^2*(Overshoot+1)*(t-1), using the verified `^` operator from "
        "p.1635) and drive Transform1.Size (p.2929) with it, lerping from a start to end value.",
    ),
    (
        "composed_animation",
        "Does Fusion have a one-click, built-in spring-physics simulator for animating a "
        "parameter, separate from writing an expression?",
        "SYNTHESIZED",
        ["chunk-01632-2326", "chunk-03072-3727"],
        "No — the closest built-in options are the Perturb and Shake modifiers (p.1632, p.3072), "
        "which generate Perlin-noise-based random jitter, not a physically-modeled spring/damper. "
        "A literal spring response has to be composed as a SimpleExpression.",
    ),
    # ---------------- out_of_scope (tests the UNVERIFIED gate) ----------------
    (
        "out_of_scope",
        "What specific noise octave count or lacunarity value does Fusion's Perturb modifier use "
        "internally when computing its Perlin noise?",
        "UNVERIFIED",
        [],
        "Not documented. The manual confirms Perturb is Perlin-noise-based but gives no "
        "implementation-level parameters like octave count or lacunarity.",
    ),
    (
        "out_of_scope",
        "How many bytes of memory does a single keyframe consume in a saved Fusion .comp file?",
        "UNVERIFIED",
        [],
        "Not documented — this is an internal file-format detail the user manual doesn't cover.",
    ),
    (
        "out_of_scope",
        "Which specific CPU instruction set (e.g. AVX2, SSE4) does Fusion's software renderer use "
        "for Gaussian blur calculations?",
        "UNVERIFIED",
        [],
        "Not documented — low-level rendering implementation isn't covered by the user manual.",
    ),
    (
        "out_of_scope",
        "Is DaVinci Resolve's Fusion page built on the same underlying node-graph engine as "
        "Blackmagic's ATEM switchers?",
        "UNVERIFIED",
        [],
        "Not documented — the manual doesn't compare Fusion's internal architecture to other "
        "Blackmagic products.",
    ),
    (
        "out_of_scope",
        "What is the maximum number of Perturb modifiers that can be chained on a single "
        "parameter before a measurable performance drop occurs?",
        "UNVERIFIED",
        [],
        "Not documented — no performance-limit figures for modifier chaining are given in the "
        "manual.",
    ),
]


def main() -> None:
    chunks = _load_chunks_by_id()
    examples: list[GoldExample] = []

    for i, (category, question, tier, source_ids, answer) in enumerate(RAW_ITEMS, start=1):
        if source_ids:
            source_chunks = [chunks[cid] for cid in source_ids]
            breadcrumbs = list(dict.fromkeys(c["breadcrumb"] for c in source_chunks))
            # One tight [min_page, max_page] range per unique breadcrumb, not one range spanning
            # all of them — composed_animation questions ground against multiple, disjoint manual
            # sections, and collapsing to a single envelope would make retrieval scoring treat the
            # (often huge) gap between them as if it were all relevant. See the expected_pages note
            # in eval/run_eval.py.
            pages_by_breadcrumb: dict[str, list[int]] = {}
            for c in source_chunks:
                r = pages_by_breadcrumb.setdefault(c["breadcrumb"], [c["page_start"], c["page_end"]])
                r[0] = min(r[0], c["page_start"])
                r[1] = max(r[1], c["page_end"])
            pages = [pages_by_breadcrumb[b] for b in breadcrumbs]
        else:
            breadcrumbs, pages = [], []

        examples.append(
            GoldExample(
                id=i,
                category=category,  # type: ignore[arg-type]
                question=question,
                expected_tier=tier,  # type: ignore[arg-type]
                expected_breadcrumbs=breadcrumbs,
                expected_pages=pages,
                answer=answer,
            )
        )

    with OUT_PATH.open("w") as f:
        for ex in examples:
            f.write(ex.model_dump_json() + "\n")

    print(f"wrote {len(examples)} gold examples to {OUT_PATH}")


if __name__ == "__main__":
    main()
