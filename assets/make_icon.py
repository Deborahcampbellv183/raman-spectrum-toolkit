# -*- coding: utf-8 -*-
"""生成「拉曼光谱转换与鉴定工具」的应用图标。

产物：
    assets/icon.png        512×512，用于 README / 仓库展示
    assets/icon.ico        多尺寸（16/24/32/48/64/128/256），用于 exe 图标
    assets/icon_64.b64    64×64 PNG 的 base64，供程序内嵌（窗口 / 任务栏图标）

图标含义：深蓝底 = 科研仪器；白色折线 + 金色圆点 = 拉曼光谱峰及其标注。
不使用文字，保证 16 px 下仍然清晰。
"""
import base64
import io
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024          # 逻辑尺寸
SS = 4            # 超采样倍数，先画大再缩小，得到平滑边缘
W = S * SS


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _gradient():
    """左上深蓝 → 右下青蓝的对角渐变（先算小图再放大，快且平滑）。"""
    n = 192
    top = (12, 40, 66)
    bot = (22, 116, 148)
    small = Image.new("RGB", (n, n))
    px = small.load()
    for y in range(n):
        for x in range(n):
            t = (x + y) / (2.0 * (n - 1))
            px[x, y] = _lerp(top, bot, t)
    return small.resize((W, W), Image.BICUBIC)


def _rounded_mask(size, radius, supersample=1):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


# 光谱折线（归一化坐标：x 向右，y 向下，0.72 为基线）
_PTS = [
    (0.105, 0.72), (0.185, 0.72), (0.245, 0.50), (0.305, 0.72),
    (0.400, 0.29), (0.455, 0.72), (0.560, 0.575), (0.615, 0.72),
    (0.720, 0.415), (0.775, 0.72), (0.860, 0.615), (0.900, 0.72),
]
_PEAKS = (2, 4, 6, 8, 10)


def build():
    base = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    grad = _gradient().convert("RGBA")
    mask = _rounded_mask(W, int(W * 0.215))
    base.paste(grad, (0, 0), mask)

    # 顶部高光，让图标有一点立体感（高斯模糊后不留硬边）
    gloss = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(gloss).ellipse(
        [-int(W * 0.55), -int(W * 1.25), int(W * 1.55), int(W * 0.40)],
        fill=(255, 255, 255, 22))
    gloss = gloss.filter(ImageFilter.GaussianBlur(W * 0.06))
    base = Image.alpha_composite(base, Image.composite(
        gloss, Image.new("RGBA", (W, W), (0, 0, 0, 0)), mask))

    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # 基线（横轴）
    y0 = W * 0.72
    d.line([(W * 0.105, y0), (W * 0.900, y0)], fill=(255, 255, 255, 62),
           width=int(W * 0.006))

    pts = [(x * W, y * W) for x, y in _PTS]
    d.line(pts, fill=(255, 255, 255, 255), width=int(W * 0.027), joint="curve")

    # 峰顶标注点：金心 + 白圈，呼应工具里“自动标峰”的样子
    r = W * 0.028
    for i in _PEAKS:
        cx, cy = pts[i]
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 194, 75, 255))
        rr = r * 0.46
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 246, 226, 255))

    out = Image.alpha_composite(base, layer)
    return out.resize((S, S), Image.LANCZOS)


def main():
    icon = build()
    png = os.path.join(HERE, "icon.png")
    icon.resize((512, 512), Image.LANCZOS).save(png, "PNG")

    ico = os.path.join(HERE, "icon.ico")
    icon.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                          (64, 64), (128, 128), (256, 256)])

    small = icon.resize((64, 64), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, "PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    with open(os.path.join(HERE, "icon_64.b64"), "w", encoding="ascii") as f:
        f.write(b64)

    print("icon.png  ", os.path.getsize(png), "bytes")
    print("icon.ico  ", os.path.getsize(ico), "bytes")
    print("base64 len", len(b64))


if __name__ == "__main__":
    main()
