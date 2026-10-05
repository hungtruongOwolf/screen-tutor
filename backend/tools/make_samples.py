"""Writes the sample screenshots offered by the web playground.

    python tools/make_samples.py

They are the first triangle, toolbar and bullet cases of the evaluation set.
"""

import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.cases import build_cases  # noqa: E402

OUT = ROOT / "app" / "static" / "samples"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    picks = {
        "triangle": next(c for c in cases if c.kind == "triangle"),
        "toolbar": next(c for c in cases if c.kind == "toolbar"),
        "bullets": next(c for c in cases if c.kind == "bullets"),
    }
    for name, case in picks.items():
        # cv2.imwrite cannot write to a path with non-ASCII characters on Windows.
        ok, encoded = cv2.imencode(".png", case.image)
        assert ok
        (OUT / f"{name}.png").write_bytes(encoded.tobytes())
        print(name, "->", case.question)


if __name__ == "__main__":
    main()
