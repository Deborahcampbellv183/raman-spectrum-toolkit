# -*- coding: utf-8 -*-
"""英文界面覆盖率自测：把所有对话框在 EN 模式下打开，检查控件文案是否还有中文。"""
import math
import os
import re
import sys
import tempfile
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as mb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jws2csv as T

CJK = re.compile(r"[\u4e00-\u9fff]")
PATH_RX = re.compile(r"[A-Za-z]:\\[^\s\"']*")
CSVDUMMY = os.path.join(T.results_dir(), "_en_probe.csv")

mb.showinfo = lambda *a, **k: None
mb.showwarning = lambda *a, **k: None
mb.showerror = lambda *a, **k: None
mb.askyesno = lambda *a, **k: False
fd.asksaveasfilename = lambda *a, **k: CSVDUMMY

ok = [0, 0]
residue = {}
ALLOW = ("工具数据", "参考谱库", "RRUFF数据包", "分析结果", "光谱数据库",
         "转换结果", "批处理汇总", "未知光谱检索", "配对报告", "分析报告",
         "主峰", "光谱转换", "使用说明", "光谱分析报告",
         "相似度矩阵", "平均光谱", "相减_A减", "数据库比对")


def _make_synth(n=4):
    """造几条带高斯峰的合成光谱 CSV，供需要多条光谱的工具使用。"""
    d = os.path.join(tempfile.gettempdir(), "_en_synth")
    if not os.path.isdir(d):
        os.makedirs(d)
    paths = []
    for i in range(n):
        path = os.path.join(d, "synth_%d.csv" % (i + 1))
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write("Wavenumber,Intensity\n")
                for k in range(300, 1601):
                    y = 0.0
                    for c in (420, 640, 1008, 1200):
                        y += (10 + i * 2) * math.exp(-((k - (c + i * 3)) ** 2) / (2 * 12.0 ** 2))
                    y += 1.5 + 0.5 * math.sin(k / 50.0)
                    f.write("%d,%.4f\n" % (k, y))
        paths.append(path)
    return tuple(paths)


SYNTH = _make_synth()


def check(label, cond, extra=""):
    ok[0 if cond else 1] += 1
    print("  [%s] %s %s" % ("OK" if cond else "FAIL", label, extra))


def walk(w, out, seen):
    for c in w.winfo_children():
        if id(c) not in seen:
            seen.add(id(c))
            out.append(c)
        walk(c, out, seen)


def widget_texts(win):
    """收集窗口里所有“控件自带文案”（不含数据行）。"""
    texts = []
    for w in [win] + collect(win):
        cls = None
        try:
            cls = w.winfo_class()
        except Exception:
            continue
        try:
            if cls in ("TLabel", "TButton", "TCheckbutton", "TRadiobutton",
                       "TLabelFrame", "TLabelframe", "Label", "Button",
                       "Checkbutton", "Radiobutton", "LabelFrame"):
                t = str(w.cget("text"))
                if t:
                    texts.append((cls, t))
            elif cls == "Treeview":
                for col in str(w.cget("columns")).split():
                    h = str(w.heading(col, "text"))
                    if h:
                        texts.append(("heading", h))
            elif cls == "TCombobox":
                for v in list(w.cget("values")):
                    if str(v).strip():
                        texts.append(("combo", str(v)))
        except Exception:
            continue
    return texts


def collect(w, out=None, seen=None):
    if out is None:
        out, seen = [], set()
    walk(w, out, seen)
    return out


def menu_labels(menu, out=None):
    if out is None:
        out = []
    try:
        end = menu.index("end")
    except Exception:
        return out
    if end is None:
        return out
    for i in range(end + 1):
        try:
            if str(menu.type(i)) == "separator":
                continue
            lab = menu.entrycget(i, "label")
        except Exception:
            lab = ""
        if lab:
            out.append(lab)
        try:
            sub = menu.entrycget(i, "menu")
        except Exception:
            sub = ""
        if sub:
            try:
                menu_labels(menu.nametowidget(sub), out)
            except Exception:
                pass
    return out


def scan(name, win):
    bad = []
    for cls, text in widget_texts(win):
        probe = PATH_RX.sub("<path>", text)
        if CJK.search(probe) and not any(a in probe for a in ALLOW):
            bad.append("%s: %s" % (cls, probe[:60]))
    if bad:
        residue[name] = bad
    return bad


