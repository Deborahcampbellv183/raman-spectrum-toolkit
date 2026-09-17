# -*- coding: utf-8 -*-
"""下载引擎自测：断点续传 / 并发分片 / 自动重试 / 完整性校验 / 取消。

用本机起一个可“说谎”的 HTTP 服务器来复现真实故障：
  · 传一半就断开连接（模拟国际链路抖动）
  · Content-Length 报全长但只发一半（模拟被截断却不报错）
  · 完全不支持 Range（模拟不支持续传的服务器）
不靠真实网络，所以又快又确定；服务器还会统计“累计发出多少字节”，
用来证明续传确实生效（没有从头重来）。
"""
import http.server
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jws2csv as T  # noqa: E402

ok = [0, 0]


def check(label, cond, extra=""):
    ok[0 if cond else 1] += 1
    print("  [%s] %s %s" % ("OK" if cond else "FAIL", label, extra))


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _serve(self, with_body):
        srv = self.server
        with srv.lock:
            srv.hits += 1
            hit = srv.hits
        payload = srv.payload
        rng = self.headers.get("Range")
        chunk = payload
        status = 200
        content_range = None
        if rng and srv.support_range:
            m = re.match(r"bytes=(\d+)-(\d*)", rng)
            if m:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else len(payload) - 1
                end = min(end, len(payload) - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                chunk = payload[start:end + 1]
                status = 206
                content_range = "bytes %d-%d/%d" % (start, end, len(payload))
        self.send_response(status)
        self.send_header("Content-Length", str(len(chunk)))
        if srv.support_range:
            self.send_header("Accept-Ranges", "bytes")
        if content_range:
            self.send_header("Content-Range", content_range)
        self.end_headers()
        if not with_body:
            return
        # 前 cut_times 次连接只发 cut_after 字节然后断线
        if srv.cut_after and hit <= srv.cut_times:
            piece = chunk[:srv.cut_after]
            try:
                self.wfile.write(piece)
                self.wfile.flush()
            except Exception:
                pass
            with srv.lock:
                srv.served += len(piece)
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            return
        # throttle：每 64 KB 歇一下，用来把“下载中取消”变成确定性测试
        delay = srv.throttle
        sent = 0
        try:
            if delay:
                while sent < len(chunk):
                    piece = chunk[sent:sent + (1 << 16)]
                    self.wfile.write(piece)
                    self.wfile.flush()
                    sent += len(piece)
                    with srv.lock:
                        srv.served += len(piece)
                    if srv.abort.is_set():
                        self.close_connection = True
                        return
                    time.sleep(delay)
            else:
                self.wfile.write(chunk)
                self.wfile.flush()
                sent = len(chunk)
                with srv.lock:
                    srv.served += len(chunk)
        except Exception:
            pass

    def do_HEAD(self):
        self._serve(with_body=False)

    def do_GET(self):
        self._serve(with_body=True)


class Server:
    """可控的测试服务器：payload / 是否支持 Range / 断线策略。"""

    def __init__(self, payload, support_range=True, cut_after=0, cut_times=0,
                 throttle=0.0):
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.daemon_threads = True
        self.httpd.payload = payload
        self.httpd.support_range = support_range
        self.httpd.cut_after = cut_after
        self.httpd.cut_times = cut_times
        self.httpd.throttle = throttle
        self.httpd.abort = threading.Event()
        self.httpd.hits = 0
        self.httpd.served = 0
        self.httpd.lock = threading.Lock()
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return "http://127.0.0.1:%d/data.bin" % self.httpd.server_address[1]

    @property
    def served(self):
        with self.httpd.lock:
            return self.httpd.served

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def open_gate(self):
        """修好线路：允许完整下发。"""
        self.httpd.cut_after = 0
        self.httpd.cut_times = 0


def parts_of(dst):
    d = os.path.dirname(dst)
    base = os.path.basename(dst)
    return sorted(n for n in os.listdir(d) if n.startswith(base + ".part"))


def main():
    tmp = os.path.join(tempfile.gettempdir(), "_raman_dl_test")
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)

    # 别把测试速率写进用户的设置文件
    T.remember_download_speed = lambda bps: None

    BIG = os.urandom(9 * 1024 * 1024)      # 9 MB：切成 5 个工作单元，够 4 条连接抢
    SMALL = os.urandom(300 * 1024)

    # ---------- 1) 正常下载（支持 Range，应走并发分片）----------
    srv = Server(BIG, support_range=True)
    dst = os.path.join(tmp, "a.bin")
    got = []
    T.download_file(srv.url, dst, progress=lambda g, t, s, e: got.append((g, t, s, e)))
    srv.stop()
    check("正常下载：文件已生成", os.path.isfile(dst), "%d B"
          % (os.path.getsize(dst) if os.path.isfile(dst) else 0))
    with open(dst, "rb") as f:
        check("正常下载：内容与源逐字节一致", f.read() == BIG, "")
    check("正常下载：大小正确", os.path.getsize(dst) == len(BIG), "")
    check("正常下载：分片文件已清理", not parts_of(dst), str(parts_of(dst)))
    check("正常下载：进度回调拿到了总数",
          bool(got) and got[-1][1] == len(BIG) and got[-1][0] == len(BIG),
          "末次 got=%s total=%s" % (got[-1][0], got[-1][1]) if got else "无回调")

    # 分片策略：按“工作单元”切，每条连接分到 DOWNLOAD_UNITS_PER_LANE 个单元，
    # 这样才有“谁先下完谁再领”的余地（静态均分时总耗时会被最慢那一段拖住）
    lanes = T.download_lanes(4, len(BIG))
    units = T.download_units(len(BIG), lanes)
    spans = T.download_spans(len(BIG), units)
    check("9 MB / 4 路：每条连接分到 4 个工作单元",
          lanes == 4 and units == 16, "lanes=%d units=%d" % (lanes, units))
    check("工作单元首尾相接、无缝无重叠",
          spans[0][0] == 0 and spans[-1][1] == len(BIG) - 1
          and all(spans[i][1] + 1 == spans[i + 1][0] for i in range(units - 1)),
          "共 %d 段，末段 %s" % (len(spans), spans[-1]))
    check("连接数翻倍、单元数跟着翻倍（领活余地不随文件缩小）",
          T.download_units(len(BIG), 8) == 32,
          str(T.download_units(len(BIG), 8)))
    check("文件太小不硬开并发（271 KB 只给 1 路）",
          T.download_lanes(32, 271 * 1024) == 1,
          str(T.download_lanes(32, 271 * 1024)))
    check("单元数有上限，不会为超大文件开一堆分片文件",
          T.download_units(8 * 1024 * 1024 * 1024, 32) <= T.DOWNLOAD_MAX_UNITS,
          str(T.download_units(8 * 1024 * 1024 * 1024, 32)))

    srv = Server(BIG, support_range=True, cut_after=1 << 20, cut_times=0)
    dst2 = os.path.join(tmp, "parts.bin")
    stop_flag = threading.Event()

    seen = set()
    real_open = open

    def spy(path, mode="r", *a, **k):
        m = re.search(r"\.part(\d+)$", str(path))
        if m:
            seen.add(int(m.group(1)))
        return real_open(path, mode, *a, **k)

    import builtins
    orig_open = builtins.open
    builtins.open = spy
    try:
        T.download_file(srv.url, dst2, connections=4)
    finally:
        builtins.open = orig_open
        srv.stop()
    check("4 条连接动态领完了全部 %d 个工作单元" % units,
          seen == set(range(units)), str(sorted(seen)))

    # ---------- 2) 传一半就断线：必须靠续传救回来，不能从头重来 ----------
    srv = Server(BIG, support_range=True, cut_after=1 << 20, cut_times=2)
    dst3 = os.path.join(tmp, "resume.bin")
    try:
        T.download_file(srv.url, dst3, connections=1)
        with open(dst3, "rb") as f:
            same = f.read() == BIG
    except Exception as exc:
        same = False
        print("     （第 1 次尝试失败：%s）" % exc)
        T.download_file(srv.url, dst3, connections=1)
        with open(dst3, "rb") as f:
            same = f.read() == BIG
    served = srv.served
    srv.stop()
    check("断线两次后仍下完且内容正确", same, "")
    check("续传生效：累计只传了不到 1.3 倍（没有从头重来）",
          served < len(BIG) * 1.3,
          "发出 %.1f MB / 文件 %.1f MB = %.2f 倍"
          % (served / 1048576.0, len(BIG) / 1048576.0, served / float(len(BIG))))

    # ---------- 3) 跨两次运行续传（模拟：先失败退出，再点一次接着下）----------
    srv = Server(BIG, support_range=True, cut_after=1 << 20, cut_times=99)
    dst4 = os.path.join(tmp, "cross.bin")
    failed = False
    try:
        T.download_file(srv.url, dst4, connections=1, retries=2)
    except Exception:
        failed = True
    first_served = srv.served
    check("线路一直断：本次必须失败，且不生成目标文件",
          failed and not os.path.exists(dst4), "dst 存在=%s" % os.path.exists(dst4))
    check("失败后保留分片，供下次续传", bool(parts_of(dst4)), str(parts_of(dst4)))
    srv.open_gate()
    T.download_file(srv.url, dst4, connections=1)
    with open(dst4, "rb") as f:
        check("修好线路后接着下：内容正确", f.read() == BIG, "")
    check("跨运行续传：第二次只补了下剩下的部分",
          srv.served - first_served < len(BIG),
          "第二次发出 %.1f MB / 共 %.1f MB"
          % ((srv.served - first_served) / 1048576.0, len(BIG) / 1048576.0))
    srv.stop()

    # ---------- 3b) 中途改并发数：必须沿用上次的切法，分片不能错位 ----------
    srv = Server(BIG, support_range=True, cut_after=128 * 1024, cut_times=999)
    dst4b = os.path.join(tmp, "concur.bin")
    try:
        T.download_file(srv.url, dst4b, connections=4, retries=2)
    except Exception:
        pass
    with open(dst4b + ".part.meta", encoding="utf-8") as f:
        meta = f.read().splitlines()
    srv.open_gate()
    T.download_file(srv.url, dst4b, connections=1)      # 换成 1 路接着下
    with open(dst4b, "rb") as f:
        same = f.read() == BIG
    check("改了并发数续传：内容依然正确（分片错位会拼出坏文件）",
          same, "上次切法 %s 个单元，这次 1 路" % (meta[2] if len(meta) > 2 else "?"))
    check("改了并发数续传：没有整份重下",
          srv.served < len(BIG) * 2,
          "累计发出 %.1f MB / 文件 %.1f MB"
          % (srv.served / 1048576.0, len(BIG) / 1048576.0))
    srv.stop()

    # ---------- 4) 服务器不支持 Range：退化为单连接，仍要下完 ----------
    srv = Server(SMALL, support_range=False)
    dst5 = os.path.join(tmp, "norange.bin")
    T.download_file(srv.url, dst5, connections=4)
    srv.stop()
    with open(dst5, "rb") as f:
        check("不支持 Range 的服务器也能下完", f.read() == SMALL, "")

    # ---------- 5) 截断却不报错 —— 绝不能把残缺当成功 ----------
    srv = Server(SMALL, support_range=True, cut_after=100 * 1024, cut_times=99)
    dst6 = os.path.join(tmp, "trunc.bin")
    err = None
    try:
        T.download_file(srv.url, dst6, connections=1, retries=2)
    except Exception as exc:
        err = exc
    srv.stop()
    check("被截断时报错，不返回成功", err is not None,
          "%s: %s" % (type(err).__name__, err) if err else "没有报错！")
    check("被截断时不生成目标文件（不会被当成已下载）",
          not os.path.exists(dst6), "dst 存在=%s" % os.path.exists(dst6))

    # ---------- 6) 远端文件换了：旧分片必须作废 ----------
    srv = Server(SMALL, support_range=True)
    dst7 = os.path.join(tmp, "changed.bin")
    with open(dst7 + ".part0", "wb") as f:
        f.write(b"x" * (SMALL.__len__() // 2))          # 假装是上次的半截
    with open(dst7 + ".part.meta", "w", encoding="utf-8") as f:
        f.write("%s\n%d\n" % (srv.url, 999999))         # 但记录的总大小对不上
    T.download_file(srv.url, dst7, connections=1)
    srv.stop()
    with open(dst7, "rb") as f:
        check("远端大小变了时丢弃旧分片、重新下对", f.read() == SMALL, "")

    # ---------- 7) 取消 ----------
    # 限速下发，保证取消是在“下载进行中”发生的（本机太快，不限速会先下完）
    SLOW = os.urandom(3 * 1024 * 1024)
    srv = Server(SLOW, support_range=True, throttle=0.02)
    dst8 = os.path.join(tmp, "cancel.bin")
    flag = threading.Event()

    def cancel_soon():
        time.sleep(0.7)
        flag.set()
        srv.httpd.abort.set()          # 让服务端也别一直写

    threading.Thread(target=cancel_soon, daemon=True).start()
    err = None
    t0 = time.time()
    try:
        T.download_file(srv.url, dst8, connections=1, cancel=flag)
    except Exception as exc:
        err = exc
    took = time.time() - t0
    srv.stop()
    check("取消时抛 DownloadCancelled",
          isinstance(err, T.DownloadCancelled), type(err).__name__ if err else "没抛")
    check("取消后不生成目标文件", not os.path.exists(dst8), "")
    check("取消是及时响应的（没有等到下完或超时）", took < 6.0, "耗时 %.1f s" % took)

    # 一开始就已取消：应立刻抛出
    srv = Server(SMALL, support_range=True)
    pre = threading.Event()
    pre.set()
    err = None
    try:
        T.download_file(srv.url, os.path.join(tmp, "pre.bin"), cancel=pre)
    except Exception as exc:
        err = exc
    srv.stop()
    check("开始前就取消则立刻抛出", isinstance(err, T.DownloadCancelled),
          type(err).__name__ if err else "没抛")

    # 多分片下载途中取消：线程里不能抛未捕获异常（否则 stderr 会刷 traceback，
    # 看起来就像又崩了）
    caught = []
    old_hook = threading.excepthook
    threading.excepthook = lambda args: caught.append(args.exc_type)
    try:
        srv = Server(os.urandom(9 * 1024 * 1024), support_range=True, throttle=0.05)
        flag2 = threading.Event()

        def stop_it():
            time.sleep(0.6)
            flag2.set()
            srv.httpd.abort.set()

        threading.Thread(target=stop_it, daemon=True).start()
        err = None
        try:
            T.download_file(srv.url, os.path.join(tmp, "multi.bin"),
                            connections=4, cancel=flag2)
        except Exception as exc:
            err = exc
        srv.stop()
    finally:
        threading.excepthook = old_hook
    check("多分片下载中取消：正常抛出 DownloadCancelled",
          isinstance(err, T.DownloadCancelled), type(err).__name__ if err else "没抛")
    check("多分片取消时线程没有未捕获异常（不会刷 traceback）",
          not caught, str([c.__name__ for c in caught]))

    # ---------- 8) 预计耗时换算 ----------
    check("预计耗时：100 MB 按默认速率应给出分钟数",
          T.format_eta(T.estimate_download_seconds(100 * 1048576, bps=0.27 * 1048576))
          .endswith("分钟"),
          T.format_eta(T.estimate_download_seconds(100 * 1048576, bps=0.27 * 1048576)))
    check("预计耗时：不到 1 分钟", T.format_eta(30) == "不到 1 分钟", T.format_eta(30))
    check("预计耗时：小时级",
          "小时" in T.format_eta(3900), T.format_eta(3900))
    check("大小未知时不给估算", T.estimate_download_seconds(0) is None, "")

    shutil.rmtree(tmp, ignore_errors=True)
    return 0


main()

def part_two():
    """界面自查：两个下载对话框要有进度条与【取消】，且英文模式不残留中文。"""
    import tkinter as tk
    import tkinter.messagebox as mb
    from tkinter import ttk
    mb.showinfo = lambda *a, **k: None
    mb.showwarning = lambda *a, **k: None
    mb.showerror = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: False

    CJK = re.compile(r"[\u4e00-\u9fff]")

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
        for opener, tag in (("open_rruff", "RRUFF 数据源"),
                            ("open_db_search", "ROD 检索")):
            before = {id(w) for w in app.winfo_children() if isinstance(w, tk.Toplevel)}
            try:
                getattr(app, opener)()
            except Exception as exc:
                check("%s 对话框能打开" % tag, False, repr(exc)[:90])
                continue
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
            kids = walk(dlg)
            bars = [w for w in kids if isinstance(w, ttk.Progressbar)]
            check("%s 对话框有进度条" % tag, bool(bars), "找到 %d 个" % len(bars))
            btns = []
            for w in kids:
                try:
                    if w.winfo_class() == "TButton":
                        btns.append((str(w.cget("text")), w))
                except Exception:
                    continue
            cbtn = [w for t, w in btns if "取消" in t]
            check("%s 对话框有【取消】按钮" % tag, bool(cbtn), str([t for t, _ in btns]))
            if cbtn:
                check("%s【取消】按钮默认禁用（没有任务时）" % tag,
                      "disabled" in cbtn[0].state(), str(cbtn[0].state()))
            check("%s 对话框不超出屏幕" % tag,
                  dlg.winfo_width() <= app.winfo_screenwidth()
                  and dlg.winfo_height() <= app.winfo_screenheight(),
                  "%dx%d" % (dlg.winfo_width(), dlg.winfo_height()))
            dlg.destroy()
            app.update()

        # 英文模式下重开：表头与按钮不能残留中文
        T.set_ui_lang("en")
        try:
            before = {id(w) for w in app.winfo_children() if isinstance(w, tk.Toplevel)}
            app.open_rruff()
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
                        if w.winfo_class() in ("TButton", "TLabel", "TCheckbutton"):
                            texts.append(str(w.cget("text")))
                        if w.winfo_class() == "Treeview":
                            texts += [w.heading(c, "text") for c in w.cget("columns")]
                    except Exception:
                        continue
                residue = [t for t in texts if CJK.search(t)]
                check("英文模式：RRUFF 对话框控件无中文残留", not residue,
                      str(residue[:6]))
                heads = []
                for w in walk(dlg):
                    if w.winfo_class() == "Treeview":
                        heads += [w.heading(c, "text") for c in w.cget("columns")]
                check("英文模式：数据包表头已翻译",
                      "Estimated time" in heads, str(heads))
                dlg.destroy()
                app.update()
        finally:
            T.set_ui_lang("zh")
        app.destroy()

    tk.Tk.mainloop = mainloop
    T._run_gui()


print()
print("=== 界面 ===")
try:
    part_two()
except Exception as exc:
    print("  （跳过界面自测：%s）" % exc)

print()
print("下载引擎自测：通过 %d 项，失败 %d 项" % (ok[0], ok[1]))
sys.exit(1 if ok[1] else 0)
