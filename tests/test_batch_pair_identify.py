# -*- coding: utf-8 -*-
"""批量配对 / 批量鉴定 自测。

分两段：
  一、无界面的逻辑：自配满分、异类低分、可疑的排最前、汇总表列数对齐、
      CSV / HTML 落盘、英文模式无中文残留；
  二、真的开一次窗口：两个对话框能打开、不超出屏幕、按钮与结果表都在。
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jws2csv as T

LIB = os.path.join(ROOT, "工具数据", "参考谱库")
CJK = re.compile(r"[\u4e00-\u9fff]")

ok = [0, 0]


def check(label, cond, extra=""):
    ok[0 if cond else 1] += 1
    print("  [%s] %s %s" % ("OK" if cond else "FAIL", label, extra))


def lib_names():
    return sorted(n for n in os.listdir(LIB) if n.lower().endswith(".csv"))


def load(*names):
    return T.load_reference_set([os.path.join(LIB, n) for n in names])


def part_one():
    names = lib_names()
    check("参考谱库至少 10 条", len(names) >= 10, "%d 条" % len(names))
    if len(names) < 10:
        return
    plot = dict(T._PLOT_DEFAULT)
    refs = load(*names)
    targets = load(*names[:4])

    # ---------- 1) 自己配自己必须满分 ----------
    rows = T.batch_pair(targets, refs, plot)
    hits = [r for r in rows if r["best"] and r["best"]["name"] == r["name"]]
    check("每条谱的最佳参考都是它自己", len(hits) == len(targets),
          "%d/%d" % (len(hits), len(targets)))
    rich = [r for r in rows if r["n_peaks"] >= 2]
    thin = [r for r in rows if r["n_peaks"] < 2]
    check("峰数 ≥2 的谱：自己配自己综合分 100",
          bool(rich) and all(r["best"]["score"] == 100.0 for r in rich),
          str([round(r["best"]["score"], 1) for r in rich]))
    check("峰数 ≥2 的谱：自己配自己 F1 100",
          bool(rich) and all(r["best"]["f1"] == 100.0 for r in rich),
          str([round(r["best"]["f1"], 1) for r in rich]))
    # 只识别到 1 个峰时 F1 一律记 0（命中<2），综合分因此封顶 50。
    # 这是刻意的：单个峰不足以定案，宁可判它“部分匹配”让人工去看。
    check("只识别到 1 个峰的谱：F1 记 0、综合分不高于 50（单峰定不了案）",
          all(r["best"]["f1"] == 0.0 and r["best"]["score"] <= 50.0 for r in thin),
          "这类谱 %d 条 %s" % (len(thin), [round(r["best"]["score"], 1) for r in thin]))

    # ---------- 2) 异类必须低分（锆石谱 × 非锆石参考）----------
    zircon = [n for n in names if "zircon" in n.lower()]
    other = [n for n in names if "zircon" not in n.lower()]
    check("库里有锆石族与其它矿物", bool(zircon) and len(other) >= 5,
          "锆石 %d 条 / 其它 %d 条" % (len(zircon), len(other)))
    zrows = T.batch_pair(load(*zircon), load(*other[:8]), plot)
    scores = [r["best"]["score"] for r in zrows if r["best"]]
    check("拿锆石谱去配非锆石参考，全部低分（<35）",
          bool(scores) and max(scores) < 35.0,
          "最高 %s" % (round(max(scores), 1) if scores else None))
    readings = {T.pair_reading(r["best"]) for r in zrows}
    check("异类配对的判读是「匹配很差」",
          all("匹配很差" in x for x in readings), str(sorted(readings)))

    # ---------- 3) 汇总表：可疑的排最前 ----------
    mixed = T.batch_pair(load(*names[:3]), load(*other[:6]), plot)   # 应该全都不匹配
    keyed = sorted(mixed, key=T._pair_sort_key)
    check("按综合分升序（最可疑的在前）",
          [r["name"] for r in keyed] == sorted(
              [r["name"] for r in mixed],
              key=lambda n: dict((r["name"], r) for r in mixed)[n]["best"]["score"]),
          "前列 %s" % [round(r["best"]["score"], 1) for r in keyed][:4])

    # ---------- 4) 列数对齐 ----------
    good = T.batch_pair_row(rows[0])                     # 有最佳参考
    bad_row = {"name": "x.csv", "n_points": 10, "n_peaks": 0, "best": None,
               "margin": None, "candidates": [], "error": ""}
    check("配对表列数与数据行一致（正常行）",
          len(T.BATCH_PAIR_COLUMNS) == len(good),
          "%d vs %d" % (len(T.BATCH_PAIR_COLUMNS), len(good)))
    check("配对表列数与数据行一致（无匹配行）",
          len(T.BATCH_PAIR_COLUMNS) == len(T.batch_pair_row(bad_row)),
          "%d vs %d" % (len(T.BATCH_PAIR_COLUMNS), len(T.batch_pair_row(bad_row))))
    check("无匹配行也给出说明而不是空白",
          bool(T.batch_pair_row(bad_row)[-1].strip()),
          T.batch_pair_row(bad_row)[-1])

    id_bad = {"name": "x.csv", "n_points": 10, "n_peaks": 0,
              "candidates": [], "verdict": "", "total": 0}
    check("鉴定表列数与数据行一致（无候选行）",
          len(T.BATCH_IDENTIFY_COLUMNS) == len(T.batch_identify_row(id_bad)),
          "%d vs %d" % (len(T.BATCH_IDENTIFY_COLUMNS),
                        len(T.batch_identify_row(id_bad))))

    # ---------- 5) CSV / HTML 落盘 ----------
    out = os.path.join(tempfile.gettempdir(), "_raman_batch_test")
    os.makedirs(out, exist_ok=True)
    csv_path = os.path.join(out, "配对汇总.csv")
    html_path = os.path.join(out, "配对汇总.html")
    T.write_batch_pair_csv(csv_path, mixed, "测试参考集")
    T.write_batch_pair_html(html_path, mixed, "测试参考集")
    check("配对汇总 CSV 已生成", os.path.isfile(csv_path)
          and os.path.getsize(csv_path) > 200, "%d B"
          % (os.path.getsize(csv_path) if os.path.isfile(csv_path) else 0))
    check("配对汇总 HTML 已生成", os.path.isfile(html_path)
          and os.path.getsize(html_path) > 400, "%d B"
          % (os.path.getsize(html_path) if os.path.isfile(html_path) else 0))

    with open(csv_path, encoding="utf-8-sig") as f:
        lines = [ln.rstrip("\n") for ln in f]
    head = [ln for ln in lines if ln.startswith("文件名,")]
    check("CSV 表头与列定义一致",
          bool(head) and head[0].split(",") == list(T.BATCH_PAIR_COLUMNS),
          str(head[0].split(",")[:4]) if head else "没找到表头")
    data = lines[lines.index(head[0]) + 1:] if head else []
    check("CSV 每条谱一行", len(data) == len(mixed),
          "%d 行 / %d 条" % (len(data), len(mixed)))
    check("CSV 里写明了这只是辅助指标",
          any("辅助指标" in ln for ln in lines), "")
    css = [ln.split(",")[4] for ln in data if ln.split(",")[4] not in ("-",)]
    check("CSV 里数据行按综合分升序",
          css == sorted(css, key=float), str(css[:4]))

    # ---------- 6) 英文模式无中文残留 ----------
    T.set_ui_lang("en")
    try:
        en_csv = os.path.join(out, "en.csv")
        en_html = os.path.join(out, "en.html")
        T.write_batch_pair_csv(en_csv, mixed, "TestRefs")
        T.write_batch_pair_html(en_html, mixed, "TestRefs")
        with open(en_csv, encoding="utf-8-sig") as f:
            text = f.read()
        leftover = sorted(set(m for m in CJK.findall(text)))
        check("英文模式：配对汇总 CSV 无中文残留", not leftover, str(leftover))
        check("英文模式：表头是英文",
              "File name" in text and "Advisory reading" in text, "")
        check("英文模式：判读文案是英文",
              T.pair_reading(rows[0]["best"]).startswith("Good match"),
              T.pair_reading(rows[0]["best"]))
        check("英文模式：列名都有译文",
              all(not CJK.search(T.T(c)) for c in T.BATCH_PAIR_COLUMNS
                  + T.BATCH_IDENTIFY_COLUMNS), "")
    finally:
        T.set_ui_lang("zh")

    # ---------- 7) 批量鉴定 ----------
    try:
        keys = T.peak_index_keys()
    except Exception:
        keys = []
    if not keys:
        print("  （跳过批量鉴定：还没有特征索引）")
    else:
        idrows = T.batch_identify(load("Zircon_R050034_785nm.csv"), plot,
                                  keys=keys, top=3)
        check("批量鉴定能返回结果", len(idrows) == 1 and bool(idrows[0]["candidates"]),
              "%d 条候选" % len(idrows[0]["candidates"] if idrows else []))
        if idrows and idrows[0]["candidates"]:
            best = T._best_named(idrows[0]["candidates"])
            check("在库里的谱能定名到自己", bool(best) and best["score"] == 100.0,
                  "%s %.1f" % (best["name"] if best else "-",
                               best["score"] if best else -1))
            check("鉴定表列数与数据行一致",
                  len(T.BATCH_IDENTIFY_COLUMNS) == len(T.batch_identify_row(idrows[0])),
                  "%d vs %d" % (len(T.BATCH_IDENTIFY_COLUMNS),
                                len(T.batch_identify_row(idrows[0]))))
            check("结论文本非空", bool(idrows[0]["verdict"].strip()), "")
            ic = os.path.join(out, "鉴定汇总.csv")
            T.write_batch_identify_csv(ic, idrows, idrows[0]["total"], 3)
            check("鉴定汇总 CSV 已生成", os.path.isfile(ic)
                  and os.path.getsize(ic) > 200, "%d B"
                  % (os.path.getsize(ic) if os.path.isfile(ic) else 0))

    for f in os.listdir(out):
        try:
            os.remove(os.path.join(out, f))
        except OSError:
            pass
    try:
        os.rmdir(out)
    except OSError:
        pass


def part_two():
    """真的开一次窗口：批量配对对话框能打开、能跑、结果进表。"""
    import tkinter as tk
    import tkinter.messagebox as mb
    mb.showinfo = lambda *a, **k: None
    mb.showwarning = lambda *a, **k: None
    mb.showerror = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: False

    out = os.path.join(tempfile.gettempdir(), "_raman_batch_gui")
    os.makedirs(out, exist_ok=True)
    real_results_dir = T.results_dir
    T.results_dir = lambda: out          # 别把测试结果写进用户的 分析结果

    def walk(w, acc=None):
        if acc is None:
            acc = []
        for c in w.winfo_children():
            acc.append(c)
            walk(c, acc)
        return acc

    def mainloop(self):
        app = self
        app.update()
        names = lib_names()[:3]
        app.files = [os.path.join(LIB, n) for n in names]
        app.listbox.delete(0, "end")
        for n in names:
            app.listbox.insert("end", n)
        app.listbox.selection_set(0, "end")
        app.update()

        sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
        for mode, opener, tag in (("pair", "tool_batch_pair", "批量配对"),
                                  ("identify", "tool_batch_identify", "批量鉴定")):
            before = {id(w) for w in app.winfo_children() if isinstance(w, tk.Toplevel)}
            getattr(app, opener)()
            app.update()
            new = [w for w in app.winfo_children()
                   if isinstance(w, tk.Toplevel) and id(w) not in before]
            check("%s 对话框能打开" % tag, bool(new), "%d 个新窗口" % len(new))
            if not new:
                continue
            dlg = new[-1]
            for _ in range(6):
                dlg.update_idletasks()
                app.update()
            check("%s 对话框不超出屏幕" % tag,
                  dlg.winfo_width() <= sw and dlg.winfo_height() <= sh,
                  "%dx%d 屏幕 %dx%d" % (dlg.winfo_width(), dlg.winfo_height(), sw, sh))
            kids = walk(dlg)
            btns = {}
            for w in kids:
                try:
                    if w.winfo_class() == "TButton":
                        btns[str(w.cget("text"))] = w
                except Exception:
                    continue
            check("%s 对话框有【开始批量处理】" % tag,
                  any("批量处理" in k for k in btns), str(sorted(btns)))
            check("%s 对话框有结果表" % tag,
                  any(w.winfo_class() == "Treeview" for w in kids), "")
            if mode == "pair":
                run_btn = [w for k, w in btns.items() if "批量处理" in k]
                if run_btn:
                    run_btn[0].invoke()
                    for _ in range(30):
                        app.update()
                    tree = [w for w in walk(dlg) if w.winfo_class() == "Treeview"]
                    rows = len(tree[0].get_children()) if tree else 0
                    check("点开始后结果表填上了行", rows == 3, "%d 行" % rows)
                    made = [f for f in os.listdir(out) if "批量配对汇总" in f]
                    check("批量配对汇总文件已落盘", len(made) == 2, str(sorted(made)))
            dlg.destroy()
            app.update()

        # 英文模式下重开一次：对话框文案必须跟着变英文
        T.set_ui_lang("en")
        try:
            before = {id(w) for w in app.winfo_children() if isinstance(w, tk.Toplevel)}
            app.tool_batch_pair()
            app.update()
            new = [w for w in app.winfo_children()
                   if isinstance(w, tk.Toplevel) and id(w) not in before]
            if new:
                dlg = new[-1]
                for _ in range(6):
                    dlg.update_idletasks()
                    app.update()
                texts = []
                for w in walk(dlg):
                    try:
                        if w.winfo_class() in ("TButton", "TLabel", "TCheckbutton",
                                               "TRadiobutton", "TEntry"):
                            texts.append(str(w.cget("text")))
                        if w.winfo_class() == "Treeview":
                            texts += [w.heading(c, "text") for c in w.cget("columns")]
                    except Exception:
                        continue
                residue = [t for t in texts if CJK.search(t)]
                check("英文模式：批量配对对话框控件无中文残留", not residue,
                      str(residue[:6]))
                check("英文模式：对话框标题是英文",
                      "Batch" in dlg.title(), dlg.title())
                dlg.destroy()
                app.update()
        finally:
            T.set_ui_lang("zh")
        app.destroy()

    tk.Tk.mainloop = mainloop
    try:
        T._run_gui()
    finally:
        T.results_dir = real_results_dir
        for f in os.listdir(out):
            try:
                os.remove(os.path.join(out, f))
            except OSError:
                pass
        try:
            os.rmdir(out)
        except OSError:
            pass


print("=== 一、批量配对 / 批量鉴定 逻辑 ===")
part_one()
print()
print("=== 二、界面 ===")
try:
    part_two()
except Exception as exc:                                  # 没有显示器就跳过
    print("  （跳过界面自测：%s）" % exc)

print()
print("批量配对 / 批量鉴定自测：通过 %d 项，失败 %d 项" % (ok[0], ok[1]))
sys.exit(1 if ok[1] else 0)