def fake_mainloop(self):
    app = self
    app.update()
    T.set_ui_lang("en", persist=False, apply_now=True)
    app.update()
    check("主窗口切到英文", T.ui_lang() == "en")

    bad = scan("主窗口", app)
    check("主窗口控件无中文残留", not bad, "残留 %d 处：%s" % (len(bad), bad[:4]))
    ntitle = app.title()
    check("主窗口标题已翻译", not CJK.search(ntitle), repr(ntitle))

    labels = menu_labels(app.nametowidget(app.cget("menu")))
    badm = [l for l in labels if CJK.search(l) and not any(a in l for a in ALLOW)]
    check("菜单无中文残留", not badm, "残留 %d 处：%s" % (len(badm), badm[:6]))
    check("菜单已翻译（示例）",
          "Settings" in labels and "Analysis" in labels and "Database" in labels,
          str([l for l in labels if l in ("设置", "分析工具", "数据库", "Settings")]))

    fd.askopenfilenames = lambda *a, **k: SYNTH
    fd.askopenfilename = lambda *a, **k: SYNTH[0]
    fd.askdirectory = lambda *a, **k: os.path.dirname(SYNTH[0])
    import tkinter.simpledialog as _sd
    _sd.askstring = lambda *a, **k: ""
    app.add_files()
    app.update()
    if app.files:
        app.listbox.selection_clear(0, "end")
        for i in range(len(app.files)):
            app.listbox.selection_set(i)
        app.update()
    check("已载入多条光谱（供多谱工具使用）", len(app.files) >= 4, "共 %d 条" % len(app.files))

    dialogs = [
        ("高级设置", lambda: app.open_advanced()),
        ("数据文件夹", lambda: app.open_data_manager()),
        ("使用说明书", lambda: app.open_manual()),
        ("矿物信息", lambda: app.open_mineral_info()),
        ("未知光谱鉴定", lambda: app.open_identify()),
        ("数据库检索", lambda: app.open_db_search()),
        ("RRUFF 数据源", lambda: app.open_rruff()),
        ("批处理", lambda: app.open_batch()),
        ("聚类分析", lambda: app.tool_cluster()),
        ("二维成像", lambda: app.tool_map()),
        ("谱段替换", lambda: app.tool_replace()),
        ("交互式相减", lambda: app.tool_subtract_interactive()),
        ("多数据图叠加", lambda: app.tool_overlay()),
    ]
    actions = [
        ("配对比较", lambda: app.tool_pair_manual()),
        ("峰拟合", lambda: app.tool_fit()),
        ("峰位检索", lambda: app.tool_search()),
        ("相似度矩阵", lambda: app.tool_similarity()),
        ("光谱比对", lambda: app.tool_match()),
    ]
    for name, opener in dialogs:
        before = {id(w) for w in app.winfo_children() if isinstance(w, tk.Toplevel)}
        try:
            opener()
            app.update()
            new = [w for w in app.winfo_children()
                   if isinstance(w, tk.Toplevel) and id(w) not in before]
            if not new:
                check("%s 打开" % name, False, "没有新窗口")
                continue
            win = new[-1]
            win.update()
            bad = scan(name, win)
            check("%s 控件无中文残留" % name, not bad,
                  "残留 %d 处：%s" % (len(bad), bad[:4]))
            for w in new:
                w.destroy()
            app.update()
        except Exception as exc:
            check("%s 打开" % name, False, repr(exc)[:90])

    for name, runner in actions:
        app.log.configure(state="normal")
        app.log.delete("1.0", "end")
        app.log.configure(state="disabled")
        try:
            runner()
            app.update()
        except Exception as exc:
            check("%s 执行" % name, False, repr(exc)[:90])
            continue
        app.log.configure(state="normal")
        lines = app.log.get("1.0", "end").splitlines()
        app.log.configure(state="disabled")
        bad = []
        for ln in lines:
            probe = PATH_RX.sub("<path>", ln)
            if CJK.search(probe) and not any(a in probe for a in ALLOW):
                bad.append(probe[:60])
        residue[name] = bad
        check("%s 日志无中文残留" % name, not bad,
              "残留 %d 处：%s" % (len(bad), bad[:4]))

    # 多数据图叠加：先开预览窗口 → 点“Export PNG”确认导出 → 确认 PNG 真的落盘
    before = {id(w) for w in app.winfo_children() if isinstance(w, tk.Toplevel)}
    app.log.configure(state="normal")
    app.log.delete("1.0", "end")
    app.log.configure(state="disabled")
    try:
        app.tool_overlay()
        app.update()
        new = [w for w in app.winfo_children()
               if isinstance(w, tk.Toplevel) and id(w) not in before]
        if not new:
            check("叠加图对话框 打开", False, "没有新窗口")
        else:
            dlg = new[-1]
            dlg.update()
            btns = [w for w in collect(dlg) if w.winfo_class() == "TButton"]
            labels = [str(w.cget("text")) for w in btns]
            hit = [w for w in btns if str(w.cget("text")) == "Export PNG"]
            check("叠加图对话框有导出按钮", bool(hit), str(labels))
            if hit:
                hit[0].invoke()
                app.update()
            app.log.configure(state="normal")
            lines = app.log.get("1.0", "end").splitlines()
            app.log.configure(state="disabled")
            names = []
            for ln in lines:
                ln = ln.strip()
                if ln.startswith("Overlay:") and ":" in ln:
                    nm = ln.split(":", 1)[1].strip()
                    names.append(re.sub(r"\s*\(.*\)$", "", nm))
            path = os.path.join(T.results_dir(), names[-1]) if names else ""
            check("叠加图已导出 PNG",
                  bool(path) and os.path.isfile(path) and os.path.getsize(path) > 10000,
                  path)
    except Exception as exc:
        check("叠加图导出", False, repr(exc)[:90])
    for w in [x for x in app.winfo_children() if isinstance(x, tk.Toplevel)]:
        if id(w) not in before:
            w.destroy()
    app.update()

    # 右键删除自动峰 → 恢复自动峰（界面记账是否正确）
    try:
        app.listbox.selection_clear(0, "end")
        app.listbox.selection_set(0)
        app.update()
        app.preview_selected()
        app.update()
        v = app._view
        key = app._peak_key(app.files[0])
        xs = app._view_series[0][1]
        ys = app._view_series[0][2]
        before_pk = T.analyze_peaks(xs, ys, app.current_plot_options(), processed=True)

        class _E(object):
            pass

        def _at(data_x):
            ev = _E()
            ev.x = int(v["ml"] + (data_x - v["xmin"]) / (v["xmax"] - v["xmin"]) * v["pw"])
            ev.y = int(v["mt"] + v["ph"] * 0.3)
            return ev

        auto = [q for q in before_pk if not q.get("manual")]
        hit = max(auto, key=lambda q: q["prominence"])
        app.hidden_peaks.pop(key, None)
        app.remove_annotated_peak(_at(hit["x"]))
        app.update()
        hidden = list(app.hidden_peaks.get(key, []))
        check("右键删掉一个自动峰", len(hidden) == 1, str(hidden))
        after_pk = T.analyze_peaks(xs, app._view_series[0][2],
                                   app.current_plot_options(), processed=True)
        check("删掉的峰从峰表消失", len(after_pk) == len(before_pk) - 1,
              "%d -> %d" % (len(before_pk), len(after_pk)))

        # 空白处右键不能误删
        span = v["xmax"] - v["xmin"]
        far_x = None
        for frac in (0.02, 0.05, 0.95, 0.98):
            cand = v["xmin"] + span * frac
            if all(abs(cand - q["x"]) > span / 20.0 for q in after_pk):
                far_x = cand
                break
        if far_x is not None:
            app.remove_annotated_peak(_at(far_x))
            app.update()
            check("空白处右键不会误删",
                  len(app.hidden_peaks.get(key, [])) == 1,
                  str(app.hidden_peaks.get(key, [])))

        app.restore_hidden_peaks()
        app.update()
        check("恢复自动峰后名单清空", not app.hidden_peaks.get(key), "")
        restored = T.analyze_peaks(xs, app._view_series[0][2],
                                   app.current_plot_options(), processed=True)
        check("恢复后峰表还原", len(restored) == len(before_pk),
              "%d / %d" % (len(restored), len(before_pk)))
    except Exception as exc:
        check("右键删除 / 恢复自动峰", False, repr(exc)[:90])

    # 关于框走 messagebox，单独抓文本检查
    cap = {}
    _keep_show = mb.showinfo
    mb.showinfo = lambda title=None, message=None, *a, **k: cap.update(
        t=title, m=message)
    try:
        app._about()
    except Exception as exc:
        check("关于框 打开", False, repr(exc)[:90])
    mb.showinfo = _keep_show
    atxt = "%s\n%s" % (T.T(cap.get("t") or ""), cap.get("m") or "")
    abad = [l for l in atxt.splitlines() if CJK.search(l)]
    residue["关于"] = abad
    check("关于框无中文残留", not abad, "残留 %d 处：%s" % (len(abad), abad[:4]))

    # 切回中文应当能恢复（登记表机制）
    T.set_ui_lang("zh", persist=False, apply_now=True)
    app.update()
    zh_back = [t for _c, t in widget_texts(app) if t == "开始转换"]
    check("切回中文后主窗口恢复中文", bool(zh_back), str(zh_back))
    T.set_ui_lang("en", persist=False, apply_now=True)
    app.update()
    en_again = [t for _c, t in widget_texts(app) if t == "Start conversion"]
    check("再切英文仍然正确", bool(en_again), str(en_again))
    app.destroy()


tk.Tk.mainloop = fake_mainloop
T._run_gui()

print()
if residue:
    print("== 残留明细（前 40 条）==")
    shown = 0
    for name, items in residue.items():
        for it in items:
            print("   %-12s %s" % (name, it))
            shown += 1
            if shown >= 40:
                break
        if shown >= 40:
            break
print()
miss = [m for m in T.i18n_missing() if CJK.search(PATH_RX.sub("<path>", m))
        and not any(a in m for a in ALLOW)]
print("== 未收录（查不到译文）的中文文案：%d 条 ==" % len(miss))
for m in miss[:30]:
    print("   %s" % m[:70])
print()
print("英文界面自测：通过 %d 项，失败 %d 项" % (ok[0], ok[1]))
sys.exit(1 if ok[1] else 0)
