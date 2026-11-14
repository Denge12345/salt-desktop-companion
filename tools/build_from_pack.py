"""Build Codex v2 frames from the user-provided 魔法盐巴 expression pack.

Source: https://www.bilibili.com/video/BV1Te896yE9d/
Author: @0x4682B4 (https://space.bilibili.com/1354443)
Terms : 禁止商用 / 禁止投喂 AI / 二创请告知

The pack is a 300x300 transparent PNGTuber-style bust. This script:
* selects clean frames per state (no UI, no floating confetti),
* scales 300x300 -> 184x184 inside the 192x208 cell,
* generates the 16 look directions by shifting the pink pupils + highlights
  inside the existing eye sockets (deterministic pixel editing, no AI).

Run:
    python tools/build_from_pack.py
    python tools/build_atlas.py --frames-dir build/pack-frames
"""

from __future__ import annotations

import math
import argparse
import json
import hashlib
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "魔法盐巴合集（43）2026-08-24-11-01-45"
OUT = ROOT / "build" / "pack-frames"
CELL_W, CELL_H = 192, 208

# state -> (gif stem, frame indices, dx list or None, dy list or None)
PLAN = {
    "idle": ("呆 3", [0, 16, 33, 49, 66, 82], None, None),
    "running-right": ("跳舞(Caramelldansen)", [0, 9, 18, 27, 36, 45, 54, 63], [2, 2, 1, 1, 0, -1, -1, -2], None),
    "running-left": ("跳舞(Caramelldansen)", [0, 9, 18, 27, 36, 45, 54, 63], [-2, -2, -1, -1, 0, 1, 1, 2], None),
    "waving": ("打招呼 1", [0, 16, 49, 82], None, None),
    "jumping": ("点赞", [0, 7, 18, 32, 48], None, None),
    "failed": ("摇头", [0, 4, 8, 12, 16, 20, 24, 28], None, None),
    "waiting": ("茶 （闭眼", [0, 13, 26, 39, 52, 65], None, None),
    "running": ("打游戏", [0, 8, 16, 24, 32, 38], None, None),
    "review": ("主意", [0, 9, 19, 46, 56, 65], None, None),
}

# Additional manual interactions: reuse standard playback tracks, separate sheet.
EXPRESSIONS = [
    ("cheer", "比耶", "jumping", "耶", [0, 10, 20, 30, 40]),
    ("shy", "害羞", "waving", "害羞 2", [0, 12, 28, 48]),
    ("excited", "期待", "waiting", "期待 2", [0, 11, 22, 33, 44, 55]),
    ("cry", "哭泣", "failed", "哭 2", [0, 14, 27, 41, 55, 69, 82, 96]),
]


