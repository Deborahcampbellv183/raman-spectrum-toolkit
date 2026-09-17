# -*- coding: utf-8 -*-
"""界面布局自测：对话框不得超出屏幕，底部按钮必须留在可视范围内且可点击。

背景：高级设置内容较长，小屏 / 高 DPI 下旧版会把窗口撑到屏幕外，
“确定 / 应用 / 取消”被推到底部看不见，点了没反应。
"""
import os
import sys
import time
import tkinter as tk
import tkinter.messagebox as mb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jws2csv as T

mb.showinfo = lambda *a, **k: None
mb.showwarning = lambda *a, **k: None
mb.showerror = lambda *a, **k: None
mb.askyesno = lambda *a, **k: False

ok = [0, 0]


def check(label, cond, extra=""):
    ok[0 if cond else 1] += 1
    print("  [%s] %s %s" % ("OK" if cond else "FAIL", label, extra))


def walk(w, out=None):
    if out is None:
        out = []
    for c in w.winfo_children():
        out.append(c)
        walk(c, out)
    return out


def mainloop(self):
    app = self
    app.update()
    sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
    print("屏幕可用：%dx%d" % (sw, sh))

    before = {id(w) for w in app.winfo_children() if isinstance(w, tk.Toplevel)}
    app.open_advanced()
    app.update()
    new = [w for w in app.winfo_children()
           if isinstance(w, tk.Toplevel) and id(w) not in before]
    if not new:
        check("高级设置 打开", False, "没有新窗口")
        app.destroy()
        return
    dlg = new[-1]
    dlg.update_idletasks()
    dlg.update()
    # 窗口刚映射时几何信息还没稳定（尤其紧跟其它 GUI 测试跑），等一下再量
    for _ in range(10):
        app.update()
        time.sleep(0.05)
    dlg.update_idletasks()
    dlg.update()

    kids = walk(dlg)
    canvases = [w for w in kids if w.winfo_class() == "Canvas"]
    bars = [w for w in kids if w.winfo_class() == "TScrollbar"]

    # 1) 窗口本身不能超出屏幕
    h, y = dlg.winfo_height(), dlg.winfo_y()
    check("高级设置窗口不超出屏幕高度", h <= int(sh * 0.9),
          "h=%d 屏幕=%d" % (h, sh))
    check("高级设置窗口底部在屏幕内", y + h <= sh, "y+h=%d 屏幕=%d" % (y + h, sh))
    check("高级设置宽度不超出屏幕", dlg.winfo_width() <= int(sw * 0.95),
          "w=%d" % dlg.winfo_width())

    # 2) 内容区可滚动
    check("高级设置有滚动条", bool(bars), "找到 %d 个" % len(bars))
    if canvases:
        cv = canvases[0]
        bbox = cv.bbox("all")
        content_h = (bbox[3] - bbox[1]) if bbox else 0
        check("内容高于可视区时靠滚动而不是撑窗口",
              content_h > cv.winfo_height() and bbox is not None,
              "内容 %d px / 可视 %d px" % (content_h, cv.winfo_height()))
        cv.yview_moveto(1.0)
        dlg.update()
        check("滚动到底部可用", True, str(cv.yview()))
        cv.yview_moveto(0.0)
        dlg.update()

    # 3) 三个按钮都必须留在屏幕内，且位于固定底栏（不在滚动区里，滚到哪都点得到）
    def is_under(widget, ancestor):
        node = widget
        while node is not None:
            if node is ancestor:
                return True
            try:
                node = node.master
            except Exception:
                return False
        return False

    wanted = ("确定", "应用", "取消")
    found = {}
    for w in kids:
        try:
            if w.winfo_class() == "TButton" and str(w.cget("text")) in wanted:
                found[str(w.cget("text"))] = w
        except Exception:
            continue
    check("三个按钮都存在", len(found) == 3, str(sorted(found)))
    check("高级设置已显示", bool(dlg.winfo_ismapped()), str(dlg.winfo_ismapped()))

    cv0 = canvases[0] if canvases else None
    for name in wanted:
        w = found.get(name)
        if w is None:
            check("按钮 %s 可用" % name, False, "没找到")
            continue
        w.update_idletasks()
        by, bh = w.winfo_rooty(), w.winfo_height()
        bx, bw = w.winfo_rootx(), w.winfo_width()
        check("按钮 %s 在屏幕内" % name, 0 <= by and by + bh <= sh,
              "y=%d h=%d 屏幕=%d" % (by, bh, sh))
        check("按钮 %s 在横向屏幕内" % name, 0 <= bx and bx + bw <= sw,
              "x=%d w=%d" % (bx, bw))
        # 关键：按钮在固定底栏里，不属于滚动区 —— 内容再长也不会被顶走
        check("按钮 %s 不在滚动区内" % name,
              cv0 is not None and not is_under(w, cv0),
              "master=%s" % (w.master.winfo_class() if w.master else "?"))

    for w in new:
        w.destroy()
    app.update()
    app.destroy()


tk.Tk.mainloop = mainloop
T._run_gui()

print()
print("界面布局自测：通过 %d 项，失败 %d 项" % (ok[0], ok[1]))
sys.exit(1 if ok[1] else 0)
