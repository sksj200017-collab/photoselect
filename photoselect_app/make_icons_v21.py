#!/usr/bin/env python3
"""生成漫画风模式图标：风光（严格去重）/ 人像（同主体筛选）+ 主图标"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(OUT, exist_ok=True)


def rounded_mask(size, radius):
    m = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([2, 2, size-3, size-3], radius=radius, fill=255)
    return m


def comic_bg(size, base, border=(60, 60, 60)):
    """漫画风卡片底：纯色 + 细浅色描边（去掉粗黑框）"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 细浅描边（圆润边缘）
    d.rounded_rectangle([0, 0, size-1, size-1], radius=int(size*0.18),
                        fill=base)
    return img


def sun(d, cx, cy, r, color=(255, 193, 7)):
    d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)


def mountain(d, x0, y0, x1, y1, color=(76, 175, 80)):
    """画一座山：三角形"""
    d.polygon([(x0, y1), ((x0+x1)//2, y0), (x1, y1)], fill=color)


def make_landscape(size=256):
    """风光图标：蓝天 + 太阳 + 山 + 云（严格去重）"""
    img = comic_bg(size, (135, 206, 250))   # 天蓝底
    d = ImageDraw.Draw(img)
    s = size / 256
    # 太阳
    sun(d, int(190*s), int(70*s), int(38*s))
    # 云
    d.ellipse([int(50*s), int(60*s), int(110*s), int(85*s)], fill=(255, 255, 255))
    d.ellipse([int(70*s), int(45*s), int(120*s), int(75*s)], fill=(255, 255, 255))
    d.ellipse([int(95*s), int(58*s), int(140*s), int(80*s)], fill=(255, 255, 255))
    # 远山（浅绿）
    mountain(d, int(20*s), int(200*s), int(140*s), int(120*s), (129, 199, 132))
    # 近山（深绿）
    mountain(d, int(100*s), int(200*s), int(240*s), int(110*s), (76, 175, 80))
    # 地面
    d.rectangle([0, int(200*s), size, size], fill=(139, 195, 74))
    return img


def make_portrait(size=256):
    """人像图标：人形剪影 + 背景（同主体筛选）"""
    img = comic_bg(size, (255, 236, 179))   # 暖黄底
    d = ImageDraw.Draw(img)
    s = size / 256
    # 背景圆
    d.ellipse([int(58*s), int(40*s), int(198*s), int(180*s)],
              fill=(255, 224, 130))
    # 头
    d.ellipse([int(98*s), int(60*s), int(158*s), int(120*s)],
              fill=(93, 64, 55))
    # 身体（圆弧）
    d.pieslice([int(70*s), int(105*s), int(186*s), int(230*s)],
               180, 360, fill=(93, 64, 55))
    # 笑脸
    d.arc([int(112*s), int(78*s), int(144*s), int(106*s)],
          20, 160, fill=(255, 255, 255), width=int(5*s))
    # 眼睛
    d.ellipse([int(114*s), int(80*s), int(122*s), int(88*s)], fill=(255, 255, 255))
    d.ellipse([int(134*s), int(80*s), int(142*s), int(88*s)], fill=(255, 255, 255))
    # 腮红
    d.ellipse([int(100*s), int(95*s), int(116*s), int(107*s)], fill=(255, 138, 101))
    d.ellipse([int(140*s), int(95*s), int(156*s), int(107*s)], fill=(255, 138, 101))
    return img


def make_main_icon(size=256):
    """主图标：漫画风 'PS' 圆角方块（相机镜头风格）"""
    img = comic_bg(size, (3, 155, 229))     # 亮蓝底
    d = ImageDraw.Draw(img)
    s = size / 256
    # 镜头圈
    d.ellipse([int(58*s), int(48*s), int(198*s), int(188*s)],
              outline=(255, 255, 255), width=int(10*s))
    d.ellipse([int(85*s), int(75*s), int(171*s), int(161*s)],
              fill=(255, 255, 255))
    d.ellipse([int(105*s), int(95*s), int(151*s), int(141*s)],
              fill=(3, 155, 229))
    # 顶部闪光
    d.rounded_rectangle([int(90*s), int(24*s), int(166*s), int(46*s)],
                        radius=int(8*s), fill=(255, 193, 7))
    # 底部文字条
    d.rounded_rectangle([int(50*s), int(196*s), int(206*s), int(228*s)],
                        radius=int(10*s), fill=(255, 255, 255))
    try:
        font = ImageFont.truetype("arialbd.ttf", int(20*s))
    except Exception:
        font = ImageFont.load_default()
    text = "PhotoSelect"
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    d.text((int((size-tw)/2), int(200*s)), text, fill=(3, 155, 229), font=font)
    return img


if __name__ == "__main__":
    make_landscape().save(os.path.join(OUT, "mode_landscape.png"))
    make_portrait().save(os.path.join(OUT, "mode_portrait.png"))
    make_main_icon().save(os.path.join(OUT, "icon_256.png"))
    # ico
    Image.open(os.path.join(OUT, "icon_256.png")).save(
        os.path.join(OUT, "icon.ico"),
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("漫画风图标已生成:", OUT)
