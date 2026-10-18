#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""易装 (easyapt) — 新手友好的 apt 图形界面包管理器。入口与主窗口。"""
import os
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QLabel,
                             QMessageBox, QDialog, QVBoxLayout, QHBoxLayout,
                             QPushButton)

from runner import OutputDialog
from widgets import confirm
from tab_packages import PackagesTab
from tab_sources import SourcesTab
from tab_maintenance import MaintenanceTab
from tab_history import HistoryTab
import settings
import widgets

APP_NAME = "易装"
APP_ID = "easyapt"
VERSION = "1.1.3"
APP_DESC = "新手友好的 apt 图形界面包管理器"
APP_AUTHOR = "sunny334481"
APP_URL = "https://github.com/sunzi334481/easyapt"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("%s %s — 新手友好的软件包管理器" % (APP_NAME, VERSION))
        self.resize(900, 620)

        tabs = QTabWidget()
        self.packages_tab = PackagesTab(self)
        self.sources_tab = SourcesTab(self)
        self.maintenance_tab = MaintenanceTab(self)
        self.history_tab = HistoryTab(self)
        tabs.addTab(self.packages_tab, "📦 软件管理")
        tabs.addTab(self.sources_tab, "🌐 软件源")
        tabs.addTab(self.maintenance_tab, "🛠 系统维护")
        tabs.addTab(self.history_tab, "📜 历史记录")
        self.setCentralWidget(tabs)

        self.statusBar().showMessage(
            "提示: 所有操作都会先弹窗解释并请你确认；输入密码后才能执行。")
        self._build_menu()
        # 启动后自动更新软件列表（可在 系统维护 页关闭）
        if settings.get_update_on_launch():
            QTimer.singleShot(600, self.auto_update_lists)

    def _build_menu(self):
        help_menu = self.menuBar().addMenu("帮助(&H)")
        act = help_menu.addAction("关于 %s(&A)" % APP_NAME)
        act.triggered.connect(self.show_about)

    def show_about(self):
        AboutDialog(self).exec_()

    def auto_update_lists(self):
        """启动后自动更新软件列表（pkexec 弹出一次密码框）。"""
        OutputDialog("更新软件列表", self).start_privileged(["update"])
        self.packages_tab.reload()

    # 供各页调用的公共操作 ------------------------------------------------
    def run_upgrade(self):
        if confirm(self, "一键升级",
                   "把所有已安装的软件升级到最新版本（不删除任何软件）。\n"
                   "软件较多时可能需要几分钟，期间请勿关闭窗口。",
                   "sudo apt upgrade"):
            OutputDialog("一键升级", self).start_privileged(["upgrade"])
            self.packages_tab.reload()
            self.refresh_history()

    def install_debs(self, paths):
        """文件管理器双击/右键“用易装打开”的本地 .deb 安装请求。"""
        names = "\n".join(os.path.basename(p) for p in paths)
        if confirm(self, "安装本地软件包",
                   "将安装以下本地软件包(.deb)及其依赖：\n\n" + names,
                   "apt install " + " ".join(paths)):
            OutputDialog("安装本地软件包", self).start_privileged(
                ["install-deb"] + paths)
            self.packages_tab.reload()
            self.refresh_history()

    def refresh_history(self):
        self.history_tab.reload()


def _deb_paths(args):
    """从命令行参数中挑出真实存在的 .deb 文件。"""
    return [os.path.abspath(a) for a in args
            if a.lower().endswith(".deb") and os.path.isfile(a)]


class AboutDialog(QDialog):
    """关于界面: 版本/简介/许可/致谢/项目主页。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于 %s" % APP_NAME)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)

        title = QLabel("%s %s" % (APP_NAME, VERSION))
        f = title.font()
        f.setPointSize(f.pointSize() + 6)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        sub = QLabel(APP_DESC)
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color:#666;")
        lay.addWidget(sub)

        body = QLabel(
            "面向 Linux 新手的软件包管理器，覆盖软件搜索/安装/卸载/升级、\n"
            "软件源管理、国内镜像一键切换、系统维护与操作历史。\n\n"
            "作者: %s\n"
            "许可: GPL-3.0+\n"
            "内置符号字体: Symbola（George Douros，允许自由分发）\n"
            "兼容: deepin / Ubuntu / Debian 等 Debian 系发行版" % APP_AUTHOR)
        body.setWordWrap(True)
        body.setStyleSheet("color:#333; padding:8px;")
        lay.addWidget(body)

        link = QLabel('<a href="%s">%s</a>' % (APP_URL, APP_URL))
        link.setOpenExternalLinks(True)
        link.setAlignment(Qt.AlignCenter)
        lay.addWidget(link)

        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton("关闭")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        lay.addLayout(btns)


def notify(title, message, timeout_ms=10000):
    """发送桌面通知（freedesktop 标准，GNOME/KDE/DDE/Cinnamon 通用）。

    优先级: QtDBus 直连通知服务（无需额外依赖）
            -> notify-send 命令（libnotify-bin）
            -> 返回 False 由调用方回退弹窗。
    """
    try:
        from PyQt5.QtDBus import (QDBusConnection, QDBusMessage,
                                  QDBusArgument)
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            msg = QDBusMessage.createMethodCall(
                "org.freedesktop.Notifications",
                "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications", "Notify")
            arg = QDBusArgument()
            arg.beginArray(8)  # QVariant::String
            arg.endArray()
            msg.setArguments([APP_NAME, 0, "easyapt", title, message,
                              arg, {}, timeout_ms])
            reply = bus.call(msg)
            if reply.type() != QDBusMessage.ErrorMessage:
                return True
    except Exception:
        pass
    import shutil
    import subprocess
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(["notify-send", "-a", APP_NAME, "-t",
                              str(timeout_ms), title, message])
            return True
        except Exception:
            pass
    return False


def _check_updates_flow():
    """开机自启动入口：按用户设置执行 自动更新 / 通知提醒 / 不处理。"""
    mode = settings.get_update_mode()
    if mode == settings.MODE_OFF:
        return 0
    if mode == settings.MODE_AUTO:
        return OutputDialog("开机自动更新").start_privileged(["auto-upgrade"])
    from backend import upgradable_count
    n = upgradable_count()
    if n <= 0:
        return 0
    msg = "检测到 %d 个软件可以升级，打开「易装」即可一键升级。" % n
    if notify("%s：发现软件更新" % APP_NAME, msg, timeout_ms=15000):
        return 0  # 已发系统通知，进程可直接退出
    # 通知服务不可用时回退为弹窗
    box = QMessageBox()
    box.setWindowTitle("发现软件更新")
    box.setIcon(QMessageBox.Information)
    box.setText("检测到 %d 个软件可以升级。" % n)
    box.setInformativeText("建议及时升级以获得最新功能与安全修复；\n"
                           "升级过程需要输入密码，期间请勿关闭窗口。")
    btn_now = box.addButton("立即升级", QMessageBox.AcceptRole)
    box.addButton("以后再说", QMessageBox.RejectRole)
    box.exec_()
    if box.clickedButton() is btn_now:
        return OutputDialog("一键升级").start_privileged(["upgrade"])
    return 0


def main():
    args = sys.argv[1:]
    app = QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    # 注册随包内置的符号字体，系统缺字（emoji 等）时兜底，避免方框
    widgets.load_emoji_font()
    app.setFont(widgets.with_emoji_fallback(app.font()))

    if "--check-updates" in args:
        sys.exit(_check_updates_flow())

    win = MainWindow()
    win.show()
    debs = _deb_paths(args)
    if debs:
        QTimer.singleShot(200, lambda: win.install_debs(debs))
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
