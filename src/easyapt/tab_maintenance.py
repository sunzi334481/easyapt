#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""系统维护页: 常用 apt 维护操作，每个操作附中文说明。"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame, QGridLayout, QGroupBox,
                             QRadioButton, QCheckBox)

from runner import OutputDialog
from widgets import confirm
import settings

ACTIONS = [
    ("更新软件列表", "apt update",
     "从软件源下载最新的软件信息。\n不安装、不升级任何软件，随时可安全执行。",
     ["update"], False),
    ("升级全部软件", "apt upgrade --with-new-pkgs",
     "把所有已安装的软件升级到最新版本。\n不会删除任何软件；允许安装新依赖，避免更新被扣留。\n建议定期执行。",
     ["upgrade"], False),
    ("完整系统升级", "apt full-upgrade",
     "升级整个系统，必要时会安装/删除软件以解决依赖。\n升级前建议保存好手头工作。",
     ["upgrade", "--full"], True),
    ("清理下载缓存", "apt clean",
     "删除已下载的安装包缓存（.deb 文件），释放磁盘空间。\n不影响已安装的软件，完全安全。",
     ["clean"], False),
    ("清理无用依赖", "apt autoremove",
     "卸载那些不再被任何软件需要的依赖包，释放空间。\n执行前请核对列表，确认没有误删。",
     ["autoremove"], True),
    ("修复依赖问题", "apt -f install",
     "当软件安装失败、提示依赖错误时使用。\n先修复 dpkg 中断，再自动补齐/修正依赖。",
     ["fix"], True),
]


class MaintenanceTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QVBoxLayout(self)
        hint = QLabel("系统出了状况或者想释放空间？从这里选择对应的维护操作。每个操作执行前都会再次确认。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666;")
        lay.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(12)
        for i, (name, cmd, desc, args, danger) in enumerate(ACTIONS):
            grid.addWidget(self._card(name, cmd, desc, args, danger), i // 2, i % 2)
        lay.addLayout(grid)
        lay.addSpacing(12)
        lay.addWidget(self._update_settings_box())
        lay.addWidget(self._launch_settings_box())
        lay.addStretch(1)

    # ------------------------------------------------------------ 开机更新设置
    def _update_settings_box(self):
        box = QGroupBox("开机自动检查更新")
        v = QVBoxLayout(box)
        tip = QLabel("每次开机登录后自动检查软件更新，检查过程不会影响正常使用。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#666; border:none;")
        v.addWidget(tip)
        self._rb_notify = QRadioButton(
            "检查并提醒我（推荐）— 发现更新时弹窗提示，由我决定是否升级")
        self._rb_auto = QRadioButton(
            "自动更新 — 开机后自动更新软件列表并升级全部软件（需输入一次密码）")
        self._rb_off = QRadioButton("关闭 — 开机不做任何检查")
        self._setting_rb = True  # 初始化期间不触发保存
        {settings.MODE_NOTIFY: self._rb_notify,
         settings.MODE_AUTO: self._rb_auto,
         settings.MODE_OFF: self._rb_off}[settings.get_update_mode()].setChecked(True)
        self._setting_rb = False
        for rb, mode in ((self._rb_notify, settings.MODE_NOTIFY),
                         (self._rb_auto, settings.MODE_AUTO),
                         (self._rb_off, settings.MODE_OFF)):
            rb.toggled.connect(lambda checked, m=mode: self._mode_changed(checked, m))
            v.addWidget(rb)
        return box

    def _mode_changed(self, checked, mode):
        if checked and not self._setting_rb:
            settings.set_update_mode(mode)

    # ------------------------------------------------------------ 启动更新设置
    def _launch_settings_box(self):
        box = QGroupBox("启动易装时")
        v = QVBoxLayout(box)
        self._cb_launch = QCheckBox(
            "自动更新软件列表（启动后弹出一次密码框，保证搜索结果最新）")
        self._cb_launch.setChecked(settings.get_update_on_launch())
        self._cb_launch.toggled.connect(
            lambda on: settings.set_update_on_launch(on))
        v.addWidget(self._cb_launch)
        return box

    def _card(self, name, cmd, desc, args, danger):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame{background:#fafafa;border:1px solid #ddd;"
                            "border-radius:8px;}")
        lay = QVBoxLayout(frame)
        title = QLabel(name + ("  ⚠️" if danger else ""))
        f = title.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 1)
        title.setFont(f)
        lay.addWidget(title)
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet("color:#555; border:none;")
        lay.addWidget(d)
        c = QLabel("对应命令: " + cmd)
        c.setStyleSheet("color:#999; font-family:monospace; border:none;")
        lay.addWidget(c)
        btn = QPushButton("执行")
        if danger:
            btn.setStyleSheet("background:#c0392b;color:white;")
        btn.clicked.connect(lambda _=False, a=(name, desc, cmd, args, danger): self._run(*a))
        lay.addWidget(btn)
        return frame

    def _run(self, name, desc, cmd, args, danger):
        if confirm(self, name, desc + "\n\n确定要执行吗？", "sudo " + cmd, danger):
            OutputDialog(name, self).start_privileged(args)
            self.main.packages_tab.reload()
            self.main.refresh_history()
