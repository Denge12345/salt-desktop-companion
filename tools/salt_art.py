"""Procedural placeholder art for the Salt (銈姐儷銉?/ 鑾庨湶鏈? Codex v2 pet.

This is deliberately a *placeholder*: a clean, readable chibi cat-girl that
keeps Salt's identity anchors (pale-lavender hair, cat ears, green-violet eyes,
CAFE MiLK maid outfit, bell, bushy tail, baker/salt motif) so the atlas,
renderer and state machine can be built and tested end to end.

Replace it with hand-drawn / commissioned / licensed frames by dropping PNGs
into ``frames/<state>/`` and running ``build_atlas.py --frames-dir``.

All drawing happens in a 192x208 logical cell, rendered at 4x and downsampled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

CELL_W, CELL_H = 192, 208
S = 4  # supersampling factor
W, H = CELL_W * S, CELL_H * S

# ---------------------------------------------------------------- palette
OUTLINE = (74, 60, 92, 255)
HAIR = (203, 182, 232, 255)
HAIR_DARK = (166, 140, 203, 255)
HAIR_LIGHT = (232, 221, 248, 255)
HAIR_TIP = (244, 239, 255, 255)
SKIN = (255, 232, 221, 255)
SKIN_SHADOW = (244, 199, 185, 255)
EYE_WHITE = (255, 250, 253, 255)
IRIS_TOP = (128, 219, 181, 255)
IRIS_BOTTOM = (138, 111, 208, 255)
PUPIL = (43, 35, 62, 255)
DRESS = (61, 92, 152, 255)
DRESS_DARK = (43, 68, 116, 255)
APRON = (255, 252, 246, 255)
APRON_SHADOW = (226, 220, 240, 255)
CYAN = (146, 227, 234, 255)
CYAN_DARK = (104, 190, 203, 255)
BELL = (244, 201, 93, 255)
BELL_DARK = (203, 156, 54, 255)
RIBBON = (127, 107, 208, 255)
RIBBON_LIGHT = (167, 151, 232, 255)
BLUSH = (247, 158, 172, 150)
TEAR = (161, 216, 247, 255)
SHOE = (58, 50, 78, 255)

STATES = {
    "idle": 6,
    "running-right": 8,
    "running-left": 8,
    "waving": 4,
    "jumping": 5,
    "failed": 8,
    "waiting": 6,
    "running": 6,
    "review": 6,
}

# Nominal per-frame duration in milliseconds (renderer defaults; a pet.json
# ``tracks`` entry may override these).
TRACK_DURATIONS = {
    "idle": [200] * 6,
    "running-right": [100] * 8,
    "running-left": [100] * 8,
    "waving": [180, 150, 150, 180],
    "jumping": [140, 110, 150, 130, 180],
    "failed": [170] * 8,
    "waiting": [220] * 6,
    "running": [150] * 6,
    "review": [180] * 6,
}

TRACK_LOOP = {
    "idle": True,
    "running-right": True,
    "running-left": True,
    "waving": False,
    "jumping": False,
    "failed": False,
    "waiting": True,
    "running": True,
    "review": True,
}


# ---------------------------------------------------------------- helpers
def _sc(v: float) -> float:
    return v * S


def _box(b):
    return tuple(_sc(v) for v in b)


def ell(d: ImageDraw.ImageDraw, box, fill=None, outline=None, width=0.0):
    d.ellipse(_box(box), fill=fill, outline=outline, width=int(width * S))


def rrect(d, box, radius, fill=None, outline=None, width=0.0):
    d.rounded_rectangle(
        _box(box),
        radius=_sc(radius),
        fill=fill,
        outline=outline,
        width=int(width * S),
    )


def poly(d, pts, fill=None, outline=None, width=0.0):
    d.polygon([(_sc(x), _sc(y)) for x, y in pts], fill=fill, outline=outline)
    if outline and width:
        d.line(
            [(_sc(x), _sc(y)) for x, y in pts] + [(_sc(pts[0][0]), _sc(pts[0][1]))],
            fill=outline,
            width=int(width * S),
            joint="curve",
        )


def line(d, pts, fill, width, joint="curve"):
    d.line([(_sc(x), _sc(y)) for x, y in pts], fill=fill, width=int(width * S), joint=joint)


def radial_glow(size, color, radius, alpha=255):
    """Soft round blob used for blush / soft shading."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((0, 0, size - 1, size - 1), fill=color[:3] + (alpha,))
    return layer.filter(ImageFilter.GaussianBlur(radius))


