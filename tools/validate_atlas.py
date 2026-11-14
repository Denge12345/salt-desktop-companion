"""Validate a Codex v2 spritesheet and its pet.json.

Checks the hard contract plus the QA rules from the remielle / PetPack docs:

* 1536x2288, 8x11, 192x208 cells, RGBA
* rows 0-8 use exactly the documented frame counts
* unused standard cells are fully transparent
* rows 9-10 contain all 16 look directions
* no content touches a cell edge (avoids bleeding when scaled)
* corners are transparent (no baked background)
* file size below the 16 MiB packaging limit
* pet.json points at an existing sheet and declares spriteVersionNumber 2

Exit code 0 = pass (warnings allowed), 1 = failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image

CELL_W, CELL_H = 192, 208
COLS, ROWS = 8, 11
ATLAS_W, ATLAS_H = CELL_W * COLS, CELL_H * ROWS
STATES = [
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
FRAMES = [6, 8, 8, 4, 5, 8, 6, 6, 6]
ALPHA_THRESHOLD = 8
MIN_CONTENT_PIXELS = 40


def cell_alpha_bbox(img: Image.Image, col: int, row: int):
    cell = img.crop((col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H))
    alpha = cell.getchannel("A")
    return alpha.point(lambda v: 255 if v > ALPHA_THRESHOLD else 0).getbbox()


def content_pixels(img: Image.Image, col: int, row: int) -> int:
    cell = img.crop((col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H))
    hist = cell.getchannel("A").histogram()
    return sum(hist[ALPHA_THRESHOLD + 1:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("atlas", type=Path, nargs="?", default=Path("pets/salt/spritesheet.webp"))
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--max-mib", type=float, default=16.0)
    args = ap.parse_args()
    if not math.isfinite(args.max_mib) or args.max_mib <= 0:
        ap.error('--max-mib must be finite and positive')

    errors: list[str] = []
    warnings: list[str] = []
    report = {"atlas": str(args.atlas), "checks": [], "errors": errors, "warnings": warnings}

    if not args.atlas.is_file():
        errors.append(f'missing atlas: {args.atlas}')
        report['ok'] = False
        return finish(report, args.json_out)

    size_bytes = args.atlas.stat().st_size
    if size_bytes > args.max_mib * 1024 * 1024:
        errors.append(f"file is {size_bytes/1024/1024:.2f} MiB, limit {args.max_mib} MiB")

    try:
        img = Image.open(args.atlas)
        img.load()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        errors.append(f'cannot decode atlas: {exc}')
        report['ok'] = False
        return finish(report, args.json_out)
    fmt = (img.format or "").lower()
    if fmt not in ("webp", "png"):
        errors.append(f"format {img.format!r} is not WebP/PNG")
    if img.size != (ATLAS_W, ATLAS_H):
        errors.append(f"size {img.size[0]}x{img.size[1]}, expected {ATLAS_W}x{ATLAS_H}")
        report.update(size=list(img.size), ok=False)
        return finish(report, args.json_out)
    if 'A' not in img.getbands() and 'transparency' not in img.info:
        errors.append('atlas has no transparency channel')
    img = img.convert("RGBA")

    # transparent background at the four outer corners
    for x, y in [(0, 0), (ATLAS_W - 1, 0), (0, ATLAS_H - 1), (ATLAS_W - 1, ATLAS_H - 1)]:
        if img.getpixel((x, y))[3] > ALPHA_THRESHOLD:
            errors.append("outer corner is not transparent (baked background?)")
            break

    # standard rows
    for row, state in enumerate(STATES):
        expected = FRAMES[row]
        row_hashes = []
        for col in range(COLS):
            n = content_pixels(img, col, row)
            bbox = cell_alpha_bbox(img, col, row)
            if col < expected:
                if n < MIN_CONTENT_PIXELS:
                    errors.append(f"row {row} {state}: frame {col} is empty")
                elif bbox and (bbox[0] < 2 or bbox[1] < 2 or bbox[2] > CELL_W - 2 or bbox[3] > CELL_H - 2):
                    warnings.append(f"row {row} {state}: frame {col} touches the cell edge")
                row_hashes.append(hashlib.sha256(
                    img.crop((col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H)).tobytes()
                ).hexdigest())
            else:
                cell = img.crop((col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H))
                if cell.getchannel('A').getbbox() is not None:
                    errors.append(f"row {row} {state}: unused column {col} is not transparent ({n} px)")
        if len(row_hashes) > 1 and len(set(row_hashes)) == 1:
            warnings.append(f"row {row} {state}: all frames are identical (static animation?)")

    # A nonempty cell does not prove its gaze angle; duplicate frames are a QA warning.
    look_hashes = []
    for k in range(16):
        row, col = 9 + k // 8, k % 8
        n = content_pixels(img, col, row)
        if n < MIN_CONTENT_PIXELS:
            errors.append(f"look {k} ({k*22.5:g}deg): empty cell row {row} col {col}")
        cell = img.crop((col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H))
        look_hashes.append(hashlib.sha256(cell.tobytes()).hexdigest())
    if len(set(look_hashes)) != 16:
        warnings.append(f'look frames contain duplicates: {len(set(look_hashes))}/16 unique')

    # manifest
    manifest_path = args.manifest or args.atlas.with_name("pet.json")
    manifest = None
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            if not isinstance(manifest, dict):
                raise ValueError('manifest must be a JSON object')
        except (OSError, ValueError) as exc:
            errors.append(f'invalid pet.json: {exc}')
            manifest = {}
        if manifest.get("spriteVersionNumber") != 2:
            errors.append("pet.json spriteVersionNumber must be 2 for an 11-row atlas")
        for key in ("id", "displayName", "spritesheetPath"):
            if not isinstance(manifest.get(key), str) or not manifest[key].strip():
                errors.append(f"pet.json missing {key}")
        sheet = manifest.get('spritesheetPath')
        if isinstance(sheet, str) and sheet:
            pet = (manifest_path.parent / sheet).resolve()
            if not pet.is_relative_to(manifest_path.parent.resolve()):
                errors.append('pet.json spritesheetPath escapes the pet directory')
            elif pet != args.atlas.resolve():
                errors.append(f'pet.json points at a different atlas: {pet}')
            elif not pet.is_file():
                errors.append(f'pet.json points at missing spritesheet: {pet}')
    else:
        errors.append(f"missing pet.json ({manifest_path})")

    report.update(
        {
            "format": fmt,
            "bytes": size_bytes,
            "mib": round(size_bytes / 1024 / 1024, 3),
            "size": list(img.size),
            "sha256": hashlib.sha256(args.atlas.read_bytes()).hexdigest(),
            "manifest": manifest,
            "ok": not errors,
        }
    )

    return finish(report, args.json_out)


def finish(report, json_out=None) -> int:
    errors, warnings = report['errors'], report['warnings']
    for e in errors:
        print(f"FAIL  {e}")
    for w in warnings:
        print(f"WARN  {w}")
    print(
        f"{'PASS' if not errors else 'FAIL'}  {report['atlas']}  "
        f"({len(errors)} errors, {len(warnings)} warnings)"
    )

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report: {json_out}")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
