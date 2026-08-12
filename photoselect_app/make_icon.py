#!/usr/bin/env python3
"""生成 PhotoSelect 图标：模仿 Photoshop 风格（深蓝圆角方块 + PS 字样）"""
import os
from PIL import Image, ImageDraw, ImageFont

def rounded_rect_mask(size, radius):
    """生成圆角矩形 alpha 蒙版"""
    mask = Image.new('L', size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size[0]-1, size[1]-1], radius=radius, fill=255)
    return mask

def make_icon(size=256, output_path="icon.png"):
    """深蓝渐变圆角方块 + 白色 PS 字样"""
    # 基底：深蓝圆角方块
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))

    # 渐变背景（深蓝 → 亮蓝）
    bg = Image.new('RGB', (size, size), (0, 0, 0))
    d = ImageDraw.Draw(bg)
    top = (6, 60, 150)      # #063C96
    bottom = (28, 126, 228) # #1C7EE4
    for y in range(size):
        t = y / size
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        d.line([(0, y), (size, y)], fill=(r, g, b))

    # 圆角蒙版
    radius = int(size * 0.22)
    mask = rounded_rect_mask((size, size), radius)
    bg_rgba = bg.convert('RGBA')
    bg_rgba.putalpha(mask)

    # 中心白色圆底（PS 风格）
    d2 = ImageDraw.Draw(bg_rgba)
    circle_r = int(size * 0.34)
    cx, cy = size // 2, size // 2
    d2.ellipse([cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r],
               fill=(255, 255, 255, 255))

    # "PS" 字样（深蓝色）
    try:
        font = ImageFont.truetype("arialbd.ttf", int(size * 0.30))
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", int(size * 0.30))
        except Exception:
            font = ImageFont.load_default()

    text = "PS"
    # 测量文字
    bbox = d2.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw / 2 - bbox[0]
    ty = cy - th / 2 - bbox[1] + int(size * 0.02)
    d2.text((tx, ty), text, fill=(6, 60, 150), font=font)

    img = bg_rgba
    img.save(output_path)
    print(f"图标已生成: {output_path} ({size}x{size})")
    return output_path

if __name__ == "__main__":
    # 生成多尺寸（256 主图标 + ico）
    os.makedirs("assets", exist_ok=True)
    make_icon(256, "assets/icon_256.png")
    # 生成 .ico（含多尺寸）
    from PIL import Image as I
    icon256 = I.open("assets/icon_256.png")
    icon256.save("assets/icon.ico", sizes=[(16, 16), (32, 32), (48, 48),
                                            (64, 64), (128, 128), (256, 256)])
    print("icon.ico 已生成")
