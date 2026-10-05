// Geometry for shapes built on lines. Mirrors backend/app/geometry.py: keep in sync.
//
// Screen coordinates: x grows to the right, y grows downwards. "Left" and
// "right" of a line are as seen when looking along it from its first end to
// its second.

export type Line = readonly [number, number, number, number];
export type Side = "left" | "right";
export type Point = { x: number; y: number };

export function leftNormal(line: Line): Point {
  const dx = line[2] - line[0];
  const dy = line[3] - line[1];
  const length = Math.hypot(dx, dy) || 1;
  return { x: dy / length, y: -dx / length };
}

export function sideNormal(line: Line, side: Side): Point {
  const n = leftNormal(line);
  return side === "left" ? n : { x: -n.x, y: -n.y };
}

// The four corners of the square built on the line, on the given side. Its side
// is the line's length times `scale`.
export function squareCorners(line: Line, side: Side, scale = 1): Point[] {
  const [x1, y1, x2, y2] = line;
  const length = Math.hypot(x2 - x1, y2 - y1) * scale;
  const n = sideNormal(line, side);
  const norm = Math.hypot(x2 - x1, y2 - y1) || 1;
  const ux = ((x2 - x1) / norm) * length;
  const uy = ((y2 - y1) / norm) * length;
  return [
    { x: x1, y: y1 },
    { x: x1 + ux, y: y1 + uy },
    { x: x1 + ux + n.x * length, y: y1 + uy + n.y * length },
    { x: x1 + n.x * length, y: y1 + n.y * length },
  ];
}

export function centroid(points: Point[]): Point {
  const n = points.length || 1;
  return {
    x: points.reduce((sum, p) => sum + p.x, 0) / n,
    y: points.reduce((sum, p) => sum + p.y, 0) / n,
  };
}