@dataclass
class Pose:
    bob: float = 0.0
    lean: float = 0.0
    head_dx: float = 0.0
    head_dy: float = 0.0
    head_tilt: float = 0.0
    blink: float = 0.0
    pupil_x: float = 0.0
    pupil_y: float = 0.0
    mouth: str = "smile"
    ear_drop: float = 0.0
    ear_perk: float = 0.0
    arm_l: tuple[float, float] = (0.0, 0.0)  # hand offset from rest position
    arm_r: tuple[float, float] = (0.0, 0.0)
    leg_phase: float = 0.0
    leg_tuck: float = 0.0
    tail_angle: float = 0.0
    blush: float = 0.55
    tears: float = 0.0
    eye_scale: float = 1.0
    lid: float = 0.0  # extra upper-lid coverage (focus / droop)
    mouth_open: float = 0.0
    sweat: float = 0.0
    sparkle: float = 0.0


# ---------------------------------------------------------------- tail
def draw_tail(im: Image.Image, pose: Pose):
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bx, by = 124.0, 182.0 + pose.bob
    a = math.radians(pose.tail_angle)
    # control points of a soft S curve, rotated around the tail base
    pts = [(bx, by), (144, 172 + pose.bob), (162, 158 + pose.bob), (167, 140 + pose.bob), (158, 128 + pose.bob)]
    rot = []
    for x, y in pts:
        dx, dy = x - bx, y - by
        rot.append(
            (
                bx + dx * math.cos(a) - dy * math.sin(a),
                by + dx * math.sin(a) + dy * math.cos(a),
            )
        )
    # Build one continuous silhouette: outline pass then fill pass. Drawing
    # each bead with its own outline would read as a string of pearls.
    ol = Image.new("RGBA", im.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ol)
    for i in range(len(rot) - 1):
        w0 = 8.4 - 1.1 * i
        w1 = 8.4 - 1.1 * (i + 1)
        steps = 10
        for k in range(steps):
            f = k / steps
            x = rot[i][0] + (rot[i + 1][0] - rot[i][0]) * f
            y = rot[i][1] + (rot[i + 1][1] - rot[i][1]) * f
            r = w0 + (w1 - w0) * f
            ell(od, (x - r - 1.6, y - r - 1.6, x + r + 1.6, y + r + 1.6), fill=OUTLINE)
            ell(d, (x - r, y - r, x + r, y + r), fill=HAIR)
    # white tip blob
    tip = rot[-1]
    ell(od, (tip[0] - 7.0, tip[1] - 7.0, tip[0] + 7.0, tip[1] + 7.0), fill=OUTLINE)
    ell(d, (tip[0] - 5.5, tip[1] - 5.5, tip[0] + 5.5, tip[1] + 5.5), fill=HAIR_TIP)
    im.alpha_composite(ol)
    im.alpha_composite(layer)
    # a couple of light strands on the tail
    d2 = ImageDraw.Draw(im)
    line(d2, [(134, 160), (146, 146), (150, 132)], (236, 226, 250, 200), 2.2)


