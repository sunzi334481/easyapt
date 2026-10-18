#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务执行器 + 实时输出窗口
通过 pkexec 调用 helper.py，把输出实时展示给新手用户。
"""
import os
import re

from PyQt5.QtCore import QProcess, Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPlainTextEdit, QProgressBar, QPushButton,
                             QMessageBox)

from widgets import with_emoji_fallback

HELPER_PATHS = ["/usr/lib/easyapt/helper.py"]


def helper_path():
    for p in HELPER_PATHS:
        if os.path.exists(p):
            return p
    # 开发模式: 与本文件同目录
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "helper.py")


class TaskRunner(QObject):
    """封装 QProcess 运行提权任务。"""
    output = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = None

    def run_privileged(self, helper_args):
        return self._start(["pkexec", helper_path()] + helper_args)

    def run_plain(self, argv):
        return self._start(argv)

    def _start(self, argv):
        if self.proc is not None:
            return False
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_read)
        self.proc.finished.connect(self._on_finished)
        self.proc.start(argv[0], argv[1:])
        if not self.proc.waitForStarted(3000):
            self.output.emit("无法启动进程: " + " ".join(argv))
            self.finished.emit(-1)
            self.proc = None
            return False
        return True

    def _on_read(self):
        data = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        self.output.emit(data)

    def _on_finished(self, code, _status):
        self.finished.emit(code)
        self.proc = None

    def cancel(self):
        if self.proc is not None:
            self.proc.kill()


class OutputDialog(QDialog):
    """实时输出窗口: 终端输出 + 进度条 + 取消按钮。"""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 460)
        self.runner = TaskRunner(self)
        self.return_code = -1
        self._exact_progress = False  # 收到精确进度后不再解析普通百分比

        lay = QVBoxLayout(self)
        self.head = QLabel("正在执行，请稍候…")
        lay.addWidget(self.head)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # 未知进度 -> 滚动条
        lay.addWidget(self.progress)

        self.term = QPlainTextEdit()
        self.term.setReadOnly(True)
        self.term.setFont(with_emoji_fallback(QFont("Monospace", 9)))
        lay.addWidget(self.term, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_close = QPushButton("关闭")
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_close)
        lay.addLayout(btns)

        self.runner.output.connect(self._append)
        self.runner.finished.connect(self._done)

    def start_privileged(self, helper_args):
        if not self.runner.run_privileged(helper_args):
            self._fail("无法启动 pkexec，请确认已安装 policykit-1")
        self.exec_()
        return self.return_code

    def start_plain(self, argv):
        if not self.runner.run_plain(argv):
            self._fail("无法启动进程: " + " ".join(argv))
        self.exec_()
        return self.return_code

    def _fail(self, msg):
        self.term.setPlainText(msg)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)
        self.return_code = -1

    def _append(self, text):
        # 解析进度: 优先采用 helper 输出的 EASYAPT_PROGRESS（由“正在解压/
        # 正在设置”行数与摘要总包数推算，解压阶段也会实时推进）；
        # 否则回退到普通百分比，但跳过 dpkg“读取数据库”的干扰百分比
        # （它在解压前瞬间冲到 100%，与实际进度无关）。
        pct = None
        m = re.findall(r"EASYAPT_PROGRESS:(\d{1,3})", text)
        if m:
            self._exact_progress = True
            pct = min(100, int(m[-1]))
            text = re.sub(r"EASYAPT_PROGRESS:\d{1,3}\n?", "", text)
        elif not self._exact_progress:
            for line in text.splitlines():
                if re.search(r"正在读取数据库|Reading database", line):
                    continue
                m2 = re.findall(r"(\d{1,3})\s*%", line)
                if m2:
                    pct = min(100, int(m2[-1]))
        if pct is not None:
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 100)
            self.progress.setValue(pct)
        self.term.moveCursor(QTextCursor.End)
        self.term.insertPlainText(text)
        self.term.moveCursor(QTextCursor.End)

    def _done(self, code):
        self.return_code = code
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if code == 0 else 0)
        if code == 0:
            self.head.setText("✅ 操作成功完成")
        elif code == 127:
            self.head.setText("⚠️ 操作已取消（未授权或用户取消）")
        else:
            self.head.setText("❌ 操作未完成，返回码 %d（请查看上方输出）" % code)
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)

    def _cancel(self):
        if QMessageBox.question(self, "取消操作",
                                "确定要中断当前操作吗？\n中断可能导致软件包状态不一致。") \
                == QMessageBox.Yes:
            self.runner.cancel()

    def closeEvent(self, e):
        if self.btn_close.isEnabled():
            e.accept()
        else:
            e.ignore()
