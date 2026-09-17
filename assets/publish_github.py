# -*- coding: utf-8 -*-
"""把当前源码 + 绿色版压缩包发布到 GitHub 仓库。

用法：
    set GH_TOKEN_FILE=C:\\path\\to\\token.txt      &  python assets/publish_github.py
    python assets/publish_github.py --token-file C:\\path\\to\\token.txt

令牌来源优先级：
    --token-file 参数  >  环境变量 GH_TOKEN_FILE  >  环境变量 GH_TOKEN
令牌只用于 HTTP 头，全程不打印、不写入任何受版本管理的文件。

流程：
    1. 取令牌 → GET /user 确认身份
    2. 逐个文件上传为 blob（含二进制）→ tree → commit → 更新 main 分支
    3. 设置仓库 topics
    4. 建 Release（已存在则沿用）并上传 dist/RamanSpectrumToolkit-v<版本>.zip
"""
import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER = "qdTXTbp"
REPO = "raman-spectrum-toolkit"
API = "https://api.github.com"

DESC = ("Raman Spectrum Toolkit: convert JASCO .jws / CSV / SPC / JCAMP-DX spectra to CSV, "
        "Excel, PNG; detect, delete and fit Raman peaks, assign mineral bands, search ROD / "
        "RRUFF reference libraries, identify unknown spectra, overlay multiple datasets. "
        "Bilingual EN/ZH Windows desktop tool. 拉曼光谱工具：转换 · 分析 · 矿物鉴定")

TOPICS = ["raman-spectroscopy", "raman", "spectroscopy", "spectrum-converter", "jasco",
          "jws", "mineral-identification", "rruff", "rod-database", "peak-fitting",
          "xrd", "infrared", "desktop-app", "tkinter", "python", "bilingual",
          "geoscience", "materials-science"]

FILES = [
    ".gitignore", "README.md", "LICENSE", "CHANGELOG.md", "jws2csv.py",
    "使用说明.txt", "User_Guide.txt", "启动拉曼光谱工具.bat",
    "assets/icon.png", "assets/icon.ico", "assets/icon_64.b64",
    "assets/make_icon.py", "assets/embed_icon.py",
    "assets/make_readme_images.py", "assets/make_release.py",
    "assets/publish_github.py",
    "docs/example_spectrum.png", "docs/example_pairing.png", "docs/example_overlay.png",
    "tests/test_i18n_kernel.py", "tests/test_ui_english.py",
    "tests/test_output_english.py", "tests/test_cli_english.py",
    "tests/test_dialog_layout.py", "tests/test_overlay_dash.py",
    "tests/test_overlay_preview.py",
]

TOK = None


def version():
    src = open(os.path.join(ROOT, "jws2csv.py"), encoding="utf-8").read()
    m = re.search(r'_MANUAL_VERSION\s*=\s*"([^"]+)"', src)
    return m.group(1) if m else "0.0"


def read_token(path):
    if path:
        if not os.path.isfile(path):
            raise SystemExit("找不到令牌文件：%s" % path)
        with open(path, "r", encoding="utf-8-sig") as f:
            t = f.read().strip()
    else:
        t = (os.environ.get("GH_TOKEN") or "").strip()
    t = t.strip().strip('"').strip("'")
    if not t:
        raise SystemExit("没有拿到令牌。请用 --token-file 指定文件，"
                         "或设置环境变量 GH_TOKEN_FILE / GH_TOKEN。")
    print("· 令牌已读入（长度 %d，不回显任何字符）" % len(t))
    return t


def call(method, url, data=None, raw=None, ctype="application/json",
         ok=(200, 201, 204), tries=4):
    """发一个 GitHub API 请求。网络抖动（连接被重置 / 超时）自动重试。"""
    global TOK
    headers = {"Authorization": "Bearer " + TOK,
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "raman-spectrum-toolkit-publish"}
    body = None
    if raw is not None:
        body = raw
        headers["Content-Type"] = ctype
    elif data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = ctype

    last = None
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                txt = r.read().decode("utf-8", "replace")
                return r.status, (json.loads(txt) if txt.strip() else {})
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            if e.code in ok:
                return e.code, (json.loads(txt) if txt.strip() else {})
            # 5xx 多为服务端抖动，值得重试；4xx 是真错，直接报
            if e.code < 500:
                raise SystemExit("HTTP %s %s %s\n%s" % (e.code, method, url, txt[:400]))
            last = "HTTP %s %s" % (e.code, txt[:160])
        except Exception as e:                      # 网络类异常
            last = "%s: %s" % (type(e).__name__, e)
        if attempt < tries:
            wait = 3 * attempt
            print("   ~ 第 %d 次失败（%s），%d 秒后重试 %s"
                  % (attempt, last, wait, url.rsplit("/", 1)[-1][:40]))
            time.sleep(wait)
    raise SystemExit("多次重试仍失败 %s %s\n%s" % (method, url, last))


