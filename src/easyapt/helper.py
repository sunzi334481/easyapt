#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
easyapt 提权助手（通过 pkexec 以 root 运行）
所有写操作统一在这里执行，GUI 只负责调用并展示输出。
用法: pkexec /usr/lib/easyapt/helper.py <命令> [参数...]
"""
import argparse
import glob
import gzip
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

APT_DIR = "/etc/apt"
SOURCES_LIST = os.path.join(APT_DIR, "sources.list")
SOURCES_D = os.path.join(APT_DIR, "sources.list.d")

APT_COMMON_OPTS = [
    "-y",
    "-o", "Dpkg::Options::=--force-confdef",
    "-o", "Dpkg::Options::=--force-confold",
]

# ---------------------------------------------------------------- 进度解析
# apt 在管道模式下不输出“解压/配置”阶段的百分比（只有 dpkg 读数据库的
# 干扰百分比），因此按计划摘要里的总包数与各阶段已完成包数推算真实进度。
# 中英文摘要都要支持（GUI 环境可能是 zh_CN 或 C）。
_SUMMARY_RES = (
    (re.compile(r"升级了\s*(\d+)\s*个软件包"), "up"),
    (re.compile(r"新安装了\s*(\d+)\s*个软件包"), "new"),
    (re.compile(r"重新安装了\s*(\d+)\s*个软件包"), "re"),
    (re.compile(r"要卸载\s*(\d+)\s*个软件包"), "rem"),
)
_EN_SUMMARY_RE = re.compile(
    r"(\d+) upgraded(?:[,\s]+(\d+) newly installed)?"
    r"(?:[,\s]+(\d+) reinstalled)?(?:[,\s]+(\d+) to remove)?")
_STEP_RES = (
    (re.compile(r"^(?:正在解压|Unpacking)\s+(\S+)"), "unpack"),
    (re.compile(r"^(?:正在设置|正在设定|Setting up)\s+(\S+)"), "config"),
    (re.compile(r"^(?:正在删除|Removing)\s+(\S+)"), "remove"),
)


def _pump_apt_output(proc):
    """转发 apt 输出到标准输出，并统计各阶段进度发给 GUI。

    进度行格式: EASYAPT_PROGRESS:<0-100>，GUI 优先采用。
    升级/新装每包计 2 步（解压+配置），卸载每包计 1 步。
    """
    counts = {"unpack": set(), "config": set(), "remove": set()}
    totals = {"up": 0, "new": 0, "re": 0, "rem": 0}
    state = {"last_pct": -1}
    linebuf = b""

    def emit():
        total = (totals["up"] + totals["new"] + totals["re"]) * 2 + totals["rem"]
        if total <= 0:
            return
        done = sum(len(v) for v in counts.values())
        pct = min(100, done * 100 // total)
        if pct != state["last_pct"]:
            state["last_pct"] = pct
            print("EASYAPT_PROGRESS:%d" % pct, flush=True)

    def handle(text):
        for rx, key in _SUMMARY_RES:
            m = rx.search(text)
            if m:
                totals[key] = int(m.group(1))
        m = _EN_SUMMARY_RE.search(text)
        if m:
            totals["up"] = int(m.group(1))
            if m.group(2):
                totals["new"] = int(m.group(2))
            if m.group(3):
                totals["re"] = int(m.group(3))
            if m.group(4):
                totals["rem"] = int(m.group(4))
        for rx, key in _STEP_RES:
            m = rx.match(text)
            if m:
                counts[key].add(m.group(1).split(":")[0])
        emit()

    try:
        while True:
            chunk = os.read(proc.stdout.fileno(), 4096)
            if not chunk:
                break
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            linebuf += chunk
            while True:
                n_idx = linebuf.find(b"\n")
                r_idx = linebuf.find(b"\r")
                if n_idx < 0 and r_idx < 0:
                    break
                if r_idx < 0 or (0 <= n_idx < r_idx):
                    idx = n_idx
                else:
                    idx = r_idx
                line = linebuf[:idx]
                linebuf = linebuf[idx + 1:]
                try:
                    handle(line.decode("utf-8", "replace").strip())
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass


def log(msg):
    print("[easyapt] %s" % msg, flush=True)


def err(msg):
    print("[easyapt] 错误: %s" % msg, file=sys.stderr, flush=True)


_CHILD = None  # 当前正在运行的子进程（apt-get/dpkg 等）


def _on_signal(signum, _frame):
    """收到终止信号（用户取消/pkexec 被杀）时，先终止子进程再退出。"""
    global _CHILD
    log("收到终止信号(%d)，正在中断当前操作…" % signum)
    if _CHILD is not None and _CHILD.poll() is None:
        try:
            _CHILD.terminate()
        except Exception:
            pass
        try:
            _CHILD.wait(timeout=5)
        except Exception:
            try:
                _CHILD.kill()
            except Exception:
                pass
    sys.exit(128 + signum)


def setup_cancel_support():
    """
    GUI 取消任务时只会杀掉 pkexec 进程（普通用户无权杀 root 进程）。
    通过 PR_SET_PDEATHSIG 让内核在 pkexec(父进程) 死亡时给本进程发
    SIGTERM，再由信号处理器连带终止 apt-get/dpkg 子进程。
    """
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG = 1
    except Exception:
        pass
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)


def run_cmd(cmd, env_extra=None):
    """直接运行命令，输出实时回传给 GUI。"""
    global _CHILD
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    if env_extra:
        env.update(env_extra)
    log("执行命令: " + " ".join(cmd))
    _CHILD = subprocess.Popen(cmd, env=env)
    rc = _CHILD.wait()
    _CHILD = None
    return rc


def run_apt(args):
    """运行 apt-get: 输出经 _pump_apt_output 实时转发并计算真实进度。"""
    global _CHILD
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    cmd = ["apt-get"] + APT_COMMON_OPTS + args
    log("执行命令: " + " ".join(cmd))
    _CHILD = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)
    pump = threading.Thread(target=_pump_apt_output, args=(_CHILD,),
                            daemon=True)
    pump.start()
    rc = _CHILD.wait()
    pump.join(timeout=10)
    _CHILD = None
    return rc


# ---------------------------------------------------------------- 镜像源模板
# 每个镜像为一个函数 distro, codename -> (base_url, security_url)
MIRRORS = {
    "official": {
        "name": "官方源",
        "ubuntu": ("http://cn.archive.ubuntu.com/ubuntu/", "http://security.ubuntu.com/ubuntu/"),
        "debian": ("https://deb.debian.org/debian/", "https://security.debian.org/debian-security/"),
        "deepin": ("https://community-packages.deepin.com/deepin/", None),
    },
    "tsinghua": {
        "name": "清华大学镜像",
        "ubuntu": ("https://mirrors.tuna.tsinghua.edu.cn/ubuntu/", None),
        "debian": ("https://mirrors.tuna.tsinghua.edu.cn/debian/", "https://mirrors.tuna.tsinghua.edu.cn/debian-security/"),
        "deepin": ("https://mirrors.tuna.tsinghua.edu.cn/deepin/", None),
    },
    "aliyun": {
        "name": "阿里云镜像",
        "ubuntu": ("https://mirrors.aliyun.com/ubuntu/", None),
        "debian": ("https://mirrors.aliyun.com/debian/", "https://mirrors.aliyun.com/debian-security/"),
        "deepin": ("https://mirrors.aliyun.com/deepin/", None),
    },
    "ustc": {
        "name": "中科大镜像",
        "ubuntu": ("https://mirrors.ustc.edu.cn/ubuntu/", None),
        "debian": ("https://mirrors.ustc.edu.cn/debian/", "https://mirrors.ustc.edu.cn/debian-security/"),
        "deepin": ("https://mirrors.ustc.edu.cn/deepin/", None),
    },
    "huawei": {
        "name": "华为云镜像",
        "ubuntu": ("https://mirrors.huaweicloud.com/repository/ubuntu/", None),
        "debian": ("https://mirrors.huaweicloud.com/repository/debian/", "https://mirrors.huaweicloud.com/repository/debian-security/"),
        "deepin": ("https://mirrors.huaweicloud.com/repository/deepin/", None),
    },
}

DEBIAN_OLD_RELEASES = {"buster", "bullseye"}


def detect_distro():
    distro, codename = "", ""
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            data = dict(
                line.strip().split("=", 1)
                for line in f
                if "=" in line
            )
        distro = data.get("ID", "").strip('"').lower()
        codename = data.get("VERSION_CODENAME", "").strip('"')
    except OSError:
        pass
    if not codename:
        try:
            codename = subprocess.check_output(
                ["lsb_release", "-cs"], text=True).strip()
        except Exception:
            pass
    return distro, codename


def gen_sources_text(mirror_key, distro, codename):
    m = MIRRORS[mirror_key]
    if distro not in m:
        raise ValueError("暂不支持的发行版: %s" % (distro or "未知"))
    base, sec = m[distro]
    lines = ["# 由 易装(easyapt) 生成于 %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "# 镜像: %s" % m["name"], ""]
    if distro == "ubuntu":
        comps = "main restricted universe multiverse"
        for suite in (codename, codename + "-updates", codename + "-backports"):
            lines.append("deb %s %s %s" % (base, suite, comps))
        sec_base = sec if sec else base
        lines.append("deb %s %s-security %s" % (sec_base, codename, comps))
    elif distro == "debian":
        comps = ("main contrib non-free" if codename in DEBIAN_OLD_RELEASES
                 else "main contrib non-free non-free-firmware")
        for suite in (codename, codename + "-updates", codename + "-backports"):
            lines.append("deb %s %s %s" % (base, suite, comps))
        sec_base = sec if sec else base
        lines.append("deb %s %s-security %s" % (sec_base, codename, comps))
    elif distro == "deepin":
        lines.append("deb %s %s main contrib non-free" % (base, codename))
    return "\n".join(lines) + "\n"


def backup_file(path):
    if os.path.exists(path):
        bak = path + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, bak)
        log("已备份 %s -> %s" % (path, bak))


# ---------------------------------------------------------------- 命令实现
def cmd_update(_):
    return run_apt(["update"])


# 升级时的附加选项（Debian/Ubuntu/deepin 全系 apt 通用）:
#   --with-new-pkgs  允许安装新依赖，避免包被 "kept back" 扣留
#   Always-Include-Phased-Updates  跳过灰度分阶段更新限制（Ubuntu 系）
#   这些选项在旧版 apt 上会被安全忽略，不影响兼容性。
UPGRADE_OPTS = ["--with-new-pkgs",
                "-o", "APT::Get::Always-Include-Phased-Updates=true"]


def cmd_upgrade(a):
    mode = "full-upgrade" if a.full else "upgrade"
    return run_apt([mode] + UPGRADE_OPTS)


def cmd_install(a):
    return run_apt(["install"] + a.packages)


def cmd_remove(a):
    return run_apt(["remove"] + a.packages)


def cmd_purge(a):
    return run_apt(["purge"] + a.packages)


def cmd_autoremove(_):
    return run_apt(["autoremove"])


def cmd_clean(_):
    rc = run_apt(["clean"])
    if rc == 0:
        rc = run_apt(["autoclean"])
    return rc


def cmd_fix(_):
    log("第一步: 修复被中断的 dpkg 配置")
    rc = run_cmd(["dpkg", "--configure", "-a"])
    if rc != 0:
        err("dpkg 修复失败")
        return rc
    log("第二步: 修复依赖关系")
    return run_apt(["--fix-broken", "install"])


def cmd_reinstall(a):
    return run_apt(["install", "--reinstall"] + a.packages)


def cmd_install_deb(a):
    """安装本地 .deb 文件（路径含 / 时 apt 会按本地包处理）。"""
    paths = []
    for f in a.files:
        p = os.path.abspath(f)
        if not (p.lower().endswith(".deb") and os.path.isfile(p)):
            err("不是有效的 .deb 文件: %s" % f)
            return 2
        paths.append(p)
    return run_apt(["install"] + paths)


def cmd_auto_upgrade(_):
    """开机自动更新: 先更新软件列表，成功后升级全部软件。"""
    log("第一步: 更新软件列表")
    rc = run_apt(["update"])
    if rc != 0:
        err("更新软件列表失败，已取消后续升级")
        return rc
    log("第二步: 升级全部软件")
    return run_apt(["upgrade"] + UPGRADE_OPTS)


# ---------------------------------------------------------------- 软件源编辑
def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _write(path, text):
    backup_file(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    log("已写入 %s" % path)


def _toggle_list_file(path, enable):
    out = []
    for line in _read(path).splitlines():
        s = line.strip()
        if enable:
            if s.startswith("#") and re.match(r"#\s*deb(-src)?\s", s):
                line = re.sub(r"^\s*#\s*", "", line, count=1)
        else:
            if re.match(r"deb(-src)?\s", s):
                line = "# " + line
        out.append(line)
    _write(path, "\n".join(out) + "\n")


def _toggle_deb822_file(path, enable):
    text = _read(path)
    if re.search(r"(?im)^Enabled:\s*", text):
        text = re.sub(r"(?im)^Enabled:.*$",
                      "Enabled: " + ("yes" if enable else "no"), text)
    else:
        text = text.rstrip() + "\nEnabled: " + ("yes" if enable else "no") + "\n"
    _write(path, text)


def cmd_source_toggle(a):
    path = a.file
    if not os.path.isfile(path):
        err("文件不存在: %s" % path)
        return 2
    enable = a.action == "enable"
    if path.endswith(".sources"):
        _toggle_deb822_file(path, enable)
    else:
        _toggle_list_file(path, enable)
    log(("已启用" if enable else "已禁用") + ": %s" % path)
    log("提示: 请执行“更新软件列表”使改动生效")
    return 0


def cmd_source_delete(a):
    path = a.file
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(SOURCES_D) + os.sep):
        err("仅允许删除 %s 下的文件" % SOURCES_D)
        return 2
    if not os.path.isfile(path):
        err("文件不存在: %s" % path)
        return 2
    backup_file(path)
    os.remove(path)
    log("已删除 %s（备份在同目录 .bak- 文件中）" % path)
    log("提示: 请执行“更新软件列表”使改动生效")
    return 0


def cmd_source_add(a):
    line = a.line.strip()
    if not re.match(r"deb(-src)?\s+\S+\s+\S+", line):
        err("源格式不正确，应类似: deb https://xxx/ubuntu/ noble main")
        return 2
    fname = "easyapt-%s.list" % time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(SOURCES_D, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 由 易装(easyapt) 添加\n" + line + "\n")
    log("已添加软件源: %s" % path)
    log("正在更新软件列表...")
    return run_apt(["update"])


def cmd_ppa_add(a):
    if not shutil.which("add-apt-repository"):
        err("未安装 add-apt-repository（请先安装 software-properties-common）")
        return 2
    rc = run_cmd(["add-apt-repository", "-y", a.ppa])
    if rc == 0:
        log("正在更新软件列表...")
        rc = run_apt(["update"])
    return rc


def cmd_set_mirror(a):
    distro, codename = detect_distro()
    if not codename:
        err("无法识别系统代号(codename)")
        return 2
    log("检测到系统: %s (%s)" % (distro or "未知", codename))
    try:
        text = gen_sources_text(a.mirror, distro, codename)
    except ValueError as e:
        err(str(e))
        return 2
    target = SOURCES_LIST
    if not os.path.exists(target):
        # 部分系统主 sources.list 不存在（纯 deb822），写到独立文件
        target = os.path.join(SOURCES_D, "easyapt-mirror.list")
    backup_file(target)
    with open(target, "w", encoding="utf-8") as f:
        f.write(text)
    log("已将 %s 切换为 %s" % (target, MIRRORS[a.mirror]["name"]))
    log("正在更新软件列表...")
    return run_apt(["update"])


# ---------------------------------------------------------------- 入口
def main():
    if os.geteuid() != 0:
        err("助手必须以 root 身份运行（请通过 pkexec 调用）")
        return 1
    setup_cancel_support()
    ap = argparse.ArgumentParser(prog="easyapt-helper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("update")
    p = sub.add_parser("upgrade")
    p.add_argument("--full", action="store_true")
    p = sub.add_parser("install"); p.add_argument("packages", nargs="+")
    p = sub.add_parser("remove"); p.add_argument("packages", nargs="+")
    p = sub.add_parser("purge"); p.add_argument("packages", nargs="+")
    p = sub.add_parser("reinstall"); p.add_argument("packages", nargs="+")
    p = sub.add_parser("install-deb"); p.add_argument("files", nargs="+")
    sub.add_parser("auto-upgrade")
    sub.add_parser("autoremove")
    sub.add_parser("clean")
    sub.add_parser("fix")
    p = sub.add_parser("source-toggle"); p.add_argument("action", choices=["enable", "disable"]); p.add_argument("file")
    p = sub.add_parser("source-delete"); p.add_argument("file")
    p = sub.add_parser("source-add"); p.add_argument("line")
    p = sub.add_parser("ppa-add"); p.add_argument("ppa")
    p = sub.add_parser("set-mirror"); p.add_argument("mirror", choices=list(MIRRORS))

    a = ap.parse_args()
    fn = {
        "update": cmd_update, "upgrade": cmd_upgrade, "install": cmd_install,
        "remove": cmd_remove, "purge": cmd_purge, "reinstall": cmd_reinstall,
        "install-deb": cmd_install_deb, "auto-upgrade": cmd_auto_upgrade,
        "autoremove": cmd_autoremove, "clean": cmd_clean, "fix": cmd_fix,
        "source-toggle": cmd_source_toggle, "source-delete": cmd_source_delete,
        "source-add": cmd_source_add, "ppa-add": cmd_ppa_add,
        "set-mirror": cmd_set_mirror,
    }[a.cmd]
    rc = fn(a)
    log("操作结束，返回码: %d" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
