#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""软件源管理页: 查看/启用/禁用/添加/删除源，一键换国内镜像，PPA。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTreeWidget, QTreeWidgetItem,
                             QMessageBox, QDialog, QFormLayout, QLineEdit,
                             QComboBox, QDialogButtonBox, QCheckBox)

from backend import AptBackend
from runner import OutputDialog
from widgets import confirm

MIRROR_CHOICES = [
    ("official", "官方源"),
    ("tsinghua", "清华大学镜像（推荐教育网）"),
    ("aliyun", "阿里云镜像"),
    ("ustc", "中科大镜像"),
    ("huawei", "华为云镜像"),
]


class AddSourceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加软件源")
        lay = QFormLayout(self)
        self.uri = QLineEdit()
        self.uri.setPlaceholderText("如: https://mirrors.tuna.tsinghua.edu.cn/ubuntu/")
        self.suite = QLineEdit()
        self.suite.setPlaceholderText("发行版代号，如: noble / bookworm")
        self.comps = QLineEdit("main")
        self.src = QCheckBox("这是源码源 (deb-src，一般用不到)")
        lay.addRow("镜像地址", self.uri)
        lay.addRow("版本代号", self.suite)
        lay.addRow("组件", self.comps)
        lay.addRow("", self.src)
        box = QDialogButtonBox(QDialogButtonBox.Ok
                               | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addRow(box)

    def line(self):
        t = "deb-src" if self.src.isChecked() else "deb"
        return "%s %s %s %s" % (t, self.uri.text().strip(),
                                self.suite.text().strip(),
                                self.comps.text().strip())


class SourcesTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QVBoxLayout(self)
        hint = QLabel("软件源就是软件的“下载地址”。勾选=启用。切换到国内镜像可显著提升下载速度。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666;")
        lay.addWidget(hint)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["软件源条目", "类型", "地址 / 组件"])
        self.tree.setColumnWidth(0, 320)
        lay.addWidget(self.tree, 1)

        row = QHBoxLayout()
        for text, tip, fn in (
            ("启用/禁用", "暂时停用某个源而不删除它", self.toggle),
            ("添加源", "添加一行 deb 源", self.add),
            ("添加 PPA", "Ubuntu 用户常用的第三方源，如 ppa:graphics-drivers/ppa", self.add_ppa),
            ("删除", "删除选中的源文件（仅限 sources.list.d 目录，自动备份）", self.delete),
            ("刷新", "重新读取源配置", self.reload),
        ):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        box = QHBoxLayout()
        box.addWidget(QLabel("一键换源:"))
        self.mirror = QComboBox()
        for key, label in MIRROR_CHOICES:
            self.mirror.addItem(label, key)
        self.mirror.setCurrentIndex(1)
        box.addWidget(self.mirror)
        btn = QPushButton("切换镜像源")
        btn.setToolTip("自动备份并重写 /etc/apt/sources.list，然后更新软件列表")
        btn.clicked.connect(self.set_mirror)
        box.addWidget(btn)
        box.addStretch(1)
        lay.addLayout(box)

        self.reload()

    # ------------------------------------------------------------ 数据
    def reload(self):
        self.tree.clear()
        for path in AptBackend.list_source_files():
            entries = AptBackend.parse_sources(path)
            parent = QTreeWidgetItem([path, "", ""])
            parent.setData(0, Qt.UserRole, {"file": path, "is_file": True})
            flags = parent.flags() | Qt.ItemIsUserCheckable
            parent.setFlags(flags)
            any_enabled = any(e["enabled"] for e in entries)
            parent.setCheckState(0, Qt.Checked if any_enabled
                                 else Qt.Unchecked)
            self.tree.addTopLevelItem(parent)
            for e in entries:
                child = QTreeWidgetItem([
                    e["suite"], e["type"],
                    (e["uri"] + " " + e["components"]).strip()])
                child.setData(0, Qt.UserRole,
                              {"file": path, "entry": e})
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Checked if e["enabled"]
                                    else Qt.Unchecked)
                child.setDisabled(True)  # 条目级展示，整文件粒度启停
                parent.addChild(child)
            parent.setExpanded(True)

    def _selected_file(self):
        it = self.tree.currentItem()
        if not it:
            return None
        data = it.data(0, Qt.UserRole)
        return data.get("file") if data else None

    def _task(self, title, helper_args):
        rc = OutputDialog(title, self).start_privileged(helper_args)
        self.reload()
        return rc

    # ------------------------------------------------------------ 操作
    def toggle(self):
        path = self._selected_file()
        if not path:
            QMessageBox.information(self, "提示", "请先选择一个源文件。")
            return
        it = self.tree.currentItem()
        enable = it.checkState(0) == Qt.Checked
        action = "enable" if enable else "disable"
        word = "启用" if enable else "禁用"
        if confirm(self, word + "软件源",
                   "将%s文件:\n%s\n\n%s后需要“更新软件列表”才会生效。" % (word, path, word)):
            self._task(word + "软件源", ["source-toggle", action, path])

    def add(self):
        dlg = AddSourceDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        line = dlg.line()
        if confirm(self, "添加软件源",
                   "将添加以下源并自动更新软件列表:\n\n" + line):
            self._task("添加软件源", ["source-add", line])

    def add_ppa(self):
        from PyQt5.QtWidgets import QInputDialog
        ppa, ok = QInputDialog.getText(self, "添加 PPA",
                                       "输入 PPA 地址，如: ppa:graphics-drivers/ppa")
        if not ok or not ppa.strip().startswith("ppa:"):
            return
        if confirm(self, "添加 PPA",
                   "将通过 add-apt-repository 添加:\n\n" + ppa.strip()
                   + "\n\nPPA 是第三方维护的软件源，请确认来源可信。"):
            self._task("添加 PPA", ["ppa-add", ppa.strip()])

    def delete(self):
        path = self._selected_file()
        if not path:
            QMessageBox.information(self, "提示", "请先选择一个源文件。")
            return
        if path == "/etc/apt/sources.list":
            QMessageBox.warning(self, "不允许",
                                "主源文件 sources.list 不能删除，可以用“禁用”代替。")
            return
        if confirm(self, "删除软件源",
                   "将删除文件:\n%s\n\n删除前会自动备份（.bak- 文件）。\n"
                   "删除后需要“更新软件列表”才会生效。" % path, danger=True):
            self._task("删除软件源", ["source-delete", path])

    def set_mirror(self):
        key = self.mirror.currentData()
        label = self.mirror.currentText()
        if confirm(self, "一键切换镜像源",
                   "将自动识别系统版本，备份并重写 /etc/apt/sources.list 为:\n\n%s\n\n"
                   "随后自动更新软件列表。\n适合下载慢的新手用户。" % label,
                   danger=False):
            rc = self._task("切换镜像源", ["set-mirror", key])
            if rc == 0:
                self.main.packages_tab.reload()
