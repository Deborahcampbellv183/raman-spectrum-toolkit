# -*- coding: utf-8 -*-
"""构建 Windows 绿色版压缩包。

用法：  python assets/make_release.py

流程：
  1. 用 PyInstaller 把 jws2csv.py 打包成单文件 exe（图标用 assets/icon.ico）；
  2. 组装成一个自包含目录：exe + 中英说明书 + README + 图标 + 工具数据 + 源码；
  3. 压缩成 dist/RamanSpectrumToolkit-v<版本>.zip。

注意：工具数据只带入“参考谱库 / RRUFF数据包 / 分析结果(_说明.txt)”，
      本机分析产生的临时结果不会被打进发布包。
"""
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
BUILD = os.path.join(ROOT, "_build_release")
STAGE = os.path.join(BUILD, "stage")
EXE = "RamanSpectrumToolkit.exe"
PKG = "RamanSpectrumToolkit"


def version():
    src = open(os.path.join(ROOT, "jws2csv.py"), encoding="utf-8").read()
    m = re.search(r'_MANUAL_VERSION\s*=\s*"([^"]+)"', src)
    return m.group(1) if m else "0.0"


def build_exe():
    work = os.path.join(BUILD, "pyi")
    dist = os.path.join(BUILD, "dist")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile",
           "--windowed", "--name", "RamanSpectrumToolkit",
           "--icon", os.path.join(ASSETS, "icon.ico"),
           "--distpath", dist, "--workpath", work,
           "--specpath", work,
           "--exclude-module", "numpy", "--exclude-module", "pandas",
           "--exclude-module", "scipy", "--exclude-module", "matplotlib",
           "--exclude-module", "PIL.ImageQt",
           os.path.join(ROOT, "jws2csv.py")]
    print("· PyInstaller 打包中…")
    subprocess.run(cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return os.path.join(dist, EXE)


def copy_into(src, dst):
    if not os.path.exists(src):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def stage_package(exe_path):
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE)
    target = os.path.join(STAGE, PKG)
    os.makedirs(target)

    shutil.copy2(exe_path, os.path.join(target, EXE))
    for name in ("使用说明.txt", "User_Guide.txt", "README.md", "LICENSE",
                 "CHANGELOG.md"):
        copy_into(os.path.join(ROOT, name), os.path.join(target, name))
    for name in ("icon.png", "icon.ico"):
        copy_into(os.path.join(ASSETS, name), os.path.join(target, "assets", name))

    data = os.path.join(ROOT, "工具数据")
    for sub in ("参考谱库", "RRUFF数据包"):
        copy_into(os.path.join(data, sub), os.path.join(target, "工具数据", sub))
    copy_into(os.path.join(data, "分析结果", "_说明.txt"),
              os.path.join(target, "工具数据", "分析结果", "_说明.txt"))

    src_dir = os.path.join(target, "源码")
    os.makedirs(src_dir, exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "jws2csv.py"), os.path.join(src_dir, "jws2csv.py"))
    copy_into(os.path.join(ROOT, "启动拉曼光谱工具.bat"),
              os.path.join(src_dir, "启动拉曼光谱工具.bat"))
    copy_into(os.path.join(ROOT, "tests"), os.path.join(src_dir, "tests"))
    return target


def make_zip(target):
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "%s-v%s.zip" % (PKG, version()))
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _dirs, files in os.walk(STAGE):
            for f in files:
                full = os.path.join(base, f)
                z.write(full, os.path.relpath(full, STAGE))
    return out


def main():
    exe = build_exe()
    target = stage_package(exe)
    out = make_zip(target)
    n = sum(len(f) for _b, _d, f in os.walk(target))
    print("· 打包目录：%s（%d 个文件）" % (target, n))
    print("· 发布包：%s（%.1f MB）" % (out, os.path.getsize(out) / 1048576.0))


if __name__ == "__main__":
    main()
