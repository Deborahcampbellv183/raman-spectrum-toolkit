# -*- coding: utf-8 -*-
"""双语内核自测：表解析、占位符一致性、语言切换、命令行英文输出。"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jws2csv as T

ok = [0, 0]


def check(label, cond, extra=""):
    ok[0 if cond else 1] += 1
    print("  [%s] %s %s" % ("OK" if cond else "FAIL", label, extra))


print("=== 翻译表 ===")
tbl = T.i18n_table()
check("表已解析", len(tbl) > 700, "%d 条" % len(tbl))
bad_sep = [k for k in tbl if "||" in k or "||" in tbl[k]]
check("键值里没有分隔符冲突", not bad_sep, str(bad_sep[:3]))
CJK = re.compile(r"[\u4e00-\u9fff]")
cn_keys = [k for k in tbl if CJK.search(k)]
check("所有键都是中文原文", len(cn_keys) == len(tbl),
      "非中文键 %d 个：%s" % (len(tbl) - len(cn_keys),
                          [k for k in tbl if not CJK.search(k)][:3]))
same = [k for k in tbl if tbl[k].strip() == k.strip()]
check("没有“译成自己”的占位条目", not same, str(same[:5]))

SPEC = re.compile(r"%[-#0 +]?[\d*]*(?:\.\d+)?[hlL]?[diouxXeEfFgGcrsa%]")


def sig(text):
    return sorted(SPEC.findall(text))


mismatch = []
for cn, en in tbl.items():
    if sig(cn) != sig(en):
        mismatch.append((cn[:34], sig(cn), sig(en)))
check("中英占位符一致（%s / %s 等）", not mismatch,
      "%d 处不一致：%s" % (len(mismatch), mismatch[:3]))

print("=== 语言切换 ===")
T.set_ui_lang("en", persist=False, apply_now=False)
miss_probe = T.T("这句话没有译文")
check("未收录文案原样返回", miss_probe == "这句话没有译文", miss_probe)
miss = T.i18n_missing()
check("未命中的中文会被记账", "这句话没有译文" in miss, "共 %d 条" % len(miss))
check("模板回退翻译（先格式化再输出）",
      T.T("已下载，索引 639 条") == "downloaded, 639 entries indexed",
      T.T("已下载，索引 639 条"))
check("模板回退：另一条",
      T.T("索引完成：639 条") == "Indexed: 639 entries",
      T.T("索引完成：639 条"))
check("模板回退：带换行的",
      T.T("结论：Quartz 可信\n") == "Conclusion: Quartz 可信\n",
      repr(T.T("结论：Quartz 可信\n")))
check("模板回退不会误伤无关文本",
      T.T("随便一句 123 话") == "随便一句 123 话")
T.set_ui_lang("zh", persist=False, apply_now=False)
check("切回中文正常", T.T("光谱预览") == "光谱预览")
check("语言别名（EN/English/中文）",
      T.set_ui_lang("English", persist=False, apply_now=False) == "en"
      and T.set_ui_lang("zh_CN", persist=False, apply_now=False) == "zh")
T.set_ui_lang("zh", persist=False, apply_now=False)
print("  当前语言：%s，语言表：%s" % (T.ui_lang(), T._LANG_LABELS))
check("设置可持久化（写 ini 再读回）",
      T.set_ui_lang("en", persist=True, apply_now=False) == "en"
      and T._load_settings().get("lang") == "en")
T.set_ui_lang("zh", persist=True, apply_now=False)

print("=== 命令行英文输出 ===")
exe = [sys.executable, os.path.join(ROOT, "jws2csv.py")]
# 磁盘上的真实目录名、内置矿物表里的中文矿物名属于“数据”，不算界面残留
DATA_OK = set("工具数据参考谱库RRUFF数据包分析结果启动转换工具光谱转换工具使用说明"
              "启动拉曼光谱工具拉曼光谱工具")
for rec in T._MINERAL_DB:
    DATA_OK |= set(rec["cn"])
PATH_RE = re.compile(r"[A-Za-z]:\\")


def ui_residue(out):
    bad = []
    for line in out.splitlines():
        if not CJK.search(line) or PATH_RE.search(line):
            continue
        left = "".join(ch for ch in line if CJK.search(ch))
        if left and all(ch in DATA_OK for ch in left):
            continue
        bad.append(line)
    return bad


for args, want_en in (
        (["--lang", "en", "--data-dir"], "Data folder"),
        (["--lang", "en", "--rruff-list"], "RRUFF data packages"),
        (["--lang", "en", "--mineral-search", "Zircon"], "minerals found"),
        (["--lang", "en", "--help"], "Usage:"),
        (["--lang", "en", "--mineral-info", "Zircon"], "Formula"),
        (["--lang", "zh", "--data-dir"], "数据文件夹")):
    r = subprocess.run(exe + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    label = " ".join(args[2:]) or " ".join(args)
    check("--lang 输出：%s" % label, want_en in out,
          out.strip().splitlines()[-1][:70] if out.strip() else "（无输出）")
    if "en" in args:
        bad = ui_residue(out)
        check("  该输出无界面中文残留", not bad,
              "残留 %d 行：%s" % (len(bad), bad[:2]))

print()
# 命令行子进程会把 --lang 写进 ini，这里清掉，避免自测污染用户设置
try:
    _s = T._load_settings()
    _s.pop("lang", None)
    T._save_settings(_s)
except Exception:
    pass
print("双语内核自测：通过 %d 项，失败 %d 项" % (ok[0], ok[1]))
sys.exit(1 if ok[1] else 0)