def main():
    global TOK
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", default=os.environ.get("GH_TOKEN_FILE") or "")
    args = ap.parse_args()

    tag = "v" + version()
    zip_path = os.path.join(ROOT, "dist", "RamanSpectrumToolkit-%s.zip" % tag)
    TOK = read_token(args.token_file)

    _st, me = call("GET", API + "/user")
    login = me.get("login")
    email = "%s@users.noreply.github.com" % (me.get("id") or login)
    print("· 已认证：%s" % login)
    if login != OWNER:
        raise SystemExit("令牌身份是 %s，与预期 %s 不一致" % (login, OWNER))

    # 1) 仓库已存在则沿用（本仓库是早先建好的，这里只做兜底）
    #    细粒度令牌通常没有“创建仓库”权限，403 也当已存在处理，后面几步会真正报错
    st, r = call("POST", API + "/user/repos",
                 {"name": REPO, "description": DESC, "private": False,
                  "auto_init": False, "has_issues": True, "has_wiki": False},
                 ok=(201, 422, 403))
    if st == 201:
        print("· 仓库已创建：%s" % r.get("html_url"))
    elif st == 403:
        print("· 令牌无建仓权限，按“仓库已存在”继续")

    # 2) 空仓库必须先用 Contents API 打一个初始提交，否则 Git Data API 会 409
    st, commits = call("GET", "%s/repos/%s/%s/commits?per_page=1" % (API, OWNER, REPO),
                       ok=(200, 409))
    if st == 409:
        with open(os.path.join(ROOT, ".gitignore"), "rb") as f:
            seed = f.read()
        st, init = call("PUT", "%s/repos/%s/%s/contents/.gitignore" % (API, OWNER, REPO),
                        {"message": "chore: 初始化仓库",
                         "content": base64.b64encode(seed).decode("ascii"),
                         "branch": "main"})
        parent = init["commit"]["sha"]
        print("· 空仓库已初始化：%s" % parent[:8])
    else:
        parent = commits[0]["sha"] if commits else None
        print("· 已有提交，接续：%s" % (parent[:8] if parent else "无"))

    # 3) 逐个文件上传为 blob，然后一次性提交
    blobs = []
    for rel in FILES:
        full = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(full):
            print("   ! 跳过缺失文件 %s" % rel)
            continue
        with open(full, "rb") as f:
            content = f.read()
        _st, b = call("POST", "%s/repos/%s/%s/git/blobs" % (API, OWNER, REPO),
                      {"content": base64.b64encode(content).decode("ascii"),
                       "encoding": "base64"})
        blobs.append({"path": rel, "mode": "100644", "type": "blob", "sha": b["sha"]})
        print("   + %-42s %8d B" % (rel, len(content)))

    _st, tree = call("POST", "%s/repos/%s/%s/git/trees" % (API, OWNER, REPO),
                     {"tree": blobs})
    _st, commit = call("POST", "%s/repos/%s/%s/git/commits" % (API, OWNER, REPO),
                       {"message": "%s 叠加图先预览再导出：可手动增减标注峰位" % tag,
                        "tree": tree["sha"],
                        "parents": ([parent] if parent else []),
                        "author": {"name": login, "email": email},
                        "committer": {"name": login, "email": email}})
    st, _ref = call("POST", "%s/repos/%s/%s/git/refs" % (API, OWNER, REPO),
                    {"ref": "refs/heads/main", "sha": commit["sha"]}, ok=(201, 422))
    if st == 422:
        call("PATCH", "%s/repos/%s/%s/git/refs/heads/main" % (API, OWNER, REPO),
             {"sha": commit["sha"], "force": True})
    print("· 已提交 %d 个文件，commit %s" % (len(blobs), commit["sha"][:8]))

    # 4) topics
    call("PUT", "%s/repos/%s/%s/topics" % (API, OWNER, REPO), {"names": TOPICS})
    print("· topics 已设置：%d 个" % len(TOPICS))

    # 5) Release（已存在则沿用）
    st, rel = call("GET", "%s/repos/%s/%s/releases/tags/%s" % (API, OWNER, REPO, tag),
                   ok=(200, 404))
    if st == 200:
        print("· Release 已存在，沿用：%s" % rel.get("html_url"))
    else:
        _st, rel = call("POST", "%s/repos/%s/%s/releases" % (API, OWNER, REPO),
                        {"tag_name": tag, "target_commitish": "main",
                         "name": "%s · 拉曼光谱工具 Raman Spectrum Toolkit" % tag,
                         "body": RELEASE_BODY % {"tag": tag},
                         "draft": False, "prerelease": False})
        print("· Release 已创建：%s" % rel.get("html_url"))

    # 6) 上传压缩包
    if os.path.isfile(zip_path):
        size = os.path.getsize(zip_path)
        up = ("https://uploads.github.com/repos/%s/%s/releases/%d/assets?name=%s"
              % (OWNER, REPO, rel["id"], os.path.basename(zip_path)))
        print("· 正在上传 %.1f MB …" % (size / 1048576.0))
        with open(zip_path, "rb") as f:
            _st, asset = call("POST", up, raw=f.read(),
                              ctype="application/zip", ok=(201, 422))
        print("· 附件：%s（%s）" % (asset.get("name"), asset.get("state")))
    else:
        print("! 没找到压缩包 %s（先跑 assets/make_release.py）" % zip_path)

    print("\n完成 → https://github.com/%s/%s" % (OWNER, REPO))