def build_expressions(pet_out: Path) -> None:
    atlas = Image.new('RGBA', (CELL_W * 8, CELL_H * len(EXPRESSIONS)))
    items = []
    for row, (key, label, state, stem, indices) in enumerate(EXPRESSIONS):
        for col, index in enumerate(indices):
            atlas.alpha_composite(fit_cell(load_frame(stem, index)), (col * CELL_W, row * CELL_H))
        items.append(dict(id=key, label=label, state=state, row=row, frames=len(indices),
                          source=f'{stem}.gif', indices=indices))
    pet_out.mkdir(parents=True, exist_ok=True)
    sheet = pet_out / 'expressions.webp'
    atlas.save(sheet, 'WEBP', quality=92, method=6, exact=True)
    manifest = dict(schemaVersion=1, spritesheetPath=sheet.name, columns=8,
                    cell=dict(width=CELL_W, height=CELL_H), items=items,
                    sha256=hashlib.sha256(sheet.read_bytes()).hexdigest())
    (pet_out / 'expressions.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'expressions    -> {sheet} (4 manual interactions)')

# Eye sockets / pupils measured on the 300x300 neutral frame.
EYES = [
    # iris center/radius, pupil centre/radii, crop around the iris
    {"center": (105, 180), "r": 21, "pupil_center": (108, 186), "pupil_r": (16, 10), "crop": (82, 156, 128, 204)},
    {"center": (190, 196), "r": 21, "pupil_center": (193, 199), "pupil_r": (16, 9), "crop": (167, 172, 213, 220)},
]
TEAL = (82, 107, 132, 255)


def load_frame(gif_stem: str, index: int) -> Image.Image:
    path = SRC / f"{gif_stem}.gif"
    if not path.exists():
        raise FileNotFoundError(path)
    with Image.open(path) as im:
        index = max(0, min(index, im.n_frames - 1))
        im.seek(index)
        return im.convert("RGBA")


def fit_cell(fr: Image.Image, dx: int = 0, dy: int = 0) -> Image.Image:
    """Scale to 184x184, center horizontally, leaving transparent cell margins."""
    fr = fr.resize((184, 184), Image.LANCZOS)
    cell = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
    cell.alpha_composite(fr, ((CELL_W - 184) // 2 + dx, 20 + dy))
    return cell


def pupil_mask(crop: Image.Image, center: tuple[float, float], radii: tuple[float, float]) -> Image.Image:
    """Ellipse around the flat pink pupil (moves as one piece)."""
    mask = Image.new("L", crop.size, 0)
    cx, cy = center
    rx, ry = radii
    ImageDraw.Draw(mask).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    return mask


def shift_eye(im: Image.Image, eye: dict, dx: int, dy: int) -> Image.Image:
    x0, y0, x1, y1 = eye["crop"]
    crop = im.crop((x0, y0, x1, y1)).convert("RGBA")
    pcx, pcy = eye["pupil_center"]
    prx, pry = eye["pupil_r"]
    mask = pupil_mask(crop, (pcx - x0, pcy - y0), (prx, pry))

    # erase the old pupil with the flat iris colour
    base = crop.copy()
    base.paste(TEAL, mask=mask)

    # move the pupil together with its dithering pattern
    layer = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    pupil = crop.copy()
    pupil.putalpha(mask)
    layer.alpha_composite(pupil, (dx, dy))

    # keep it inside the iris
    cx, cy = eye["center"][0] - x0, eye["center"][1] - y0
    r = eye["r"]
    clip = Image.new("L", crop.size, 0)
    ImageDraw.Draw(clip).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), clip))
    base.alpha_composite(layer)

    out = im.copy()
    out.paste(base, (x0, y0))
    return out


def make_look(neutral: Image.Image, index: int) -> Image.Image:
    ang = math.radians(index * 22.5)
    dx = round(math.sin(ang) * 6)
    dy = round(-math.cos(ang) * 5)
    im = neutral
    for eye in EYES:
        im = shift_eye(im, eye, dx, dy)
    return im


def main() -> None:
    global SRC, OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SRC)
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--pet-out', type=Path, default=ROOT / 'pets' / 'salt', help='optional expression sheet output')
    args = parser.parse_args()
    SRC, OUT = args.source, args.out
    stems = {p[0] for p in PLAN.values()} | {p[3] for p in EXPRESSIONS}
    missing = [str(SRC / f'{stem}.gif') for stem in stems
               if not (SRC / f'{stem}.gif').is_file()]
    if missing:
        parser.error('missing source GIFs (use --source): ' + ', '.join(sorted(missing)))
    OUT.mkdir(parents=True, exist_ok=True)
    neutral = load_frame("呆 3", 0)

    for state, (stem, indices, dxs, dys) in PLAN.items():
        folder = OUT / state
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.png"):
            old.unlink()
        for i, idx in enumerate(indices):
            fr = load_frame(stem, idx)
            dx = dxs[i] if dxs else 0
            dy = dys[i] if dys else 0
            fit_cell(fr, dx, dy).save(folder / f"{i:02d}.png")
        print(f"{state:14s} <- {stem}.gif  frames={indices}")

    look = OUT / "look"
    look.mkdir(parents=True, exist_ok=True)
    for old in look.glob("*.png"):
        old.unlink()
    for i in range(16):
        fit_cell(make_look(neutral, i)).save(look / f"{i:02d}.png")
    print("look           <- 16 pupil-shift frames from 呆 3 frame 0")
    build_expressions(args.pet_out)


if __name__ == "__main__":
    main()