# ---------------------------------------------------------------- body
def draw_body(im: Image.Image, pose: Pose):
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    y = pose.bob
    lean = pose.lean

    # back hair behind the body
    ell(d, (48 + lean, 44 + y, 144 + lean, 168 + y), fill=HAIR_DARK)

    # legs
    for side, phase in ((-1, pose.leg_phase), (1, pose.leg_phase + math.pi)):
        lx = 96 + side * 10
        lift = max(0.0, math.sin(phase)) * 5 * (1 if pose.leg_phase else 0)
        lift += pose.leg_tuck
        ly = 178 + y - lift
        ell(d, (lx - 6, ly - 2, lx + 6, ly + 16), fill=EYE_WHITE, outline=OUTLINE, width=1.4)
        ell(d, (lx - 7, ly + 11, lx + 7, ly + 20), fill=SHOE, outline=OUTLINE, width=1.4)

    # neck
    rrect(d, (90 + lean, 118 + y, 102 + lean, 134 + y), 4, fill=SKIN, outline=OUTLINE, width=1.4)

    # dress skirt (bell shaped)
    poly(
        d,
        [
            (78 + lean, 146 + y),
            (114 + lean, 146 + y),
            (128 + lean, 181 + y),
            (64 + lean, 181 + y),
        ],
        fill=DRESS,
        outline=OUTLINE,
        width=1.8,
    )
    # skirt hem
    ell(d, (64 + lean, 174 + y, 128 + lean, 187 + y), fill=CYAN, outline=OUTLINE, width=1.8)
    # bodice
    rrect(d, (80 + lean, 128 + y, 112 + lean, 154 + y), 7, fill=DRESS, outline=OUTLINE, width=1.8)
    # collar + bell
    rrect(d, (85 + lean, 125 + y, 107 + lean, 133 + y), 3, fill=DRESS_DARK, outline=OUTLINE, width=1.3)
    ell(d, (92 + lean, 130 + y, 100 + lean, 138 + y), fill=BELL, outline=OUTLINE, width=1.2)
    ell(d, (95.2 + lean, 134.4 + y, 96.8 + lean, 136.2 + y), fill=BELL_DARK)
    line(d, [(96 + lean, 131 + y), (96 + lean, 134.6 + y)], BELL_DARK, 0.9)
    # white apron
    poly(
        d,
        [
            (84 + lean, 136 + y),
            (108 + lean, 136 + y),
            (113 + lean, 178 + y),
            (79 + lean, 178 + y),
        ],
        fill=APRON,
        outline=OUTLINE,
        width=1.5,
    )
    rrect(d, (82 + lean, 133 + y, 110 + lean, 141 + y), 3, fill=APRON, outline=OUTLINE, width=1.2)
    # little cat-face pocket
    ell(d, (87 + lean, 152 + y, 105 + lean, 166 + y), fill=(250, 246, 240, 255), outline=OUTLINE, width=1.2)
    ell(d, (90 + lean, 151 + y, 96 + lean, 157 + y), fill=DRESS_DARK)
    ell(d, (96 + lean, 151 + y, 102 + lean, 157 + y), fill=DRESS_DARK)

    # salt shaker charm on the apron
    rrect(d, (108 + lean, 150 + y, 116 + lean, 160 + y), 2.5, fill=(252, 252, 255, 255), outline=OUTLINE, width=1.2)
    rrect(d, (107.5 + lean, 148 + y, 116.5 + lean, 152 + y), 2, fill=CYAN_DARK, outline=OUTLINE, width=1.1)
    for dx in (0, 3):
        ell(d, (109.5 + dx + lean, 149 + y, 111.5 + dx + lean, 151 + y), fill=OUTLINE)

    # arms (sleeves + forearms + hands)
    for side, off in ((-1, pose.arm_l), (1, pose.arm_r)):
        sx = 96 + side * 19 + lean
        sy = 137 + y
        hx = sx + side * 6 + off[0]
        hy = sy + 14 + off[1]
        ell(d, (sx - 9, sy - 8, sx + 9, sy + 10), fill=DRESS, outline=OUTLINE, width=1.6)
        line(d, [(sx + side * 5, sy + 5), (hx, hy)], OUTLINE, 9, joint="curve")
        line(d, [(sx + side * 5, sy + 5), (hx, hy)], SKIN, 6.5)
        ell(d, (hx - 5.2, hy - 5.2, hx + 5.2, hy + 5.2), fill=SKIN, outline=OUTLINE, width=1.5)

    im.alpha_composite(layer)


