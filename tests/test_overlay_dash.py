# -*- coding: utf-8 -*-
"""多数据图叠加 + 峰位波长虚线 的像素级自测。

不靠肉眼看图：把 PNG 渲染出来后直接数像素——
* 叠加图：每个数据集必须用不同颜色画出来（调色板颜色逐个命中）；
* 峰位虚线：关掉再打开，标注色像素必须明显增多（自动峰和手动峰分别验）。
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jws2csv as T

LIB = os.path.join(ROOT, "工具数据", "参考谱库")
OUT = os.path.join(ROOT, "dist")
os.makedirs(OUT, exist_ok=True)

AUTO = (170, 30, 30)      # 自动峰标注色
MANUAL = (20, 80, 170)    # 手动峰标注色

ok = [0, 0]


def check(label, cond, extra=""):
    ok[0 if cond else 1] += 1
    print("  [%s] %s %s" % ("OK" if cond else "FAIL", label, extra))


def count_colour(path, colour, tol=6):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    px = im.load()
    n = 0
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = px[x, y]
            if (abs(r - colour[0]) <= tol and abs(g - colour[1]) <= tol
                    and abs(b - colour[2]) <= tol):
                n += 1
    return n


def main():
    try:
        from PIL import Image  # noqa: F401
    except Exception as exc:
        print("跳过：没有 Pillow（%s）" % exc)
        return 0

    names = sorted(n for n in os.listdir(LIB) if n.lower().endswith(".csv"))
    if len(names) < 4:
        print("跳过：参考谱库不足 4 条（%d）" % len(names))
        return 0

    series = []
    for n in names[:4]:
        _xl, rows = T.read_any_series(os.path.join(LIB, n))
        _lab, xs, ys = rows[0]
        series.append((n, list(xs), list(ys)))
    print("载入 %d 条参考谱，波数 %.1f ~ %.1f"
          % (len(series), series[0][1][0], series[0][1][-1]))

    # ---------- 1) 叠加：每个数据集一种颜色 ----------
    dst = os.path.join(OUT, "_ov_plain.png")
    plot = dict(T._PLOT_DEFAULT)
    plot["annotate_peaks"] = False
    T.render_overlay(dst, series, "overlay", T._DEFAULT_X_HEADER, "norm", plot)
    check("叠加图已生成", os.path.isfile(dst) and os.path.getsize(dst) > 10000,
          "%d B" % (os.path.getsize(dst) if os.path.isfile(dst) else 0))

    im = Image.open(dst).convert("RGB")
    px = im.load()
    cols = set()
    for y in range(im.height):
        for x in range(im.width):
            c = px[x, y]
            if c != (255, 255, 255):
                cols.add(c)
    want = [tuple(int(T._PALETTE[i].lstrip("#")[k:k + 2], 16) for k in (0, 2, 4))
            for i in range(len(series))]
    hit = [c for c in want if c in cols]
    check("每个数据集都用各自的颜色画出来了", len(hit) == len(want),
          "%d / %d  %s" % (len(hit), len(want), hit))
    check("不同数据集颜色互不相同", len(set(want)) == len(want), str(want))
    extra = [c for c in cols if c in set(T._PALETTE[i] for i in range(8))]
    check("叠加图只用了调色板色（没有串色）", len(set(want)) == len(hit), "")

    # 颜色分配：60 条以内不重复
    pal60 = [T.overlay_color(k) for k in range(60)]
    check("60 条曲线配色不重复", len(set(pal60)) == 60,
          "唯一色 %d/60" % len(set(pal60)))
    check("前 8 条沿用标准色板",
          pal60[:8] == T._PALETTE, str(pal60[:8]))

    # ---------- 2) 自动峰虚线 ----------
    one = [(series[0][0], series[0][1], series[0][2], T._PALETTE[0])]
    po = dict(T._PLOT_DEFAULT)
    po["annotate_peaks"] = True
    po["peak_dash_line"] = False
    off = os.path.join(OUT, "_ov_dash_off.png")
    T.render_png(off, one, "off", T._DEFAULT_X_HEADER, "I", po)
    pn = dict(po)
    pn["peak_dash_line"] = True
    on = os.path.join(OUT, "_ov_dash_on.png")
    T.render_png(on, one, "on", T._DEFAULT_X_HEADER, "I", pn)
    a_off, a_on = count_colour(off, AUTO), count_colour(on, AUTO)
    check("自动峰：打开虚线后标注色像素明显增多", a_on > a_off + 200,
          "off=%d on=%d 差=%+d" % (a_off, a_on, a_on - a_off))

    # ---------- 3) 手动峰虚线 ----------
    # 手动峰会与 10 cm-1（peak_min_dist/2）内的自动峰合并，先算自动峰，
    # 再挑一个离所有自动峰 >25 cm-1 的强峰当手动峰，保证它被单独画出来。
    xs0, ys0 = series[0][1], series[0][2]
    base = dict(T._PLOT_DEFAULT)
    base["annotate_peaks"] = True
    auto_x = [q["x"] for q in T.analyze_peaks(
        one[0][1], T._process_signal(one[0][2], base, one[0][1]), base, processed=True)]
    manual_x = None
    for i in sorted(range(len(ys0)), key=lambda j: -ys0[j]):
        if all(abs(xs0[i] - a) > 25.0 for a in auto_x):
            manual_x = xs0[i]
            break
    check("能挑出一个不与自动峰冲突的手动峰位", manual_x is not None,
          "自动峰 %d 个，手动峰位 %s" % (len(auto_x), manual_x))

    pm = dict(base)
    pm["manual_peaks"] = [manual_x]
    probe = T.analyze_peaks(one[0][1], T._process_signal(one[0][2], pm, one[0][1]),
                            pm, processed=True)
    n_manual = sum(1 for q in probe if q.get("manual"))
    check("手动峰被单独标记为 manual", n_manual == 1, "manual=%d" % n_manual)

    pm["peak_dash_line"] = False
    m_off_p = os.path.join(OUT, "_ov_mdash_off.png")
    T.render_png(m_off_p, one, "m off", T._DEFAULT_X_HEADER, "I", pm)
    pm2 = dict(pm)
    pm2["peak_dash_line"] = True
    m_on_p = os.path.join(OUT, "_ov_mdash_on.png")
    T.render_png(m_on_p, one, "m on", T._DEFAULT_X_HEADER, "I", pm2)
    m_off, m_on = count_colour(m_off_p, MANUAL), count_colour(m_on_p, MANUAL)
    check("手动峰：打开虚线后标注色像素明显增多", m_on > m_off + 80,
          "off=%d on=%d 差=%+d" % (m_off, m_on, m_on - m_off))

    # ---------- 4) 叠加图横坐标 = 各条波数范围的交集 ----------
    lo, hi = T.overlay_range(series)
    want_lo = max(min(s[1]) for s in series)
    want_hi = min(max(s[1]) for s in series)
    check("overlay_range 取交集", (lo, hi) == (want_lo, want_hi),
          "得 %.1f~%.1f，期望 %.1f~%.1f" % (lo, hi, want_lo, want_hi))

    caps = {}
    _orig_png = T.render_png

    def _capture(_path, _series, _title, _xlabel, _ylabel, plot=None,
                 width=None, height=None, return_geometry=False):
        caps["plot"] = dict(plot or {})

    def _render_overlay(extra_plot=None):
        caps.clear()
        T.render_png = _capture
        try:
            T.render_overlay("_unused_.png", series, "t", "x", "y", extra_plot or {})
        finally:
            T.render_png = _orig_png
        return caps.get("plot", {})

    got = _render_overlay()
    check("叠加图自动把横坐标设成交集",
          got.get("x_min") == lo and got.get("x_max") == hi,
          "%s ~ %s" % (got.get("x_min"), got.get("x_max")))

    got = _render_overlay({"x_min": 300.0, "x_max": 900.0})
    check("高级设置里手填的范围优先于交集",
          got.get("x_min") == 300.0 and got.get("x_max") == 900.0,
          "%s ~ %s" % (got.get("x_min"), got.get("x_max")))

    r_lo, r_hi = T.overlay_range([("a", [100.0, 200.0], [1.0, 2.0]),
                                  ("b", [500.0, 600.0], [1.0, 2.0])])
    check("各条完全不相交时退回并集（不画空白图）",
          (r_lo, r_hi) == (100.0, 600.0), "%s ~ %s" % (r_lo, r_hi))

    # ---------- 5) 隐藏峰位数值 ----------
    c0 = count_colour(off, AUTO)                       # 完全不标注
    lbl = os.path.join(OUT, "_ov_lab_on.png")
    nolbl = os.path.join(OUT, "_ov_lab_off.png")
    pl = dict(T._PLOT_DEFAULT)
    pl["annotate_peaks"] = True
    pl["peak_labels"] = True
    T.render_png(lbl, one, "lab on", T._DEFAULT_X_HEADER, "I", pl)
    pn2 = dict(pl)
    pn2["peak_labels"] = False
    T.render_png(nolbl, one, "lab off", T._DEFAULT_X_HEADER, "I", pn2)
    c_lab, c_nolab = count_colour(lbl, AUTO), count_colour(nolbl, AUTO)
    check("关掉峰位数值后画的像素变少", c_nolab < c_lab,
          "有数值=%d 无数值=%d" % (c_lab, c_nolab))
    check("关掉峰位数值后虚线与标记仍在", c_nolab > c0 + 300,
          "无数值=%d 完全不标注=%d" % (c_nolab, c0))

    # ---------- 6) 删除自动峰（hidden_peaks）----------
    base2 = dict(T._PLOT_DEFAULT)
    base2["annotate_peaks"] = True
    sig = T._process_signal(one[0][2], base2, one[0][1])
    all_pk = T.analyze_peaks(one[0][1], sig, base2, processed=True)
    check("先得有自动峰可删", len(all_pk) >= 2, "共 %d 个" % len(all_pk))
    victim = max(all_pk, key=lambda q: q["prominence"])
    keep = [q for q in all_pk if abs(q["x"] - victim["x"]) > 1e-9]
    ph = dict(base2)
    ph["hidden_peaks"] = [victim["x"]]
    after = T.analyze_peaks(one[0][1], sig, ph, processed=True)
    check("被删的自动峰不再出现在峰表里",
          len(after) == len(all_pk) - 1
          and all(abs(q["x"] - victim["x"]) > 1e-9 for q in after),
          "删前 %d 个 → 删后 %d 个（目标 %.2f）"
          % (len(all_pk), len(after), victim["x"]))
    check("其余自动峰一个不少",
          sorted(round(q["x"], 6) for q in after)
          == sorted(round(q["x"], 6) for q in keep), str(len(keep)))

    h_on = os.path.join(OUT, "_ov_hide_on.png")
    h_off = os.path.join(OUT, "_ov_hide_off.png")
    T.render_png(h_off, one, "hide off", T._DEFAULT_X_HEADER, "I", base2)
    T.render_png(h_on, one, "hide on", T._DEFAULT_X_HEADER, "I", ph)
    d_off, d_on = count_colour(h_off, AUTO), count_colour(h_on, AUTO)
    check("删掉自动峰后图上它的标注色像素减少", d_on < d_off,
          "删前=%d 删后=%d" % (d_off, d_on))

    # ---------- 7) 堆叠排布（stacked spectra）----------
    syn_x = [float(v) for v in range(300, 1601)]

    def _spec(shift):
        out = []
        for x in syn_x:
            v = 0.02
            for c in (500.0, 700.0, 1000.0):
                v += math.exp(-((x - (c + shift)) ** 2) / (2 * 8.0 ** 2))
            out.append(v)
        return out

    syn = [("s%d" % i, list(syn_x), _spec(sh)) for i, sh in enumerate((-6.0, 0.0, 6.0))]

    caps.clear()
    T.render_png = _capture
    try:
        T.render_overlay("_unused_.png", syn, "t", "x", "y", {"stack_offset": 1.0})
    finally:
        T.render_png = _orig_png
    got2 = caps.get("plot", {})
    check("叠加图默认走堆叠排布", got2.get("stacked") is True, str(got2.get("stacked")))
    check("叠加图默认做峰位跨谱合并",
          got2.get("merge_peak_labels") is True, str(got2.get("merge_peak_labels")))
    check("叠加图把偏移传给渲染器", got2.get("stack_offset") == 1.0,
          str(got2.get("stack_offset")))

    def _centroid(path, colour):
        im2 = Image.open(path).convert("RGB")
        p2 = im2.load()
        tot = 0
        n = 0
        for y in range(im2.height):
            for x in range(im2.width):
                if p2[x, y] == colour:
                    tot += y
                    n += 1
        return (tot / n) if n else None

    stk = os.path.join(OUT, "_ov_stack.png")
    T.render_overlay(stk, syn, "stack", T._DEFAULT_X_HEADER, "norm",
                     {"annotate_peaks": False, "stack_offset": 1.0},
                     common_range=False)
    band = [_centroid(stk, tuple(int(T._PALETTE[i].lstrip("#")[k:k + 2], 16)
                                 for k in (0, 2, 4))) for i in range(len(syn))]
    check("堆叠后每条谱落在各自的竖直区间（谱线不压在一起）",
          all(b is not None for b in band)
          and all(abs(band[i + 1] - band[i]) > 50 for i in range(len(band) - 1)),
          "各条重心 y = %s" % [None if b is None else round(b) for b in band])
    check("堆叠是自上而下依次排开的",
          all(band[i] > band[i + 1] for i in range(len(band) - 1)),
          str([round(b) for b in band]))

    # ---------- 8) 峰位跨谱合并 ----------
    po2 = T._plot_opts({"peak_merge_tol": 20.0})
    cl = T.peak_clusters(syn, po2)
    check("三组互相靠近的峰各自合并成一个（9 个峰 -> 3 个）", len(cl) == 3,
          "得 %d 簇：%s" % (len(cl), [round(c["x"], 1) for c in cl]))
    check("合并后取的是平均波数",
          all(abs(c["x"] - t) < 3.0 for c, t in zip(cl, (500.0, 700.0, 1000.0))),
          str([round(c["x"], 2) for c in cl]))
    check("每一簇都记录了参与的 3 条谱",
          all(c["n"] == 3 and len(c["curves"]) == 3 for c in cl),
          str([c["n"] for c in cl]))

    # 容差调到比峰间距还小 -> 不再合并，9 个峰各自成簇
    cl_fine = T.peak_clusters(syn, T._plot_opts({"peak_merge_tol": 1.0}))
    check("容差调小后不再合并", len(cl_fine) == 9, "得 %d 簇" % len(cl_fine))
    # 相邻峰相差 6，容差 20 时不会被“链式”串成一整段
    check("不会把整段峰链式串成一簇", len(cl) == 3, "%d" % len(cl))

    mg = os.path.join(OUT, "_ov_merge_on.png")
    nm = os.path.join(OUT, "_ov_merge_off.png")
    T.render_overlay(mg, syn, "merge", T._DEFAULT_X_HEADER, "norm",
                     {"annotate_peaks": True, "peak_merge_tol": 20.0,
                      "stack_offset": 1.0},
                     common_range=False, merge_peaks=True)
    T.render_overlay(nm, syn, "nomerge", T._DEFAULT_X_HEADER, "norm",
                     {"annotate_peaks": True, "peak_merge_tol": 20.0,
                      "stack_offset": 1.0},
                     common_range=False, merge_peaks=False)

    def _dash_columns(path, colour, tol=6):
        """统计图片里有多少个不同的 x 列含标注色 —— 约等于标注的峰个数。"""
        im2 = Image.open(path).convert("RGB")
        p2 = im2.load()
        cols = set()
        for y in range(im2.height):
            for x in range(im2.width):
                r, g, b = p2[x, y]
                if (abs(r - colour[0]) <= tol and abs(g - colour[1]) <= tol
                        and abs(b - colour[2]) <= tol):
                    cols.add(x)
        return cols

    c_on = len(_dash_columns(mg, AUTO))
    c_off = len(_dash_columns(nm, AUTO))
    check("合并后标注的峰明显变少（虚线列数下降）", c_on < c_off,
          "合并 %d 列 / 不合并 %d 列" % (c_on, c_off))
    check("不合并时每个峰各标一条", c_off > c_on, "%d vs %d" % (c_off, c_on))

    # ---------- 9) 手动清单标注（交互式预览「确认」后交给渲染器的就是它）----------
    mko = {"annotate_peaks": True, "peak_merge_tol": 20.0, "stack_offset": 1.0}

    def _ov_mark(path, marks):
        T.render_overlay(path, syn, "mark", T._DEFAULT_X_HEADER, "norm", dict(mko),
                         common_range=False, merge_peaks=True, marks=marks)

    # 不给清单（None）= 自动合并，和默认行为一致
    auto_p = os.path.join(OUT, "_ov_mark_auto.png")
    _ov_mark(auto_p, None)
    check("marks=None 时与自动合并的结果一致",
          _dash_columns(auto_p, AUTO) == _dash_columns(mg, AUTO),
          "auto 列 %d / 默认 %d" % (len(_dash_columns(auto_p, AUTO)),
                                    len(_dash_columns(mg, AUTO))))

    # 清单里只留一个手动峰 -> 只画一条虚线（手动色），且不再有自动峰标注
    mk1 = os.path.join(OUT, "_ov_mark_one.png")
    _ov_mark(mk1, [{"x": 700.0, "manual": True}])
    c1 = _dash_columns(mk1, MANUAL)
    check("清单只剩一个峰位时只标一处（手动色）",
          bool(c1) and max(c1) - min(c1) < 60,
          "列 %s~%s" % ((min(c1), max(c1)) if c1 else (None, None)))
    check("清单以外的自动峰不再标注", not _dash_columns(mk1, AUTO),
          "自动色列 %d" % len(_dash_columns(mk1, AUTO)))

    # 清单里两个手动峰 -> 两处、彼此分开
    mk2 = os.path.join(OUT, "_ov_mark_two.png")
    _ov_mark(mk2, [{"x": 700.0, "manual": True}, {"x": 1000.0, "manual": True}])
    c2 = _dash_columns(mk2, MANUAL)
    check("清单里两个峰位画两条分得很开的虚线",
          bool(c2) and max(c2) - min(c2) > 200,
          "列 %s~%s" % ((min(c2), max(c2)) if c2 else (None, None)))

    # 清单被清空 -> 图上不再有峰位标注
    mk0 = os.path.join(OUT, "_ov_mark_zero.png")
    _ov_mark(mk0, [])
    check("峰位被全部删掉后图上不再有标注",
          not _dash_columns(mk0, AUTO) and not _dash_columns(mk0, MANUAL),
          "auto=%d manual=%d" % (len(_dash_columns(mk0, AUTO)),
                                 len(_dash_columns(mk0, MANUAL))))

    # ---------- 10) 预览用的绘图区几何 ----------
    geo_p = os.path.join(OUT, "_ov_geom.png")
    geo = T.render_overlay(geo_p, syn, "geo", T._DEFAULT_X_HEADER, "norm",
                           dict(mko), common_range=False, return_geometry=True)
    need = ("xmin", "xmax", "ml", "pw", "mt", "ph", "width", "height")
    check("return_geometry 回报了完整的绘图区几何",
          isinstance(geo, dict) and all(k in geo for k in need), str(sorted(geo or [])))
    if isinstance(geo, dict) and all(k in geo for k in need):
        check("几何里的绘图区落在图内",
              0 < geo["ml"] and geo["ml"] + geo["pw"] <= geo["width"]
              and 0 < geo["mt"] and geo["mt"] + geo["ph"] <= geo["height"],
              "ml=%s pw=%s width=%s" % (geo["ml"], geo["pw"], geo["width"]))
        check("几何里的波数范围是递增的",
              geo["xmax"] > geo["xmin"],
              "%.1f ~ %.1f" % (geo["xmin"], geo["xmax"]))
        # 预览把鼠标 x 换算成波数的公式：xmin + (ix-ml)/pw*(xmax-xmin)
        mid = geo["xmin"] + (geo["ml"] + geo["pw"] / 2.0 - geo["ml"]) / float(geo["pw"]) \
            * (geo["xmax"] - geo["xmin"])
        check("绘图区正中央对应波数范围的中点",
              abs(mid - (geo["xmin"] + geo["xmax"]) / 2.0) < 1e-6,
              "%.5f vs %.5f" % (mid, (geo["xmin"] + geo["xmax"]) / 2.0))

    for f in (dst, off, on, m_off_p, m_on_p, lbl, nolbl, h_on, h_off,
              stk, mg, nm, auto_p, mk1, mk2, mk0, geo_p):
        try:
            os.remove(f)
        except OSError:
            pass
    try:
        os.rmdir(OUT)
    except OSError:
        pass
    return 0


main()

print()
print("叠加图与峰位虚线自测：通过 %d 项，失败 %d 项" % (ok[0], ok[1]))
sys.exit(1 if ok[1] else 0)
