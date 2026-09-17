# -*- coding: utf-8 -*-
"""叠加图交互式预览自测：先预览、手动增减标注峰位，确认后才落盘。

用真实的 Tk 窗口跑一遍，不靠肉眼：
* 打开对话框时只在临时目录渲染预览，**输出目录里不许出现任何文件**；
* 画布上左键 = 加一个峰位（计数 +1），右键 = 删掉最近的一个（计数 -1）；
* 【重新检测】回到自动检测的峰位；
* 点【导出 PNG】之后，输出目录里才出现 叠加图_N条.png。
"""
import os
import re
import sys
import tempfile
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


def wtext(w, root):
    """取控件当前显示的文案：优先读 textvariable 的当前值。"""
    try:
        name = str(w.cget("textvariable"))
    except Exception:
        name = ""
    if name:
        try:
            return str(root.getvar(name))
        except Exception:
            return ""
    try:
        return str(w.cget("text"))
    except Exception:
        return ""


def find_text(root, needle):
    for w in walk(root):
        t = wtext(w, root)
        if t and needle in t:
            return w, t
    return None, ""


def mark_count(root):
    """从提示行里抠出“当前标注 N 个峰位”的 N。"""
    _w, t = find_text(root, "当前标注")
    m = re.search(r"当前标注\s*(\d+)\s*个峰位", t)
    return int(m.group(1)) if m else None


