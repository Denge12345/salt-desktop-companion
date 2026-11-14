"""Convert a GIF (or a strip of frames) into Codex-v2-ready PNG frames.

Typical GIF workflow
--------------------
1. Find an authorised source (see docs/02-asset-plan.md).
2. Extract, de-background, trim, scale and baseline-align each state:

       python tools/import_gif.py --gif assets/wave.gif --state waving \
           --out build/frames/waving --max-frames 4

3. Build the atlas from the frame folders:

       python tools/build_atlas.py --frames-dir build/frames

The script writes transparent 192x208 PNGs, so unused columns can stay empty
and the atlas composer never has to guess alignment.

Notes
-----
* Background removal is a border flood fill. It handles flat cel-shaded
  backgrounds well; photographs / gradients need a real matte.
* ``--mirror`` is for producing running-left from a right-facing cycle.
* ``--strip`` slices a horizontal sprite strip instead of reading a GIF.
"""

from __future__ import annotations

import argparse
import statistics
from collections import deque
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

CELL_W, CELL_H = 192, 208
SAFE_W, SAFE_H = 176, 196
BASELINE = 202


def estimate_bg(img: Image.Image) -> tuple[int, int, int]:
    """Median colour of the 1px border."""
    w, h = img.size
    px = img.load()
    samples = []
    for x in range(0, w, max(1, w // 64)):
        samples.append(px[x, 0][:3])
        samples.append(px[x, h - 1][:3])
    for y in range(0, h, max(1, h // 64)):
        samples.append(px[0, y][:3])
        samples.append(px[w - 1, y][:3])
    return tuple(int(statistics.median(c[i] for c in samples)) for i in range(3))


def remove_background(img: Image.Image, tolerance: int, bg: tuple[int, int, int] | None = None) -> Image.Image:
    """Flood-fill the border-connected background to alpha 0."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    bg = bg or estimate_bg(img)
    br, bgc, bb = bg
    tol2 = tolerance * tolerance * 3

    def near(c):
        dr, dg, db = c[0] - br, c[1] - bgc, c[2] - bb
        return dr * dr + dg * dg + db * db <= tol2

    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if near(px[x, y]):
                q.append((x, y))
                seen[y * w + x] = 1
    for y in range(h):
        for x in (0, w - 1):
            if near(px[x, y]) and not seen[y * w + x]:
                q.append((x, y))
                seen[y * w + x] = 1

    while q:
        x, y = q.popleft()
        r, g, b, _ = px[x, y]
        px[x, y] = (r, g, b, 0)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                if near(px[nx, ny]):
                    seen[ny * w + nx] = 1
                    q.append((nx, ny))
    return img


def despill(img: Image.Image, bg: tuple[int, int, int], strength: float = 0.6) -> Image.Image:
    """Pull background colour out of the semi-transparent edge pixels."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    br, bgc, bb = bg
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            if 0 < a < 250:
                # Undo the matte contribution instead of tinting toward it.
                alpha = a / 255
                def unmatte(value, background):
                    clean = (value - background * (1 - alpha)) / alpha
                    return round(max(0, min(255, value + (clean - value) * strength)))
                r, g, b = unmatte(r, br), unmatte(g, bgc), unmatte(b, bb)
                px[x, y] = (r, g, b, a)
    return img


def trim_to_content(img: Image.Image) -> Image.Image:
    alpha = img.getchannel("A").point(lambda v: 255 if v > 8 else 0)
    bbox = alpha.getbbox()
    return img.crop(bbox) if bbox else img


def fit_cell(img: Image.Image, max_w: int = SAFE_W, max_h: int = SAFE_H) -> Image.Image:
    img = trim_to_content(img)
    scale = min(max_w / img.width, max_h / img.height, 1.0)
    if scale < 1.0:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    cell = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
    x = (CELL_W - img.width) // 2
    y = max(0, BASELINE - img.height)
    cell.alpha_composite(img, (x, y))
    return cell


def frames_from_gif(path: Path, every: int = 1):
    im = Image.open(path)
    out = []
    for i, frame in enumerate(ImageSequence.Iterator(im)):
        if i % every:
            continue
        out.append(frame.convert("RGBA").copy())
    return out


def frames_from_strip(path: Path, cols: int):
    im = Image.open(path).convert("RGBA")
    if cols < 1 or cols > im.width or im.width % cols:
        raise ValueError('strip width must be divisible by a positive column count')
    w = im.width // cols
    return [im.crop((i * w, 0, (i + 1) * w, im.height)) for i in range(cols)]


def pick_uniform(frames, n):
    if n is None or n >= len(frames):
        return frames
    if n == 1:
        return [frames[0]]
    idx = [round(i * (len(frames) - 1) / (n - 1)) for i in range(n)]
    return [frames[i] for i in idx]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--gif", type=Path)
    src.add_argument("--strip", type=Path)
    ap.add_argument("--cols", type=int, default=8, help="strip mode: number of frames in the strip")
    ap.add_argument("--state", required=True, help="target state name, e.g. waving")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-frames", type=int, default=None)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--tolerance", type=int, default=34)
    ap.add_argument("--no-key", action="store_true", help="keep the original background")
    ap.add_argument("--despill", action="store_true")
    ap.add_argument("--mirror", action="store_true")
    ap.add_argument("--max-w", type=int, default=SAFE_W)
    ap.add_argument("--max-h", type=int, default=SAFE_H)
    args = ap.parse_args()
    if args.max_frames is not None and args.max_frames < 1:
        ap.error('--max-frames must be positive')
    if not 1 <= args.max_w <= CELL_W or not 1 <= args.max_h <= BASELINE:
        ap.error('--max-w / --max-h must fit inside the cell and baseline')
    if args.every < 1 or args.cols < 1 or args.tolerance < 0:
        ap.error('--every / --cols must be positive; --tolerance must be non-negative')

    if args.gif:
        frames = frames_from_gif(args.gif, every=max(1, args.every))
    else:
        frames = frames_from_strip(args.strip, max(1, args.cols))
    if not frames:
        raise SystemExit("no frames found")
    frames = pick_uniform(frames, args.max_frames)

    bg = None
    if not args.no_key:
        bg = estimate_bg(frames[0])
        print(f"background key: rgb{bg}  tolerance={args.tolerance}")

    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.png"):
        old.unlink()

    for i, frame in enumerate(frames):
        img = frame
        if not args.no_key:
            img = remove_background(img, args.tolerance, bg)
            if args.despill:
                img = despill(img, bg)
        if args.mirror:
            img = ImageOps.mirror(img)
        cell = fit_cell(img, args.max_w, args.max_h)
        cell.save(args.out / f"{i:02d}.png")

    print(f"wrote {len(frames)} frames to {args.out}  state={args.state}")
    print(f"next: python tools/build_atlas.py --frames-dir {args.out.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
