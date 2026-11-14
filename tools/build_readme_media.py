"""Build compact README previews from the actual exported atlases (no redraw)."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont
from build_atlas import contact_sheet

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/assets'
BG = '#f6f4fb'
INK = '#3d3155'


def font(size):
    for name in ['C:/Windows/Fonts/msyh.ttc', 'NotoSansCJK-Regular.ttc', 'Arial Unicode.ttf']:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Pillow 10.0, still allowed by requirements.txt, has no size argument.
        return ImageFont.load_default()


def cell(sheet, row, col):
    return sheet.crop((col * 192, row * 208, (col + 1) * 192, (row + 1) * 208)).convert('RGBA')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with Image.open(ROOT / 'pets/salt/spritesheet.webp') as im:
        base = im.convert('RGBA')
    with Image.open(ROOT / 'pets/salt/expressions.webp') as im:
        extra = im.convert('RGBA')
    meta = json.loads((ROOT / 'pets/salt/expressions.json').read_text(encoding='utf-8'))
    items = {item['id']: item for item in meta['items']}
    # GIF: a shared palette keeps colors stable between frames.
    frames = []
    for step in range(36):
        frame = Image.new('RGB', (704, 290), BG)
        draw = ImageDraw.Draw(frame)
        draw.text((22, 12), '莎露朵 · Salt', font=font(20), fill=INK)
        demos = [(base, 3, 4, '挥手 · 原生'), (base, 4, 5, '点赞 · 原生'),
                 (extra, items['excited']['row'], 6, '期待 · 可选表情')]
        for i, (sheet, row, count, label) in enumerate(demos):
            x = 16 + i * 228
            draw.rounded_rectangle((x, 45, x + 216, 258), radius=16, fill='white')
            image = cell(sheet, row, (step // 2) % count).resize((168, 182), Image.Resampling.LANCZOS)
            frame.paste(image, (x + 24, 47), image)
            draw.text((x + 24, 229), label, font=font(16), fill=INK)
        draw.text((22, 270), '原始素材抽帧预览 · @0x4682B4 · 来源与许可见 NOTICE.md', font=font(11), fill='#776b8b')
        frames.append(frame)
    palette_source = Image.new('RGB', (6 * 176, 6 * 73))
    for i, frame in enumerate(frames):
        palette_source.paste(frame.resize((176, 73)), (i % 6 * 176, i // 6 * 73))
    palette = palette_source.quantize(colors=192)
    indexed = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    indexed[0].save(OUT / 'demo.gif', save_all=True, append_images=indexed[1:],
                    duration=100, loop=0, optimize=True, disposal=2)

    cards = [
        ('安静待机', 'idle', base, 0, 2), ('向右移动', 'running-right', base, 1, 2),
        ('向左移动', 'running-left', base, 2, 2), ('挥手招呼', 'waving', base, 3, 1),
        ('点赞庆祝', 'jumping', base, 4, 2), ('摇头受挫', 'failed', base, 5, 2),
        ('喝茶等待', 'waiting', base, 6, 2), ('专注工作', 'running', base, 7, 2),
        ('思考检查', 'review', base, 8, 2),
    ]
    for item in meta['items']:
        cards.append((item['label'], 'optional / ' + item['id'], extra, item['row'], 2))
    cards.append(('16 向视线', 'look / 90 deg', base, 9, 4))
    gallery = Image.new('RGB', (960, 1100), BG)
    d = ImageDraw.Draw(gallery)
    d.text((24, 18), '动作图鉴', font=font(25), fill=INK)
    d.text((24, 54), '9 个标准动作 + 4 个可选表情 + 16 向视线', font=font(15), fill='#776b8b')
    for i, (label, key, sheet, row, col) in enumerate(cards):
        x, y = 20 + i % 4 * 236, 90 + i // 4 * 246
        d.rounded_rectangle((x, y, x + 216, y + 230), radius=16, fill='white')
        image = cell(sheet, row, col).resize((160, 173), Image.Resampling.LANCZOS)
        gallery.paste(image, (x + 28, y + 4), image)
        d.text((x + 16, y + 183), label, font=font(17), fill=INK)
        d.text((x + 16, y + 208), key, font=font(12), fill='#776b8b')
    # Use the remaining two grid columns for an installation legend.
    d.rounded_rectangle((492, 828, 944, 1058), radius=16, fill='#eee9f8')
    d.text((514, 850), '一个资源包，日常与互动', font=font(23), fill=INK)
    d.text((514, 897), '原生安装', font=font(16), fill=INK)
    d.text((514, 925), 'pet.json + spritesheet.webp', font=font(16), fill='#776b8b')
    d.text((514, 972), '更多表情', font=font(16), fill=INK)
    d.text((514, 1000), '在独立预览器中手动切换', font=font(16), fill='#776b8b')
    d.text((28, 1080), '图像来自实际导出图集 · 素材作者 @0x4682B4 · 详见 NOTICE.md', font=font(12), fill='#776b8b')
    gallery.save(OUT / 'actions.webp', 'WEBP', quality=86, method=6)
    # Detailed grid is linked, rather than expanded to full height in README.
    qa_path = ROOT / 'build/readme-atlas.png'
    contact_sheet(base, qa_path)
    with Image.open(qa_path) as image:
        image.save(OUT / 'atlas.webp', 'WEBP', quality=85, method=6)
    for name in ['demo.gif', 'actions.webp', 'atlas.webp']:
        print(f'{name}: {(OUT / name).stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