def mainloop(self):
    app = self
    app.update()

    lib = os.path.join(ROOT, "工具数据", "参考谱库")
    if not os.path.isdir(lib):
        check("参考谱库存在", False, lib)
        app.destroy()
        return
    names = sorted(n for n in os.listdir(lib) if n.lower().endswith(".csv"))[:3]
    if len(names) < 3:
        check("参考谱库至少 3 条", False, "只有 %d 条" % len(names))
        app.destroy()
        return
    paths = [os.path.join(lib, n) for n in names]

    outdir = os.path.join(tempfile.gettempdir(), "_raman_preview_out")
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        try:
            os.remove(os.path.join(outdir, f))
        except OSError:
            pass
    app.same_dir.set(False)
    app.dir_var.set(outdir)

    app.files = list(paths)
    app.listbox.delete(0, "end")
    for n in names:
        app.listbox.insert("end", n)
    app.listbox.selection_set(0, "end")
    app.update()

    tmp_png = os.path.join(tempfile.gettempdir(), "_raman_overlay_preview.png")
    if os.path.isfile(tmp_png):
        os.remove(tmp_png)

    # ---------- 1) 打开预览窗口 ----------
    before = {id(w) for w in app.winfo_children() if isinstance(w, tk.Toplevel)}
    app.tool_overlay()
    app.update()
    new = [w for w in app.winfo_children()
           if isinstance(w, tk.Toplevel) and id(w) not in before]
    check("叠加图预览窗口已打开", bool(new), "新窗口 %d 个" % len(new))
    if not new:
        app.destroy()
        return
    dlg = new[-1]
    for _ in range(10):
        dlg.update_idletasks()
        app.update()

    cvs = [w for w in walk(dlg) if w.winfo_class() == "Canvas"]
    check("预览窗口里有画布", bool(cvs), "找到 %d 个" % len(cvs))
    if not cvs:
        dlg.destroy()
        app.destroy()
        return
    cv = cvs[0]
    cv.update_idletasks()
    app.update()

    # ---------- 2) 只是预览：不能往输出目录写东西 ----------
    check("预览图写在临时目录", os.path.isfile(tmp_png), tmp_png)
    check("打开预览时输出目录仍然是空的（未确认不导出）",
          not os.listdir(outdir), str(os.listdir(outdir)))
    check("画布上确实画了图", len(cv.find_all()) > 0, "item=%d" % len(cv.find_all()))

    # ---------- 3) 窗口和按钮都在屏幕内 ----------
    sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
    dlg.update_idletasks()
    check("预览窗口不超出屏幕高度", dlg.winfo_height() <= sh,
          "h=%d 屏幕=%d" % (dlg.winfo_height(), sh))

    btns = {}
    for w in walk(dlg):
        try:
            if w.winfo_class() == "TButton":
                btns[str(w.cget("text"))] = w
        except Exception:
            continue
    for name in ("导出 PNG", "重新检测", "关闭"):
        check("按钮【%s】存在" % name, name in btns, str(sorted(btns)))
    if "导出 PNG" not in btns:
        dlg.destroy()
        app.destroy()
        return
    b = btns["导出 PNG"]
    b.update_idletasks()
    check("【导出 PNG】按钮在屏幕内",
          0 <= b.winfo_rooty() and b.winfo_rooty() + b.winfo_height() <= sh,
          "y=%d h=%d" % (b.winfo_rooty(), b.winfo_height()))

    # ---------- 4) 初始为自动检测的峰位 ----------
    n0 = mark_count(dlg)
    check("提示行显示自动检测到的峰位数", n0 is not None and n0 > 0,
          "n0=%s" % n0)
    if not n0:
        dlg.destroy()
        app.destroy()
        return

    # ---------- 5) 左键加峰位 ----------
    w, h = cv.winfo_width(), cv.winfo_height()
    added = None
    for xf in (0.30, 0.38, 0.46, 0.54, 0.62, 0.70, 0.78):
        px, py = int(w * xf), int(h * 0.5)
        cv.event_generate("<Button-1>", x=px, y=py)
        app.update()
        n1 = mark_count(dlg)
        if n1 is not None and n1 == n0 + 1:
            added = (px, py)
            break
    check("左键点图能手动加一个峰位（计数 +1）", added is not None,
          "加在 %s，峰位数 %s" % (added, mark_count(dlg)))

    # ---------- 6) 右键删掉刚加的峰位 ----------
    if added is not None:
        cv.event_generate("<Button-3>", x=added[0], y=added[1])
        app.update()
        n2 = mark_count(dlg)
        check("右键点虚线能删掉最近的峰位（计数 -1）", n2 == n0,
              "加后 %s → 删后 %s（原 %s）" % (n0 + 1, n2, n0))
    else:
        check("右键点虚线能删掉最近的峰位（计数 -1）", False, "上一步没加成")

    # ---------- 7) 重新检测 = 回到自动峰位 ----------
    if added is not None:
        cv.event_generate("<Button-1>", x=added[0], y=added[1])
        app.update()
        check("再加一个峰位，计数再次 +1", mark_count(dlg) == n0 + 1,
              "得 %s" % mark_count(dlg))
        btns["重新检测"].invoke()
        app.update()
        check("点【重新检测】回到自动检测的峰位", mark_count(dlg) == n0,
              "得 %s，期望 %s" % (mark_count(dlg), n0))

    # ---------- 8) 确认后才导出 ----------
    check("还没点导出，输出目录依然为空", not os.listdir(outdir),
          str(os.listdir(outdir)))
    btns["导出 PNG"].invoke()
    app.update()
    made = [f for f in os.listdir(outdir) if f.startswith("叠加图_")
            and f.endswith(".png")]
    check("点【导出 PNG】后输出目录出现叠加图", len(made) == 1, str(made))
    if made:
        p = os.path.join(outdir, made[0])
        check("导出的 PNG 不是空文件", os.path.getsize(p) > 10000,
              "%d B" % os.path.getsize(p))

    # ---------- 9) 关闭 ----------
    try:
        btns["关闭"].invoke()
        app.update()
        check("点【关闭】能正常关掉预览窗口", True, "")
    except Exception as exc:
        check("点【关闭】能正常关掉预览窗口", False, str(exc))

    for f in os.listdir(outdir):
        try:
            os.remove(os.path.join(outdir, f))
        except OSError:
            pass
    try:
        os.rmdir(outdir)
    except OSError:
        pass
    for w in new:
        try:
            w.destroy()
        except Exception:
            pass
    app.update()
    app.destroy()


tk.Tk.mainloop = mainloop
T._run_gui()

print()
print("叠加图交互式预览自测：通过 %d 项，失败 %d 项" % (ok[0], ok[1]))
sys.exit(1 if ok[1] else 0)
