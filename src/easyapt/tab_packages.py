#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""软件包管理页: 搜索/安装/卸载/重装/详情/更新列表/升级/本地 .deb 安装。"""
import os

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QComboBox, QPushButton, QTableWidget,
                             QTableWidgetItem, QLabel, QMessageBox,
                             QAbstractItemView, QHeaderView, QDialog,
                             QTextBrowser, QDialogButtonBox, QFileDialog)

from backend import AptBackend
from runner import OutputDialog
from widgets import confirm


class LoadThread(QThread):
    done = pyqtSignal(dict)

    def __init__(self, backend):
        super().__init__()
        self.backend = backend

    def run(self):
        self.done.emit(self.backend.refresh())


class DetailDialog(QDialog):
    def __init__(self, backend, name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("软件包详情: " + name)
        self.resize(560, 480)
        lay = QVBoxLayout(self)
        view = QTextBrowser()
        info = backend.package_details(name)
        desc = info.get("description", "无描述")
        html = ["<h2>%s</h2>" % name]
        for key, label in (("version", "版本"), ("section", "分类"),
                           ("maintainer", "维护者"), ("installed_size", "安装后大小"),
                           ("homepage", "主页"), ("depends", "依赖")):
            if info.get(key):
                html.append("<p><b>%s:</b> %s</p>" % (label, info[key]))
        html.append("<p><b>简介:</b><br>%s</p>" % desc.replace("\n", "<br>"))
        if info.get("policy"):
            html.append("<h4>来源信息 (apt policy)</h4><pre>%s</pre>" % info["policy"])
        view.setHtml("".join(html))
        lay.addWidget(view)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        lay.addWidget(box)


class PackagesTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.backend = AptBackend()
        self._all = []
        self._loader = None

        lay = QVBoxLayout(self)
        hint = QLabel("在这里搜索并安装软件，或点击“安装 .deb”安装本地软件包。\n"
                      "双击行查看详情；选中后点击下方按钮执行操作。")
        hint.setStyleSheet("color:#666;")
        lay.addWidget(hint)

        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入软件名关键词，回车搜索，如: vlc、wps、输入法…")
        self.search_edit.returnPressed.connect(self.apply_filter)
        btn_search = QPushButton("搜索")
        btn_search.clicked.connect(self.apply_filter)
        self.scope = QComboBox()
        self.scope.addItems(["全部软件", "已安装", "可升级", "未安装"])
        self.scope.currentIndexChanged.connect(self.apply_filter)
        self.btn_deb = QPushButton("安装 .deb")
        self.btn_deb.setToolTip("选择本地 .deb 文件并安装；也可以在文件管理器中"
                                "直接双击 .deb 文件用易装打开")
        self.btn_deb.clicked.connect(self.pick_deb)
        self.btn_update = QPushButton("更新软件列表")
        self.btn_update.setToolTip("相当于 sudo apt update：从软件源获取最新软件信息")
        self.btn_update.clicked.connect(self.do_update)
        self.btn_upgrade = QPushButton("一键升级")
        self.btn_upgrade.setToolTip("升级所有已安装的软件到最新版（相当于 sudo apt upgrade）")
        self.btn_upgrade.clicked.connect(self.main.run_upgrade)
        top.addWidget(self.search_edit, 1)
        top.addWidget(btn_search)
        top.addWidget(self.scope)
        top.addWidget(self.btn_deb)
        top.addWidget(self.btn_update)
        top.addWidget(self.btn_upgrade)
        lay.addLayout(top)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["软件包名", "版本", "状态", "架构"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)  # 点击表头可按列排序
        self.table.itemDoubleClicked.connect(self.show_detail)
        lay.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.status_lbl = QLabel("正在加载软件列表…")
        bottom.addWidget(self.status_lbl, 1)
        for text, tip, fn in (
            ("安装", "安装选中的软件（相当于 sudo apt install）", self.do_install),
            ("重新安装", "已安装的软件损坏时可尝试重装", self.do_reinstall),
            ("卸载", "卸载但保留配置文件（相当于 sudo apt remove）", self.do_remove),
            ("彻底卸载", "连同配置一起删除（相当于 sudo apt purge）", self.do_purge),
            ("详情", "查看软件详细介绍", self.show_detail),
        ):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            bottom.addWidget(b)
        lay.addLayout(bottom)

        self.reload()

    # ------------------------------------------------------------ 数据
    def reload(self):
        self.table.setRowCount(0)
        self.status_lbl.setText("正在加载软件列表…")
        self._loader = LoadThread(self.backend)
        self._loader.done.connect(self._on_loaded)
        self._loader.start()

    def _on_loaded(self, pkgs):
        self._all = list(pkgs.values())
        self.apply_filter()

    def apply_filter(self):
        kw = self.search_edit.text()
        scope = ["all", "installed", "upgradable", "not_installed"][self.scope.currentIndex()]
        rows = self.backend.search(kw, scope)
        if not kw and scope == "all":
            rows = rows[:500]  # 全部包太多，先展示前 500
        self.table.setSortingEnabled(False)  # 填充期间禁用排序，防止行错位
        # 清空表头排序指示器：重新启用排序时不会按字母序重排，
        # 搜索结果得以保持后端的相关度排序（用户点表头仍可手动排序）
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.table.setRowCount(len(rows))
        for i, p in enumerate(rows):
            items = [QTableWidgetItem(p.name), QTableWidgetItem(p.version),
                     QTableWidgetItem(p.status_text), QTableWidgetItem(p.arch)]
            if p.upgradable:
                items[2].setForeground(QColor("#c0392b"))
            elif p.installed:
                items[2].setForeground(QColor("#27ae60"))
            for c, it in enumerate(items):
                self.table.setItem(i, c, it)
        self.table.setSortingEnabled(True)
        total = len(self._all)
        self.status_lbl.setText("共 %d 个软件包，当前显示 %d 个" % (total, len(rows)))

    # ------------------------------------------------------------ 选中项
    def selected_names(self):
        names = sorted({self.table.item(r.row(), 0).text()
                        for r in self.table.selectedIndexes() if r.column() == 0
                        or self.table.item(r.row(), 0)})
        return [n for n in names if n]

    def show_detail(self):
        names = self.selected_names()
        if names:
            DetailDialog(self.backend, names[0], self).exec_()

    # ------------------------------------------------------------ 操作
    def pick_deb(self):
        """主界面 .deb 安装入口: 选择一个或多个本地 .deb 文件安装。"""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择要安装的 .deb 软件包", os.path.expanduser("~"),
            "Debian 软件包 (*.deb);;所有文件 (*)")
        if paths:
            self.main.install_debs(paths)

    def _task(self, title, helper_args):
        dlg = OutputDialog(title, self)
        rc = dlg.start_privileged(helper_args)
        self.reload()
        self.main.refresh_history()
        return rc

    def do_update(self):
        if confirm(self, "更新软件列表",
                   "从软件源下载最新的软件信息（不安装、不升级任何软件）。\n"
                   "建议安装新软件前先执行一次。"):
            self._task("更新软件列表", ["update"])

    def do_install(self):
        names = [n for n in self.selected_names()
                 if not self.backend.packages.get(n) or not self.backend.packages[n].installed]
        if not names:
            QMessageBox.information(self, "提示", "请先在列表中选中要安装的软件。")
            return
        if confirm(self, "安装软件",
                   "将安装以下软件及其依赖：\n\n" + "、".join(names[:20]),
                   "apt install " + " ".join(names)):
            self._task("安装软件", ["install"] + names)

    def do_reinstall(self):
        names = [n for n in self.selected_names()
                 if self.backend.packages.get(n) and self.backend.packages[n].installed]
        if not names:
            QMessageBox.information(self, "提示", "请选中一个【已安装】的软件。")
            return
        if confirm(self, "重新安装",
                   "将重新下载并安装以下软件（配置不变）：\n\n" + "、".join(names[:20])):
            self._task("重新安装", ["reinstall"] + names)

    def do_remove(self):
        names = [n for n in self.selected_names()
                 if self.backend.packages.get(n) and self.backend.packages[n].installed]
        if not names:
            QMessageBox.information(self, "提示", "请选中一个【已安装】的软件。")
            return
        if confirm(self, "卸载软件",
                   "将卸载以下软件（保留配置文件，可随时装回）：\n\n" + "、".join(names[:20]),
                   "apt remove " + " ".join(names), danger=True):
            self._task("卸载软件", ["remove"] + names)

    def do_purge(self):
        names = [n for n in self.selected_names()
                 if self.backend.packages.get(n) and self.backend.packages[n].installed]
        if not names:
            QMessageBox.information(self, "提示", "请选中一个【已安装】的软件。")
            return
        if confirm(self, "彻底卸载",
                   "将卸载以下软件并【删除其配置文件】，此操作不可恢复：\n\n"
                   + "、".join(names[:20]),
                   "apt purge " + " ".join(names), danger=True):
            self._task("彻底卸载", ["purge"] + names)
