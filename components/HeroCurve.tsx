"use client";

import { useEffect, useRef } from "react";

// The curve is a damped oscillator — amplitude * exp(-decay*t) * cos(frequency*t) — the exact
// composed pattern a "spring" or "bounce" Fusion expression uses (see the fusion-expressions
// skill's math-patterns.md). This is the one bold visual moment on the page: the subject's own
// math, not a decorative abstract shape.
const WIDTH = 640;
const HEIGHT = 160;
const SAMPLES = 240;
const AMPLITUDE = 62;
const DECAY = 2.4;
const FREQUENCY = 11;

function buildPath(): string {
  const points: [number, number][] = [];
  for (let i = 0; i <= SAMPLES; i++) {
    const t = i / SAMPLES; // 0..1
    const y = AMPLITUDE * Math.exp(-DECAY * t) * Math.cos(FREQUENCY * t);
    const x = t * WIDTH;
    points.push([x, HEIGHT / 2 - y]);
  }
  return points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
}

export function HeroCurve() {
  const pathRef = useRef<SVGPathElement>(null);

  useEffect(() => {
    const path = pathRef.current;
    if (!path) return;
    const length = path.getTotalLength();
    path.style.setProperty("--curve-length", `${length}`);
    path.style.strokeDasharray = `${length}`;
    path.style.strokeDashoffset = `${length}`;
    // Trigger the CSS animation defined in globals.css after layout settles.
    requestAnimationFrame(() => {
      path.style.animation = "draw-curve 1.4s cubic-bezier(0.16, 1, 0.3, 1) forwards";
    });
  }, []);

  const d = buildPath();

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="w-full max-w-2xl"
      role="img"
      aria-label="A decaying oscillation curve, the kind of damped-spring math this tool helps you write as a Fusion expression"
    >
      <line
        x1="0"
        y1={HEIGHT / 2}
        x2={WIDTH}
        y2={HEIGHT / 2}
        stroke="var(--line)"
        strokeWidth="1"
      />
      <path
        ref={pathRef}
        d={d}
        fill="none"
        stroke="var(--signal-grounded)"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
