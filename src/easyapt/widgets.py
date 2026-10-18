#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新手友好的确认对话框: 解释操作含义、展示将执行的命令、危险操作标红。"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame)


class ConfirmDialog(QDialog):
    def __init__(self, title, explanation, command="", danger=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)

        head = QLabel(title)
        f = head.font()
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        head.setFont(f)
        lay.addWidget(head)

        lbl = QLabel(explanation)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.PlainText)
        lay.addWidget(lbl)

        if command:
            cmd_lbl = QLabel("将执行: " + command)
            cmd_lbl.setWordWrap(True)
            cmd_lbl.setStyleSheet(
                "color:#666; font-family:monospace; background:#f3f3f3;"
                "padding:6px; border-radius:4px;")
            lay.addWidget(cmd_lbl)

        if danger:
            warn = QLabel("⚠️ 这是高风险操作，可能影响系统稳定性，请确认你了解后果！")
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#c0392b; font-weight:bold;")
            lay.addWidget(warn)
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            lay.addWidget(line)

        btns = QHBoxLayout()
        btns.addStretch(1)
        no = QPushButton("取消")
        no.clicked.connect(self.reject)
        ok = QPushButton("确认执行")
        ok.setDefault(True)
        if danger:
            ok.setStyleSheet("background:#c0392b; color:white; padding:4px 16px;")
        ok.clicked.connect(self.accept)
        btns.addWidget(no)
        btns.addWidget(ok)
        lay.addLayout(btns)


def confirm(parent, title, explanation, command="", danger=False):
    return ConfirmDialog(title, explanation, command, danger, parent).exec_() \
        == QDialog.Accepted


# ---------------------------------------------------------------- 内置符号字体
# 随包内置 Symbola 字体（George Douros 制作，允许自由打包分发），覆盖
# emoji 及各类符号（📦🛠⚠️✓ 等）。系统缺字时由它兜底，避免界面出现方框。
EMOJI_FAMILIES = []
_FONT_PATHS = (
    "/usr/share/easyapt/fonts/Symbola_hint.ttf",
    "/usr/share/easyapt/fonts/Symbola.ttf",
)


def load_emoji_font():
    """注册随包分发的符号字体，返回可用的字体族名列表。"""
    global EMOJI_FAMILIES
    from PyQt5.QtGui import QFontDatabase
    for path in _FONT_PATHS:
        if not os.path.isfile(path):
            continue
        fid = QFontDatabase.addApplicationFont(path)
        if fid < 0:
            continue
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams:
            EMOJI_FAMILIES = list(fams)
            break
    return EMOJI_FAMILIES


def with_emoji_fallback(font):
    """给 QFont 追加内置符号字体作为回退字体族（原字体优先）。"""
    if EMOJI_FAMILIES:
        fams = [font.family()] + [f for f in EMOJI_FAMILIES
                                  if f != font.family()]
        if hasattr(font, "setFamilies"):  # Qt >= 5.13
            font.setFamilies(fams)
    return font
