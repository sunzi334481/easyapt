#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
easyapt 只读查询后端（无需 root）
负责: 软件包列表/搜索/详情/历史记录/软件源解析
"""
import glob
import gzip
import os
import re
import subprocess


def _run(args, timeout=120):
    try:
        p = subprocess.run(args, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
        return p.stdout
    except Exception:
        return ""


def upgradable_count():
    """无需 root: 根据现有源数据统计可升级软件数量。"""
    out = _run(["apt", "list", "--upgradable"], timeout=120)
    return sum(1 for line in out.splitlines()
               if line and not line.startswith(("Listing", "WARNING")))


class Package:
    __slots__ = ("name", "version", "arch", "installed", "upgradable",
                 "old_version", "automatic", "local")

    def __init__(self, name, version, arch):
        self.name = name
        self.version = version
        self.arch = arch
        self.installed = False
        self.upgradable = False
        self.old_version = ""
        self.automatic = False
        self.local = False

    @property
    def status_text(self):
        if self.upgradable:
            return "可升级"
        if self.installed:
            return "已安装(本地)" if self.local else "已安装"
        return "未安装"


class AptBackend:
    def __init__(self):
        self._packages = None  # dict name -> Package

    # ------------------------------------------------------------ 包列表
    def refresh(self):
        """解析 `apt list` 全量输出（含安装/可升级状态），
        并用 dpkg 数据库补充仓库中不存在的本地安装包。"""
        out = _run(["apt", "list"], timeout=300)
        pkgs = {}
        for line in out.splitlines():
            if not line or line.startswith("Listing"):
                continue
            m = re.match(r"^(\S+)/\S+\s+(\S+)\s+(\S+)(?:\s+\[(.+)\])?$", line)
            if not m:
                continue
            name, ver, arch, flags = m.groups()
            p = pkgs.get(name) or Package(name, ver, arch)
            if flags:
                if "installed" in flags:
                    p.installed = True
                if "local" in flags:
                    p.local = True
                if "automatic" in flags:
                    p.automatic = True
                if "upgradable" in flags:
                    p.upgradable = True
                    p.installed = True  # 可升级的包必然已安装
                    m2 = re.search(r"upgradable from:\s*(\S+?)\]", flags)
                    if m2:
                        p.old_version = m2.group(1)
            pkgs[name] = p
        self._merge_dpkg(pkgs)
        self._packages = pkgs
        return pkgs

    @staticmethod
    def _merge_dpkg(pkgs):
        """用 dpkg 数据库校准安装状态（dpkg 是安装与否的最终真值）:
        1) 补充已安装但不在任何软件源里的包（如手动安装的 .deb）；
        2) 纠正 apt list 漏标的已安装包（如 [upgradable from: x] 不带
           installed 标记），避免可升级软件无法卸载/重装。"""
        out = _run(
            ["dpkg-query", "-W",
             "-f=${binary:Package}\\t${Version}\\t${Architecture}"
             "\\t${db:Status-Abbrev}\\n"],
            timeout=60)
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) != 4:
                continue
            pkgid, ver, arch, st = parts
            if len(st) < 2 or st[1] not in "iuf":
                continue  # 只保留真正已安装的（排除 config-files 等）
            name = pkgid.split(":")[0]
            p = pkgs.get(name)
            if p is None:
                p = Package(name, ver, arch)
                p.installed = True
                p.local = True
                pkgs[name] = p
            elif not p.installed:
                p.installed = True  # apt list 漏标，按 dpkg 真值纠正

    @property
    def packages(self):
        return self._packages or self.refresh()

    def search(self, keyword, scope="all"):
        """scope: all / installed / upgradable / not_installed
        有关键词时按相似度排序: 名称完全相同 > 名称前缀 > 名称包含 > 仅描述匹配。"""
        kw = keyword.strip().lower()
        desc_hits = {}
        if kw:
            # apt-cache search 同时匹配名称与描述，用其结果判定“描述命中”
            out = _run(["apt-cache", "search", keyword.strip()], timeout=30)
            for line in out.splitlines():
                name, _, desc = line.partition(" - ")
                if name:
                    desc_hits[name.strip()] = desc.strip().lower()
        result = []
        for p in self.packages.values():
            if scope == "installed" and not p.installed:
                continue
            if scope == "upgradable" and not p.upgradable:
                continue
            if scope == "not_installed" and p.installed:
                continue
            rank = 0
            if kw:
                rank = self._rank(p, kw, desc_hits)
                if rank is None:
                    continue
            result.append((rank, p))
        result.sort(key=lambda t: (t[0], not t[1].installed, t[1].name))
        return [p for _, p in result]

    @staticmethod
    def _rank(p, kw, desc_hits):
        """越小越相关；None 表示不匹配。"""
        name = p.name.lower()
        if name == kw:
            return 0
        if name.startswith(kw):
            return 1
        if kw in name:
            return 2
        if kw in desc_hits.get(p.name, ""):
            return 3
        return None

    # ------------------------------------------------------------ 包详情
    def package_details(self, name):
        show = _run(["apt-cache", "show", name])
        policy = _run(["apt-cache", "policy", name])
        info = {"name": name, "raw": show, "policy": policy}
        for line in show.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if k == "Description" and "description" not in info:
                info["description"] = v
            elif k in ("Version", "Section", "Homepage", "Maintainer",
                       "Installed-Size", "Depends"):
                info.setdefault(k.lower().replace("-", "_"), v)
        # 描述可能多行
        m = re.search(r"(?ms)^Description:\s*(.+?)(?=^\S|\Z)", show)
        if m:
            desc = "\n".join(
                l[1:] if l.startswith(" ") else l
                for l in m.group(1).splitlines()
            )
            info["description"] = desc.strip()
        return info

    # ------------------------------------------------------------ 软件源
    @staticmethod
    def list_source_files():
        files = []
        main = "/etc/apt/sources.list"
        if os.path.exists(main):
            files.append(main)
        for pattern in ("*.list", "*.sources"):
            files.extend(sorted(glob.glob("/etc/apt/sources.list.d/" + pattern)))
        return files

    @staticmethod
    def parse_sources(path):
        """返回 [{enabled, type, uri, suite, components, raw}]"""
        entries = []
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            return entries
        if path.endswith(".sources"):
            for block in re.split(r"\n\s*\n", text):
                if not block.strip():
                    continue
                def field(name):
                    m = re.search(r"(?im)^%s:\s*(.+)$" % name, block)
                    return m.group(1).strip() if m else ""
                enabled = field("Enabled").lower() != "no"
                for t in (field("Types") or "deb").split():
                    entries.append({
                        "enabled": enabled, "type": t,
                        "uri": field("URIs"), "suite": field("Suites"),
                        "components": field("Components"),
                        "raw": block.strip(),
                    })
        else:
            for line in text.splitlines():
                s = line.strip()
                enabled = True
                if s.startswith("#"):
                    if re.match(r"#\s*deb(-src)?\s", s):
                        enabled = False
                        s = s.lstrip("#").strip()
                    else:
                        continue
                m = re.match(r"(deb(?:-src)?)\s+(?:\[[^\]]*\]\s*)?(\S+)\s+(\S+)\s*(.*)", s)
                if m:
                    entries.append({
                        "enabled": enabled, "type": m.group(1),
                        "uri": m.group(2), "suite": m.group(3),
                        "components": m.group(4).strip(), "raw": line,
                    })
        return entries

    # ------------------------------------------------------------ 历史
    @staticmethod
    def apt_history(limit_blocks=400):
        """解析 /var/log/apt/history.log* 返回操作记录列表。"""
        files = sorted(glob.glob("/var/log/apt/history.log*"), reverse=True)
        records = []
        for path in files:
            if len(records) >= limit_blocks:
                break
            try:
                if path.endswith(".gz"):
                    f = gzip.open(path, "rt", encoding="utf-8", errors="replace")
                else:
                    f = open(path, encoding="utf-8", errors="replace")
                with f:
                    text = f.read()
            except OSError:
                continue
            for block in text.split("\n\n"):
                block = block.strip()
                if not block:
                    continue
                rec = {}
                for line in block.splitlines():
                    if ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    rec[k.strip()] = v.strip()
                if "Start-Date" in rec:
                    cmdline = rec.get("Commandline", "")
                    action = ""
                    for key in ("Install", "Remove", "Purge", "Upgrade"):
                        if key in rec:
                            action = {"Install": "安装", "Remove": "卸载",
                                      "Purge": "彻底卸载", "Upgrade": "升级"}[key]
                            pkgs = re.sub(r"\((?:[^)]*)\)", "", rec[key])
                            rec["_packages"] = " ".join(pkgs.split())[:200]
                            break
                    if not action:
                        action = "其他"
                    records.append({
                        "time": rec.get("Start-Date", ""),
                        "action": action,
                        "packages": rec.get("_packages", ""),
                        "command": cmdline,
                        "end": rec.get("End-Date", ""),
                        "error": rec.get("Error", ""),
                    })
        records.sort(key=lambda r: r["time"], reverse=True)
        return records[:limit_blocks]
