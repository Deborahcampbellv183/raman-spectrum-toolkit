# -*- coding: utf-8 -*-
"""用工具自身渲染几张真实示例图，供 README 使用（数据取自随包参考谱库）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jws2csv as T

OUT = os.path.join(ROOT, "docs")
os.makedirs(OUT, exist_ok=True)
LIB = os.path.join(ROOT, "工具数据", "参考谱库")

T.set_ui_lang("en", persist=False, apply_now=False)

# 1) 单条拉曼谱（锆石参考谱）→ 与工具“导出的 PNG”完全一致
src = os.path.join(LIB, "Zircon_R050034_785nm.csv")
xlabel, series = T.read_any_series(src)
xs = series[0][1]
ys = series[0][2]
p = T._plot_opts({"x_step": 200, "show_title": True})
T.render_png(os.path.join(OUT, "example_spectrum.png"),
             [("Zircon (RRUFF R050034, 785 nm)", list(xs), list(ys), T._PALETTE[0])],
             "Zircon  -  Raman spectrum", xlabel or T._DEFAULT_X_HEADER,
             "Intensity", p)
print("example_spectrum.png ok")

# 2) 未知谱鉴定 / 配对对比图（锆石实测 vs 库中最佳匹配）
target = os.path.join(LIB, "Zircon_X050183_514nm.csv"),
_l, tser = T.read_any_series(target[0])
txs, tys = tser[0][1], tser[0][2]
refs = [os.path.join(LIB, n) for n in sorted(os.listdir(LIB))
        if n.endswith(".csv") and "X050183" not in n]
results = T.pair_spectra((txs, tys), refs, p, 5.0, top=20)
if results:
    T.render_pair_report(os.path.join(OUT, "example_pairing.png"),
                         "Zircon_X050183_514nm.csv", (txs, tys), results, p, 5.0)
    print("example_pairing.png ok, best =", results[0]["name"])
else:
    print("pairing produced no results")

# 3) 多数据图叠加（堆叠排布）：几种矿物的参考谱错开排列，峰位跨谱合并只标一个平均值
WANT = ("Zircon_R050034_785nm.csv", "Hematite_1000001_514nm.csv",
        "Gypsum_3500028_514nm.csv", "Dolomite_1000016_514nm.csv")
ov = []
for name in WANT:
    q = os.path.join(LIB, name)
    if not os.path.isfile(q):
        continue
    _l2, s2 = T.read_any_series(q)
    ov.append((name[:-4].replace("_", " "), list(s2[0][1]), list(s2[0][2])))
po = T._plot_opts({"x_step": 200, "peak_merge_tol": 20.0, "stack_offset": 1.0})
po["annotate_peaks"] = True
T.render_overlay(os.path.join(OUT, "example_overlay.png"), ov,
                 "Multi-dataset overlay  -  stacked spectra, peaks merged across datasets",
                 T._DEFAULT_X_HEADER, "Normalized intensity", po)
print("example_overlay.png ok,", len(ov), "curves ->", [c[0] for c in ov])
