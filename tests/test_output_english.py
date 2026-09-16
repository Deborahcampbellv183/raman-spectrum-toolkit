# -*- coding: utf-8 -*-
"""英文输出自测：EN 模式下生成报告 / 峰表 / 鉴定表 / 各类 PNG，检查产物里是否还有中文。"""
import contextlib
import io
import math
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jws2csv as T

CJK = re.compile(r"[\u4e00-\u9fff]")
ALLOW = ("工具数据", "参考谱库", "RRUFF数据包", "分析结果", "光谱数据库",
         "转换结果", "批处理汇总", "未知光谱检索", "配对报告", "分析报告",
         "主峰", "光谱转换", "使用说明", "光谱分析报告", "报告图",
         "相似度矩阵", "平均光谱", "相减_A减", "数据库比对")

ok = [0, 0]


def check(label, cond, extra=""):
    ok[0 if cond else 1] += 1
    print("  [%s] %s %s" % ("OK" if cond else "FAIL", label, extra))


def scan_text(name, text):
    bad = []
    for ln in text.splitlines():
        probe = re.sub(r"[A-Za-z]:\\[^\s,;\"]*", "<path>", ln)
        if CJK.search(probe) and not any(a in probe for a in ALLOW):
            bad.append(probe[:80])
    check("%s 无中文残留" % name, not bad, "残留 %d 处：%s" % (len(bad), bad[:4]))


def synth(n=4):
    out = []
    for i in range(n):
        xs = list(range(300, 1601))
        ys = []
        for k in xs:
            y = 0.0
            for c in (420, 640, 1008, 1200):
                y += (10 + i * 2) * math.exp(-((k - (c + i * 3)) ** 2) / (2 * 12.0 ** 2))
            y += 1.5 + 0.5 * math.sin(k / 50.0)
            ys.append(y)
        out.append(("synth_%d.csv" % (i + 1), xs, ys))
    return out


d = os.path.join(tempfile.gettempdir(), "_en_out")
os.makedirs(d, exist_ok=True)
data = synth()
paths = []
for name, xs, ys in data:
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        f.write("Wavenumber,Intensity\n")
        for x, y in zip(xs, ys):
            f.write("%d,%.4f\n" % (x, y))
    paths.append(p)

T.set_ui_lang("en", persist=False, apply_now=False)

# 1) HTML 分析报告
try:
    rep = os.path.join(d, "report.html")
    T.build_report(paths, rep, verbose=False)
    html = open(rep, encoding="utf-8").read()
    body = re.sub(r"data:image/png;base64,[^\"']+", "<img>", html)
    body = re.sub(r"<style>.*?</style>", "", body, flags=re.S)
    scan_text("HTML 报告", body)
except Exception as exc:
    check("HTML 报告 生成", False, repr(exc)[:110])

# 2) 峰表 CSV
try:
    csvp = os.path.join(d, "peaks.csv")
    T.write_peaks_table(csvp, data[0][1], data[0][2], {"mineral_name": "Zircon"})
    scan_text("峰表 CSV", open(csvp, encoding="utf-8-sig").read())
except Exception as exc:
    check("峰表 CSV 生成", False, repr(exc)[:110])

# 3) 鉴定表 CSV + 命令行表
try:
    rows, total, verdict = T.identify_unknown((data[0][1], data[0][2]), top=5)
    csvp = os.path.join(d, "ident.csv")
    T.write_identify_csv(csvp, "synth_1.csv", rows, verdict=verdict, total=total)
    scan_text("鉴定表 CSV", open(csvp, encoding="utf-8-sig").read())
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        T.print_identify_table(rows)
    scan_text("鉴定表 命令行", buf.getvalue())
except Exception as exc:
    check("鉴定表 生成", False, repr(exc)[:110])

# 4) 各类 PNG（图内文字无法直接扫描，主要确认不报错）
try:
    res = T.cluster_spectra(data)
    T.render_dendrogram(os.path.join(d, "d.png"), res["names"], res["merges"],
                        title=T.T("聚类树状图"), cut=res["cut"], groups=res["labels"])
    pts = [(s[0], s[1]) for s in res["scores"]]
    T.render_scatter(os.path.join(d, "s.png"), pts, title="PCA", groups=res["labels"])
    T.render_heatmap(os.path.join(d, "h.png"), [[1.0, 2.0], [3.0, None]], title="Map",
                     cbar_label=T.T("主峰位(cm-1)"))
    T.render_waterfall(os.path.join(d, "w.png"), data, title="Waterfall")
    T.render_png(os.path.join(d, "p.png"),
                 [(n, xs, ys, T._PALETTE[0]) for n, xs, ys in data],
                 "Sample", T._DEFAULT_X_HEADER, "Intensity", {})
    check("聚类 / 散点 / 热图 / 瀑布 / 光谱 出图", True, "")
except Exception as exc:
    check("聚类 / 散点 / 热图 / 瀑布 / 光谱 出图", False, repr(exc)[:130])

miss = [m for m in T.i18n_missing() if CJK.search(m) and not any(a in m for a in ALLOW)]
print()
print("== 未收录（查不到译文）的中文文案：%d 条 ==" % len(miss))
for m in miss[:30]:
    print("   %s" % m[:80])
print()
print("英文输出自测：通过 %d 项，失败 %d 项" % (ok[0], ok[1]))
sys.exit(1 if ok[1] else 0)