RELEASE_BODY = """## 拉曼光谱工具 · Raman Spectrum Toolkit %(tag)s

JASCO `.jws` 光谱转换 · 拉曼峰分析 · 矿物鉴定（中英双语，Windows 绿色版）

### 下载
下载下面的压缩包，解压到任意目录，双击 `RamanSpectrumToolkit.exe` 即可。
免安装、不写注册表，所有数据都写在解压目录的 `工具数据/` 里。

### 本次新增
- **叠加图改成「先预览、确认后再导出」**（菜单【分析工具 → 多数据图叠加（所选光谱）…】）。
  打开的是**预览窗口**，改参数、增减峰位都只重画预览，
  **不点【导出 PNG】就不会往结果目录写任何文件**。
  - **左键点图 = 在点击处加一个峰位**（蓝色虚线 + 蓝色数值）
  - **右键点虚线 = 删掉离点击处最近的峰位**（自动检测的、手动加的都能删）
  - 【重新检测】丢掉全部手动改动，回到自动检测的峰位
  - 参数改完按回车或点【刷新预览】才重画，免得每敲一个字符就重绘一次
  - 预览图按屏幕高度自适应缩放，窗口不会超出屏幕
  命令行 `--overlay` 仍是批处理，没有预览窗口，直接按自动检测的峰位出图。
- **叠加图按 stacked spectra 排布**：各条先归一化到最大值 = 1，再按“谱线偏移”
  纵向错开 k×偏移，**谱线彼此分开、不压在一起**（偏移 1.0 = 刚好不压线），
  每条一种颜色并带图例。前 8 条用标准色板，超过 8 条按黄金角旋转色相生成新色。
- **峰位跨谱合并**：同一个峰在各条谱上只画一条虚线、只标一个**平均波数**
  （容差可调，留空沿用“最小峰间距”，命令行 `--peak-merge 30`）。
- **峰位波长虚线**：自动识别的峰与手动补标的峰，都从峰顶画虚线引到横坐标轴，
  波数一眼可读（`--no-peak-dash` 可关掉）。
- **横坐标取各条谱波数范围的交集**，某条短一截时右边不再空出一段白。
- **可以删除自动标注的峰**：右键对准某个峰即可删掉离鼠标最近的那个峰；
  自动峰记进该文件的“已删除”名单，出图、峰列表与所有导出都按删除后的结果计算，
  点【恢复自动峰】一次全恢复。为避免误删，要求点在峰附近（横向约 ±1/40 图宽）。
- **显示峰位数值开关**：主界面【图表设置】里可关掉峰位数字，命令行 `--no-peak-labels`。

### 修复
- **高级设置窗口超出屏幕**：小屏 / 高 DPI 下原窗口会把底部
  「确定 / 应用 / 取消」顶到屏幕外、点不到。现在内容改为可滚动、
  按钮固定在底部，窗口高度不超过屏幕可用高度。
- 命令行瀑布图纵轴标签在英文模式下未翻译。
- 手动峰 / 已删自动峰的记账键原先混用相对路径与绝对路径，同一文件可能对不上。

### 画质与稳定性
- 七套自测合计 **161 项全部通过**，其中新增的 `tests/test_overlay_preview.py`
  在真实 Tk 窗口里走一遍左键加峰 / 右键删峰 / 重新检测 / 确认后导出，
  并断言“还没点导出时输出目录必须是空的”。
- 中英两份说明书（`使用说明.txt` / `User_Guide.txt`）同步更新至 2.2。

### 数据说明
参考谱与数据包来自 RRUFF 项目与 Raman Open Database，请遵守其使用条款；
本工具与上述项目无隶属关系。
"""


if __name__ == "__main__":
    main()