# ---------------------------------------------------------------- head
def draw_eye(cx, cy, rx, ry, pose: Pose, iris_shift=(0.0, 0.0), closed_line=True):
    """Return an RGBA eye layer of size (rx*2+pad, ry*2+pad) at 4x."""
    pad = 4
    w = int((rx * 2 + pad * 2) * S)
    h = int((ry * 2 + pad * 2) * S)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ox, oy = pad, pad

    def L(box):
        return tuple((pad + v) * S for v in box)

    # eye white
    d.ellipse(L((0, 0, rx * 2, ry * 2)), fill=EYE_WHITE, outline=OUTLINE, width=int(1.8 * S))
    # iris gradient clipped to the eye: green crown fading into violet
    irx, iry = rx * 0.78, ry * 0.82
    iw, ih = int(irx * 2 * S), int(iry * 2 * S)
    grad = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for yy in range(ih):
        t = yy / max(1, ih - 1)
        if t < 0.42:
            col = IRIS_TOP
        elif t < 0.62:
            f = (t - 0.42) / 0.2
            col = tuple(int(IRIS_TOP[i] + (IRIS_BOTTOM[i] - IRIS_TOP[i]) * f) for i in range(3))
        else:
            col = IRIS_BOTTOM
        gd.line([(0, yy), (iw, yy)], fill=tuple(col[:3]) + (255,))
    # darker top rim
    gd.rectangle((0, 0, iw, int(ih * 0.08)), fill=(92, 176, 150, 255))
    mask = Image.new("L", (iw, ih), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, iw - 1, ih - 1), fill=255)
    grad.putalpha(mask)
    ix = int((pad + rx - irx + iris_shift[0]) * S)
    iy = int((pad + ry - iry + iris_shift[1]) * S)
    layer.alpha_composite(grad, (ix, iy))
    # iris rim
    d.ellipse(
        tuple((pad + rx - irx + iris_shift[0] + v) * S for v in (0, 0, irx * 2, iry * 2)),
        outline=(74, 62, 108, 220),
        width=int(1.1 * S),
    )
    # pupil
    prx, pry = rx * 0.5, ry * 0.62
    pcx = pad + rx + iris_shift[0]
    pcy = pad + ry + iris_shift[1] + 0.5
    d.ellipse(
        ((pcx - prx) * S, (pcy - pry) * S, (pcx + prx) * S, (pcy + pry) * S),
        fill=PUPIL,
    )
    # highlights
    d.ellipse(
        ((pcx - prx - 1.2) * S, (pcy - pry - 0.6) * S, (pcx - prx + 3.2) * S, (pcy - pry + 4.4) * S),
        fill=(255, 255, 255, 240),
    )
    d.ellipse(
        ((pcx + 2.2) * S, (pcy + 3.0) * S, (pcx + 4.6) * S, (pcy + 5.4) * S),
        fill=(255, 255, 255, 180),
    )
    # eyelash top
    d.arc(L((-1, -1, rx * 2 + 1, ry * 2.2)), 185, 355, fill=OUTLINE, width=int(2.6 * S))

    blink = max(pose.blink, pose.lid)
    if blink > 0:
        cover = int(min(1.0, blink) * (ry * 2 + 2) * S)
        cover_img = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        cd = ImageDraw.Draw(cover_img)
        cd.rectangle((0, 0, w, cover), fill=SKIN)
        # keep the outer eye shape: only cover inside the eye ellipse
        eye_mask = Image.new("L", layer.size, 0)
        ImageDraw.Draw(eye_mask).ellipse(L((0, 0, rx * 2, ry * 2)), fill=255)
        cover_img.putalpha(Image.composite(cover_img.getchannel("A"), Image.new("L", layer.size, 0), eye_mask))
        layer.alpha_composite(cover_img)
        if blink > 0.75 and closed_line:
            yline = (pad + ry * 0.6) * S
            d.arc(
                ((pad + 1) * S, (yline - ry * 0.55 * S), (pad + rx * 2 - 1) * S, (yline + ry * 0.6 * S)),
                200,
                340,
                fill=OUTLINE,
                width=int(2.4 * S),
            )
    return layer


