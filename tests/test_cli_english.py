# -*- coding: utf-8 -*-
"""英文命令行自测：跑一圈常用 CLI 命令，检查输出里是否还有界面中文。"""
import os
import re
import subprocess
import sys
import tempfile

PY = sys.executable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "jws2csv.py")
CJK = re.compile(r"[\u4e00-\u9fff]")
ALLOW = ("工具数据", "参考谱库", "RRUFF数据包", "分析结果", "光谱数据库",
         "转换结果", "批处理汇总", "未知光谱检索", "配对报告", "分析报告",
         "主峰", "光谱转换", "使用说明", "光谱分析报告", "报告图",
         "相似度矩阵", "平均光谱", "相减_A减", "数据库比对", "启动转换工具",
         "启动拉曼光谱工具", "拉曼光谱工具", "叠加图")
PATH_RX = re.compile(r"[A-Za-z]:\\[^\s\"'|]*")

d = os.path.join(tempfile.gettempdir(), "_en_cli")
os.makedirs(d, exist_ok=True)
csv1 = os.path.join(d, "a.csv")
csv2 = os.path.join(d, "b.csv")
for i, p in enumerate((csv1, csv2)):
    if not os.path.exists(p):
        import math
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            f.write("Wavenumber,Intensity\n")
            for k in range(300, 1601):
                y = sum((9 + i * 2) * math.exp(-((k - (c + i * 3)) ** 2) / 200.0)
                        for c in (420, 640, 1008))
                f.write("%d,%.4f\n" % (k, y))

ok = [0, 0]


def run(label, args, allow=(), data_rows=False):
    cmd = [PY, SRC, "--lang", "en"] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180)
        out = (r.stdout or "") + (r.stderr or "")
    except Exception as exc:
        ok[1] += 1
        print("  [FAIL] %s 执行失败 %s" % (label, repr(exc)[:80]))
        return
    bad = []
    for ln in out.splitlines():
        probe = PATH_RX.sub("<path>", ln)
        if not CJK.search(probe):
            continue
        if any(a in probe for a in (ALLOW + tuple(allow))):
            continue
        # 矿物表是双语参考数据：名称列本身带中文名（如 "Zircon (锆石)"）属正常
        if data_rows and re.search(r"[A-Za-z]{3,}", probe):
            continue
        bad.append(probe.strip()[:90])
    if bad:
        ok[1] += 1
        print("  [FAIL] %s 中文残留 %d 处：%s" % (label, len(bad), bad[:5]))
    else:
        ok[0] += 1
        print("  [OK] %s" % label)


run("--help", ["--help"])
run("--manual", ["--manual"])
run("--data-dir", ["--data-dir"])
run("--rruff-list", ["--rruff-list"])
run("--mineral-search", ["--mineral-search", "Zircon"], data_rows=True)
run("--mineral-info", ["--mineral-info", "Zircon"], data_rows=True)
run("--by-element", ["--by-element", "Zr Si"], data_rows=True)
run("--by-formula", ["--by-formula", "SiO2"], data_rows=True)
run("转换 --png --peaks", ["--png", "--peaks", "--out", d, csv1])
run("--identify", ["--identify", csv1, "--identify-top", "3"])
run("--identify-all", ["--identify", csv1, "--identify-all", "--identify-top", "2"])
run("--cluster", ["--cluster", d, "--cluster-cut", "0.3"])
run("--map", ["--map", "1,2", csv1, csv2])
run("--report", ["--report", d, "--out", d])
run("--batch", ["--batch", d, "--out", d])
run("--pair", ["--pair", csv1])
run("--db-match", ["--db-match", csv1])
run("--overlay", ["--overlay", d, "--out", d])
run("--no-peak-dash", ["--png", "--no-peak-dash", "--no-peak-labels", "--out", d, csv1])
run("--cache-limit", ["--cache-limit"])

# 命令行子进程会把 --lang 写进 ini，这里清掉，避免自测污染用户设置
try:
    sys.path.insert(0, ROOT)
    import jws2csv as _T
    _s = _T._load_settings()
    _s.pop("lang", None)
    _T._save_settings(_s)
except Exception:
    pass

print()
print("英文命令行自测：通过 %d 项，失败 %d 项" % (ok[0], ok[1]))
sys.exit(1 if ok[1] else 0)
