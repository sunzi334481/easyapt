#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史记录页: 解析 /var/log/apt/history.log，看看系统里装过/删过什么。"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QComboBox, QAbstractItemView, QHeaderView,
                             QToolTip)
from PyQt5.QtCore import Qt

from backend import AptBackend


class HistoryTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._records = []
        lay = QVBoxLayout(self)
        hint = QLabel("这里记录了系统里每一次软件的安装、卸载和升级（来自 apt 日志）。")
        hint.setStyleSheet("color:#666;")
        lay.addWidget(hint)

        top = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItems(["全部操作", "安装", "卸载", "彻底卸载", "升级", "其他"])
        self.filter.currentIndexChanged.connect(self._fill)
        btn = QPushButton("刷新")
        btn.clicked.connect(self.reload)
        top.addWidget(QLabel("只看:"))
        top.addWidget(self.filter)
        top.addStretch(1)
        top.addWidget(btn)
        lay.addLayout(top)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["时间", "操作", "涉及的软件包", "完整命令"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setMouseTracking(True)
        self.table.itemEntered.connect(
            lambda it: QToolTip.showText(self.table.cursor().pos(), it.text(), self.table))
        lay.addWidget(self.table, 1)
        self.reload()

    def reload(self):
        self._records = AptBackend.apt_history()
        self._fill()

    def _fill(self):
        want = self.filter.currentText()
        rows = [r for r in self._records if want == "全部操作" or r["action"] == want]
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [r["time"], r["action"] + ("（出错）" if r["error"] else ""),
                    r["packages"], r["command"]]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setToolTip(v)
                self.table.setItem(i, c, item)