def draw_head(im: Image.Image, pose: Pose):
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = 96.0, 86.0
    tilt = pose.head_tilt
    yoff = pose.head_dy

    # ears (drawn first so the head sits on top of their base)
    for side in (-1, 1):
        bx = cx + side * 34
        by = cy - 36 + pose.ear_perk * -2 + pose.ear_drop * 2
        tipx = bx + side * 12
        tipy = by - 32 + pose.ear_drop * 14
        base = [(bx - 12, by + 2), (tipx, tipy), (bx + 12, by + 1)]
        poly(d, base, fill=HAIR, outline=OUTLINE, width=1.8)
        inner = [
            (bx - 6, by - 1),
            (bx + side * 8, by - 22 + pose.ear_drop * 10),
            (bx + 7, by - 1),
        ]
        poly(d, inner, fill=(246, 193, 208, 255), outline=(212, 150, 172, 200), width=1.0)
        # ear fluff
        line(d, [(bx - 3, by - 2), (bx, by - 7), (bx + 3, by - 2)], HAIR_LIGHT, 4)

    # back hair cap
    ell(d, (cx - 44, cy - 44, cx + 44, cy + 46), fill=HAIR, outline=OUTLINE, width=1.8)

    # face
    ell(d, (cx - 39, cy - 34, cx + 39, cy + 40), fill=SKIN, outline=OUTLINE, width=1.8)

    # blush
    if pose.blush > 0:
        for side in (-1, 1):
            gx = cx + side * 26
            glow = radial_glow(int(18 * S), (247, 158, 172), 5 * S, int(150 * pose.blush))
            layer.alpha_composite(glow, (int((gx - 9) * S), int((cy + 18 - 9) * S)))

    # eyes
    ex = 17.0
    eye_rx, eye_ry = 12.5 * pose.eye_scale, 14.5 * pose.eye_scale
    look = (pose.pupil_x, pose.pupil_y)
    for side in (-1, 1):
        eye = draw_eye(
            cx + side * ex,
            cy + 8,
            eye_rx,
            eye_ry,
            pose,
            iris_shift=(look[0] * 0.55, look[1] * 0.55),
        )
        pad = 4
        px = int((cx + side * ex - eye_rx - pad) * S)
        py = int((cy + 8 - eye_ry - pad) * S)
        layer.alpha_composite(eye, (px, py))

    # brows (bean brows)
    for side in (-1, 1):
        ell(
            d,
            (cx + side * 26 - 3, cy - 7, cx + side * 26 + 3, cy - 3),
            fill=HAIR_DARK,
        )

    # nose + mouth
    ell(d, (cx - 1, cy + 16, cx + 1.4, cy + 18), fill=(226, 176, 166, 255))
    if pose.mouth == "smile":
        d.arc(_box((cx - 5, cy + 19, cx + 1, cy + 25)), 10, 160, fill=OUTLINE, width=int(1.5 * S))
        d.arc(_box((cx - 1, cy + 19, cx + 5, cy + 25)), 20, 170, fill=OUTLINE, width=int(1.5 * S))
    elif pose.mouth == "small":
        d.arc(_box((cx - 3, cy + 20, cx + 3, cy + 24)), 20, 160, fill=OUTLINE, width=int(1.4 * S))
    elif pose.mouth == "sad":
        d.arc(_box((cx - 4, cy + 23, cx + 4, cy + 27)), 200, 340, fill=OUTLINE, width=int(1.5 * S))
    elif pose.mouth == "open":
        oh = 3 + pose.mouth_open * 4
        ell(d, (cx - 4, cy + 19, cx + 4, cy + 19 + oh), fill=(180, 92, 108, 255), outline=OUTLINE, width=1.2)
        ell(d, (cx - 2, cy + 21, cx + 2, cy + 22.4), fill=(240, 150, 160, 255))
    elif pose.mouth == "flat":
        line(d, [(cx - 4, cy + 22), (cx + 4, cy + 22)], OUTLINE, 1.5)

    # tears
    if pose.tears > 0:
        for side in (-1, 1):
            tx = cx + side * 22
            ty = cy + 16
            drop = Image.new("RGBA", im.size, (0, 0, 0, 0))
            dd = ImageDraw.Draw(drop)
            dd.ellipse(
                tuple((tx - 2.2 + v) * S for v in (0, 0, 4.4, 4.4)),
                fill=TEAR,
            )
            dd.polygon(
                [((tx - 2.2) * S, ty * S), (tx * S, (ty - 1.2) * S), ((tx + 2.2) * S, ty * S)],
                fill=TEAR,
            )
            im.alpha_composite(drop)
            break

    # bangs: one soft mass with a jagged fringe, no internal outline clutter
    ell(d, (cx - 44, cy - 46, cx + 44, cy - 2), fill=HAIR)
    d.arc(_box((cx - 44, cy - 46, cx + 44, cy - 2)), 180, 360, fill=OUTLINE, width=int(1.8 * S))
    fringe = [
        (cx - 43, cy - 16),
        (cx - 37, cy - 5),
        (cx - 30, cy - 12),
        (cx - 22, cy - 3),
        (cx - 13, cy - 12),
        (cx - 4, cy - 2),
        (cx + 5, cy - 12),
        (cx + 14, cy - 3),
        (cx + 23, cy - 12),
        (cx + 31, cy - 4),
        (cx + 40, cy - 14),
        (cx + 44, cy - 30),
        (cx + 36, cy - 44),
        (cx - 36, cy - 44),
        (cx - 44, cy - 30),
    ]
    poly(d, fringe, fill=HAIR)
    line(d, fringe[:11], OUTLINE, 1.8)
    # soft highlight band
    line(d, [(cx - 30, cy - 34), (cx, cy - 39), (cx + 28, cy - 33)], HAIR_LIGHT, 5)

    # side locks (long, with pale tips)
    for side in (-1, 1):
        pts = [
            (cx + side * 36, cy - 18),
            (cx + side * 49, cy + 20),
            (cx + side * 45, cy + 52),
            (cx + side * 38, cy + 68),
            (cx + side * 30, cy + 50),
            (cx + side * 30, cy + 8),
        ]
        poly(d, pts, fill=HAIR, outline=OUTLINE, width=1.7)
        line(d, [(cx + side * 38, cy + 4), (cx + side * 39, cy + 34)], HAIR_LIGHT, 4)

    # ahoge
    aa = 4 * math.sin(pose.bob * 1.2)
    line(d, [(cx + 2, cy - 42), (cx + aa, cy - 56), (cx + 8 + aa, cy - 58)], HAIR, 4.5)
    ell(d, (cx + 6 + aa - 3, cy - 61, cx + 6 + aa + 3, cy - 55), fill=HAIR, outline=OUTLINE, width=1.2)

    # frilly headband sitting on top of the bangs
    rrect(d, (cx - 33, cy - 49, cx + 33, cy - 44), 2.5, fill=APRON)
    for k in range(-3, 4):
        ell(d, (cx + k * 9 - 3.3, cy - 45, cx + k * 9 + 3.3, cy - 39), fill=APRON)
    line(d, [(cx - 33, cy - 44), (cx - 33, cy - 49), (cx + 33, cy - 49), (cx + 33, cy - 44)], OUTLINE, 1.3)
    for k in range(-3, 4):
        d.arc(_box((cx + k * 9 - 3.3, cy - 45, cx + k * 9 + 3.3, cy - 39)), 0, 180, fill=OUTLINE, width=int(1.0 * S))
    # ribbon
    poly(d, [(cx + 31, cy - 49), (cx + 45, cy - 55), (cx + 43, cy - 44)], fill=RIBBON, outline=OUTLINE, width=1.2)
    poly(d, [(cx + 31, cy - 49), (cx + 17, cy - 55), (cx + 19, cy - 44)], fill=RIBBON_LIGHT, outline=OUTLINE, width=1.2)
    ell(d, (cx + 27, cy - 51, cx + 35, cy - 45), fill=RIBBON, outline=OUTLINE, width=1.1)

    # small sweat drop for effort states
    if pose.sweat > 0:
        sx, sy = cx + 38, cy - 14
        d.ellipse(tuple((sx - 3 + v) * S for v in (0, 0, 6, 6)), fill=TEAR, outline=CYAN_DARK, width=int(1.0 * S))
        d.polygon(
            [((sx - 3) * S, sy * S), (sx * S, (sy - 5) * S), ((sx + 3) * S, sy * S)],
            fill=TEAR,
        )

    # rotate around the head centre for a tilt, then shift
    layer = layer.rotate(-tilt, resample=Image.BICUBIC, center=(cx * S, cy * S))
    im.alpha_composite(layer, (int(pose.head_dx * S), int(yoff * S)))


