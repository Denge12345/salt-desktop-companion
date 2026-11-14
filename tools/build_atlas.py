"""Compose the Salt Codex v2 spritesheet.

Two modes
---------
procedural (default)
    Render every frame from ``salt_art.py``. Good for the placeholder package
    and for regenerating after you tweak the drawing code.

frames-dir
    Read ``<frames-dir>/<state>/<n>.png`` (192x208, transparent). Missing
    states fall back to the procedural renderer so the atlas is always
    complete. This is the entry point for GIF-derived or hand-drawn frames.

Output
------
* ``spritesheet.webp``      exact 1536x2288 Codex v2 atlas
* ``atlas-report.json``     frame counts, hashes, sizes
* ``contact-sheet.png``     labelled QA overview
* ``tray.png``              32x32 tray/window icon (first idle frame)

Usage
-----
    python tools/build_atlas.py
    python tools/build_atlas.py --frames-dir build/frames --out pets/salt/spritesheet.webp
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import salt_art  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COLUMNS, ROWS = 8, 11
CELL_W, CELL_H = salt_art.CELL_W, salt_art.CELL_H
ATLAS_W, ATLAS_H = CELL_W * COLUMNS, CELL_H * ROWS

STANDARD_STATES = [
    "idle",
    "running-right",
    "running-left",
    "waving",
    "jumping",
    "failed",
    "waiting",
    "running",
    "review",
]
FRAME_COUNTS = [salt_art.STATES[s] for s in STANDARD_STATES] + [8, 8]


def checker(size, square=8, a=(238, 238, 242, 255), b=(214, 214, 222, 255)):
    w, h = size
    im = Image.new("RGBA", (w, h), a)
    d = ImageDraw.Draw(im)
    for y in range(0, h, square):
        for x in range(0, w, square):
            if (x // square + y // square) % 2:
                d.rectangle((x, y, x + square - 1, y + square - 1), fill=b)
    return im


def fit_frame(img: Image.Image, cell_w=CELL_W, cell_h=CELL_H) -> Image.Image:
    """Normalise a source frame into one transparent cell."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    if img.size != (cell_w, cell_h):
        img.thumbnail((cell_w, cell_h), Image.LANCZOS)
        cell = Image.new('RGBA', (cell_w, cell_h))
        cell.alpha_composite(img, ((cell_w - img.width) // 2, cell_h - img.height))
        img = cell
    return img


def _numeric_key(p: Path):
    try:
        return (0, int(p.stem))
    except ValueError:
        return (1, p.stem)


def load_frames_dir(frames_dir: Path):
    """Return {state: [Image]} loaded from disk; states may be partial."""
    out = {}
    for state in STANDARD_STATES:
        folder = frames_dir / state
        if not folder.is_dir():
            continue
        files = sorted(folder.glob("*.png"), key=_numeric_key)
        frames = [fit_frame(Image.open(f).convert("RGBA")) for f in files]
        if frames:
            out[state] = frames
    looks = []
    look_folder = frames_dir / "look"
    if look_folder.is_dir():
        files = sorted(look_folder.glob("*.png"), key=_numeric_key)
        looks = [fit_frame(Image.open(f).convert("RGBA")) for f in files][:16]
    return out, looks


def build(frames_dir: Path | None):
    if frames_dir is not None and not frames_dir.is_dir():
        raise ValueError(f'frames directory does not exist: {frames_dir}')
    atlas = Image.new("RGBA", (ATLAS_W, ATLAS_H), (0, 0, 0, 0))
    report = {"cell": [CELL_W, CELL_H], "grid": [COLUMNS, ROWS], "rows": []}
    provided, looks = ({}, []) if frames_dir is None else load_frames_dir(frames_dir)

    for row, state in enumerate(STANDARD_STATES):
        expected = FRAME_COUNTS[row]
        if state in provided:
            frames = list(provided[state])
            source = "frames-dir"
        else:
            frames = salt_art.render_state(state)
            source = "procedural"
        frames = frames[:expected]
        if len(frames) < expected:
            # pad with the last available frame rather than leaving holes
            frames += [frames[-1]] * (expected - len(frames)) if frames else []
        for col in range(COLUMNS):
            if col < len(frames):
                atlas.alpha_composite(fit_frame(frames[col]), (col * CELL_W, row * CELL_H))
        report["rows"].append(
            {
                "row": row,
                "state": state,
                "frames": len(frames),
                "expected": expected,
                "source": source,
                "durations": salt_art.TRACK_DURATIONS[state],
                "loop": salt_art.TRACK_LOOP[state],
            }
        )

    supplied_looks = len(looks)
    if len(looks) < 16:
        looks = salt_art.render_looks() if not looks else looks + salt_art.render_looks()[len(looks):]
    for k in range(16):
        row = 9 + k // 8
        col = k % 8
        atlas.alpha_composite(fit_frame(looks[k]), (col * CELL_W, row * CELL_H))
        # look rows are also recorded for the validator
    report["looks"] = {
        "count": 16,
        "row9": [f"{d * 22.5:g}" for d in range(8)],
        "row10": [f"{d * 22.5:g}" for d in range(8, 16)],
        "source": 'frames-dir' if supplied_looks == 16 else 'mixed' if supplied_looks else 'procedural',
        "provided": supplied_looks,
    }
    return atlas, report


def contact_sheet(atlas: Image.Image, out: Path, thumb_w=104, labels=True):
    tw = thumb_w
    th = round(thumb_w * CELL_H / CELL_W)
    gutter = 8
    label_h = 14 if labels else 0
    top = 26
    W = COLUMNS * (tw + gutter) + gutter
    H = top + ROWS * (th + gutter + label_h * 2) + gutter
    sheet = Image.new("RGBA", (W, H), (246, 244, 250, 255))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 11)
        font_small = ImageFont.truetype("arial.ttf", 9)
    except OSError:
        font = ImageFont.load_default()
        font_small = font

    d.text((gutter, 6), "Salt  |  Codex v2 atlas 1536x2288  |  8x11 cells 192x208  |  art: @0x4682B4 (personal use)", fill=(60, 50, 80, 255), font=font)
    for row in range(ROWS):
        y = top + row * (th + gutter + label_h * 2)
        if row < 9:
            label = f"{row}  {STANDARD_STATES[row]}  ({FRAME_COUNTS[row]}f)"
        else:
            label = f"{row}  look  {'000-157.5' if row == 9 else '180-337.5'}"
        d.text((gutter, y), label, fill=(70, 60, 92, 255), font=font_small)
        for col in range(COLUMNS):
            x = gutter + col * (tw + gutter)
            yy = y + label_h
            cell = atlas.crop((col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H))
            bg = checker((tw, th), 6)
            bg.alpha_composite(cell.resize((tw, th), Image.LANCZOS))
            if row < 9 and col >= FRAME_COUNTS[row]:
                d2 = ImageDraw.Draw(bg)
                d2.rectangle((0, 0, tw - 1, th - 1), outline=(230, 120, 120, 120), width=1)
            sheet.alpha_composite(bg, (x, yy))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(out, quality=92)


def preview_image(atlas: Image.Image, out: Path):
    """A soft hero shot used in docs / chat."""
    W, H = 640, 520
    bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / H
        d.line(
            [(0, y), (W, y)],
            fill=(int(243 - 12 * t), int(238 - 16 * t), int(250 - 6 * t), 255),
        )
    # soft vignette drawn directly into the background (no clipped blob edges)
    vignette = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse((-W * 0.25, -H * 0.35, W * 1.25, H * 1.35), fill=90)
    vignette = vignette.filter(ImageFilter.GaussianBlur(120))
    tint = Image.new("RGBA", (W, H), (226, 214, 255, 255))
    tint.putalpha(vignette)
    bg.alpha_composite(tint)
    frame = atlas.crop((0, 0, CELL_W, CELL_H)).resize((CELL_W * 2, CELL_H * 2), Image.LANCZOS)
    bg.alpha_composite(frame, ((W - CELL_W * 2) // 2, (H - CELL_H * 2) // 2 + 10))
    try:
        font = ImageFont.truetype("arial.ttf", 22)
        small = ImageFont.truetype("arial.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
        small = font
    d.text((28, 24), "SALT", fill=(86, 70, 120, 255), font=font)
    d.text((30, 52), "Codex v2 pet  /  16 look directions  /  art pack by @0x4682B4", fill=(120, 105, 150, 255), font=small)
    out.parent.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").save(out, quality=94)


def tray_icon(atlas: Image.Image, out: Path):
    frame = atlas.crop((0, 0, CELL_W, CELL_H))
    bbox = frame.getbbox()
    if bbox:
        frame = frame.crop(bbox)
    icon = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    frame.thumbnail((30, 30), Image.LANCZOS)
    icon.alpha_composite(frame, ((32 - frame.width) // 2, (32 - frame.height) // 2))
    out.parent.mkdir(parents=True, exist_ok=True)
    icon.save(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "pets" / "salt" / "spritesheet.webp")
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--contact-sheet", type=Path, default=ROOT / "build" / "contact-sheet.png")
    ap.add_argument("--preview", type=Path, default=ROOT / "build" / "preview.png")
    ap.add_argument("--tray", type=Path, default=ROOT / "renderer" / "assets" / "tray.png")
    ap.add_argument("--quality", type=int, default=92)
    args = ap.parse_args()

    atlas, report = build(args.frames_dir)
    assert atlas.size == (ATLAS_W, ATLAS_H), atlas.size

    args.out.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(args.out, "WEBP", quality=args.quality, method=6, exact=True)
    data = args.out.read_bytes()
    try:
        display_path = str(args.out.resolve().relative_to(ROOT))
    except ValueError:
        display_path = str(args.out)
    report.update(
        {
            "file": display_path,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": list(atlas.size),
            "format": "webp",
            "mode": "RGBA",
        }
    )
    report_path = args.report or args.out.with_name("atlas-report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    contact_sheet(atlas, args.contact_sheet)
    preview_image(atlas, args.preview)
    tray_icon(atlas, args.tray)

    print(f"atlas   : {args.out}  {atlas.width}x{atlas.height}  {len(data)/1024/1024:.2f} MiB")
    print(f"report  : {report_path}")
    print(f"QA sheet: {args.contact_sheet}")
    print(f"preview : {args.preview}")
    print(f"tray    : {args.tray}")


if __name__ == "__main__":
    main()
