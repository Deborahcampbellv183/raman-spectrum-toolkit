# -*- coding: utf-8 -*-
"""把 assets/icon_64.b64 内嵌进 jws2csv.py（生成 _APP_ICON_B64 常量 + 图标工具函数）。"""
import os

ROOT = r"f:\csv"
SRC = os.path.join(ROOT, "jws2csv.py")
B64 = open(os.path.join(ROOT, "assets", "icon_64.b64"), encoding="ascii").read().strip()

# 每 92 字符一段，便于阅读
chunks = [B64[i:i + 92] for i in range(0, len(B64), 92)]
body = "\n".join('    "%s"' % c for c in chunks)

snippet = '''# ===== 应用图标（内嵌 base64，冻结成 exe 后也能显示，无需外部文件）=====
_APP_ICON_B64 = (
''' + body + '''
)

_APP_ICON = [None]


def _app_icon():
    """返回 PhotoImage 形式的窗口图标（只创建一次）。"""
    if _APP_ICON[0] is None:
        try:
            import tkinter as _tk
            _APP_ICON[0] = _tk.PhotoImage(data=_APP_ICON_B64) or False
        except Exception:
            _APP_ICON[0] = False
    return _APP_ICON[0] or None


def _apply_icon(win):
    """给任意窗口（主窗口 / 对话框）套上应用图标。"""
    img = _app_icon()
    if img is None:
        return
    try:
        win.iconphoto(True, img)
    except Exception:
        pass


'''

src = open(SRC, encoding="utf-8").read()
marker = "_TEXT_CLASSES = ("
if "_APP_ICON_B64" in src:
    raise SystemExit("已经插入过，请先移除再重跑")
if marker not in src:
    raise SystemExit("找不到插入点")
src = src.replace(marker, snippet + marker, 1)
open(SRC, "w", encoding="utf-8", newline="").write(src)
print("inserted, b64 chars =", len(B64))