# ---------------------------------------------------------------- public
def render_pose(pose: Pose) -> Image.Image:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_tail(im, pose)
    draw_body(im, pose)
    draw_head(im, pose)
    return im.resize((CELL_W, CELL_H), Image.LANCZOS)


def pose_for(state: str, i: int) -> Pose:
    """Return the procedural pose for a state/frame index."""
    n = STATES.get(state)
    if n is None:
        raise KeyError(state)
    t = i / n * math.tau
    p = Pose()

    if state == "idle":
        p.bob = math.sin(t) * 1.3
        p.head_dy = math.sin(t + 0.4) * 0.6
        p.blink = 0.55 if i == 2 else (1.0 if i == 3 else 0.0)
        p.blush = 0.5
        p.tail_angle = math.sin(t) * 9
        p.ear_perk = math.sin(t * 2) * 0.5
        p.mouth = "small"

    elif state == "running-right":
        p.lean = 2.2
        p.bob = abs(math.sin(t)) * 2.2
        p.leg_phase = t
        p.arm_l = (math.sin(t) * 4, math.cos(t) * 2)
        p.arm_r = (-math.sin(t) * 4, -math.cos(t) * 2)
        p.head_dx = 1.2
        p.tail_angle = 13 + math.sin(t) * 6
        p.mouth = "open"
        p.mouth_open = 0.3
        p.blink = 0.0

    elif state == "waving":
        # left hand raised beside the cheek, waving out and back
        p.arm_l = [(-24, -38), (-30, -43), (-21, -35), (-27, -41)][i]
        p.head_tilt = 4
        p.head_dy = -0.8
        p.mouth = "open"
        p.mouth_open = 0.4
        p.blush = 0.75
        p.tail_angle = -8
        p.ear_perk = 1.2
        p.bob = math.sin(t) * 0.8

    elif state == "jumping":
        p.bob = [8, -2, -16, -5, 4][i]
        p.leg_tuck = [6, 3, 8, 4, 0][i]
        p.arm_l = [(-2, 2), (-12, -18), (-10, -24), (-6, -12), (0, 0)][i]
        p.arm_r = [(2, 2), (12, -18), (10, -24), (6, -12), (0, 0)][i]
        p.mouth = "open" if i in (1, 2) else "smile"
        p.mouth_open = 0.5
        p.blink = 0.0 if i < 3 else 0.35
        p.tail_angle = [-6, 12, 20, 8, 0][i]
        p.blush = 0.7
        p.ear_perk = [0, 1, 1.5, 1, 0][i]

    elif state == "failed":
        p.head_dy = 3.2
        p.ear_drop = 1.0
        p.blink = 0.42 if i % 2 == 0 else 0.55
        p.mouth = "sad"
        p.tears = 1.0 if i >= 3 else 0.4
        p.tail_angle = -26
        p.bob = -1.2
        p.arm_l = (1, 4)
        p.arm_r = (-1, 4)
        p.head_tilt = 2.5 * math.sin(t * 2)
        p.blush = 0.35

    elif state == "waiting":
        p.bob = math.sin(t) * 1.0
        p.head_tilt = 5
        p.head_dx = 1
        p.arm_l = (5, -3)
        p.arm_r = (-5, -3)
        p.blink = 0.5 if i == 3 else 0.0
        p.mouth = "small"
        p.ear_perk = 1.0
        p.tail_angle = math.sin(t) * 6
        p.blush = 0.6

    elif state == "running":
        p.lean = 2.0
        p.bob = abs(math.sin(t * 2)) * 1.6
        p.head_dy = 2.4
        p.head_tilt = -3
        p.eye_scale = 0.95
        p.lid = 0.15
        p.arm_l = (8 + math.sin(t * 2) * 3, 1 + math.sin(t * 2) * 2)
        p.arm_r = (-8 + math.sin(t * 2 + math.pi) * 3, 1 + math.sin(t * 2 + math.pi) * 2)
        p.mouth = "flat"
        p.tail_angle = 10 + math.sin(t * 2) * 5
        p.sweat = 0.5

    elif state == "review":
        p.lean = 2
        p.head_tilt = -5
        p.head_dy = 2
        p.arm_r = (-2, -22)
        p.arm_l = (2, 3)
        p.pupil_x = [-2.6, 0, 2.6, 0, -2.6, 0][i]
        p.pupil_y = [0.5, 1.2, 0.5, 1.2, 0.5, 1.2][i]
        p.lid = 0.1
        p.mouth = "flat"
        p.blush = 0.4
        p.tail_angle = -4

    return p


def look_pose(direction_index: int) -> Pose:
    """16 clockwise directions starting at up (000)."""
    ang = math.radians(direction_index * 22.5)
    vx, vy = math.sin(ang), -math.cos(ang)
    p = Pose()
    p.pupil_x = vx * 4.2
    p.pupil_y = vy * 3.0
    p.head_dx = vx * 3.4
    p.head_dy = vy * 1.6
    p.head_tilt = vx * 3.0
    p.mouth = "small"
    p.blush = 0.5
    if vy < -0.4:  # looking up: eyes widen a touch
        p.eye_scale = 1.02
        p.lid = -0.05
    elif vy > 0.4:  # looking down: upper lid drops
        p.lid = 0.16
    p.tail_angle = -vx * 6
    return p


def render_state(state: str, count: int | None = None) -> list[Image.Image]:
    n = count or STATES[state]
    # running-left is a mirror of the right-facing cycle
    pose_state = "running-right" if state == "running-left" else state
    frames = []
    for i in range(n):
        img = render_pose(pose_for(pose_state, i))
        if state == "running-left":
            # Salt has no asymmetric marks that would break when flipped at
            # pet scale, so the mirrored cycle is a valid left-facing gait.
            img = ImageOps.mirror(img)
        frames.append(img)
    return frames


def render_looks() -> list[Image.Image]:
    return [render_pose(look_pose(i)) for i in range(16)]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Render one procedural Salt frame.")
    ap.add_argument("--state", default="idle")
    ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--out", default="build/sample.png")
    ap.add_argument("--scale", type=int, default=2)
    args = ap.parse_args()

    if args.state == "look":
        img = render_looks()[args.frame]
    else:
        frames = render_state(args.state)
        img = frames[args.frame % len(frames)]
    if args.scale != 1:
        img = img.resize((CELL_W * args.scale, CELL_H * args.scale), Image.LANCZOS)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)
    print(f"wrote {args.out} ({img.width}x{img.height})")

