#!/usr/bin/env bash
# 一键构建 easyapt .deb 包（在 Debian/Ubuntu/Deepin 系统或 WSL 中运行）
set -euo pipefail

PKG=easyapt
VER=1.1.3
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$ROOT/dist"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "==> 准备目录结构"
mkdir -p "$STAGE/DEBIAN" \
         "$STAGE/usr/lib/easyapt" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/pixmaps" \
         "$STAGE/usr/share/polkit-1/actions" \
         "$STAGE/usr/share/doc/easyapt" \
         "$STAGE/usr/share/easyapt/fonts" \
         "$STAGE/etc/xdg/autostart"

echo "==> 拷贝程序文件"
install -m 644 "$ROOT"/src/easyapt/*.py "$STAGE/usr/lib/easyapt/"
install -m 755 "$ROOT/src/easyapt/helper.py" "$STAGE/usr/lib/easyapt/helper.py"
install -m 755 "$ROOT/src/easyapt/app.py"    "$STAGE/usr/lib/easyapt/app.py"
install -m 755 "$ROOT/packaging/easyapt"     "$STAGE/usr/bin/easyapt"
install -m 644 "$ROOT/packaging/easyapt.desktop" "$STAGE/usr/share/applications/"
install -m 644 "$ROOT/packaging/easyapt-updates.desktop" "$STAGE/etc/xdg/autostart/"
install -m 644 "$ROOT/packaging/org.easyapt.policy" "$STAGE/usr/share/polkit-1/actions/"
install -m 644 "$ROOT/packaging/icons/easyapt.png"  "$STAGE/usr/share/pixmaps/easyapt.png"
install -m 644 "$ROOT/packaging/fonts/Symbola_hint.ttf" \
               "$STAGE/usr/share/easyapt/fonts/Symbola_hint.ttf"
install -m 644 "$ROOT/packaging/fonts/symbola-copyright" \
               "$STAGE/usr/share/doc/easyapt/symbola-copyright"

cat > "$STAGE/usr/share/doc/easyapt/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: easyapt
Upstream-Contact: easyapt developers <easyapt@localhost>

Files: *
Copyright: 2026 easyapt developers
License: GPL-3.0+
 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.
 On Debian systems, the full text of the GPL-3 can be found in
 /usr/share/common-licenses/GPL-3.

Files: /usr/share/easyapt/fonts/Symbola_hint.ttf
Copyright: 2007-2015 George Douros
License: Symbola-font-license
 Fonts are free for any use; they may be opened, edited,
 modified, regenerated, packaged and redistributed.
 Full license text: /usr/share/doc/easyapt/symbola-copyright
EOF

SIZE=$(du -sk "$STAGE/usr" | cut -f1)

echo "==> 生成 control (Installed-Size: ${SIZE}K)"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VER
Section: admin
Priority: optional
Architecture: all
Installed-Size: $SIZE
Maintainer: sunny334481 <sunny334481@localhost>
Depends: python3 (>= 3.9), python3-pyqt5, apt, policykit-1
Recommends: software-properties-common
Description: 新手友好的 apt 图形界面包管理器（易装）
 易装(EasyApt) 是面向国内 Linux 新手的 apt 图形化前端，
 覆盖 apt 全量功能：软件搜索/安装/卸载/升级、软件源管理、
 一键切换国内镜像源（清华/阿里/中科大/华为）、系统维护
 （清理缓存/无用依赖/修复依赖）以及操作历史查看。
 所有写操作通过 pkexec 提权，执行前均有中文说明与二次确认。
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    update-desktop-database /usr/share/applications 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst"

mkdir -p "$OUT"
DEB="$OUT/${PKG}_${VER}_all.deb"
echo "==> dpkg-deb --build $DEB"
dpkg-deb --root-owner-group --build "$STAGE" "$DEB"

echo "==> 校验包信息"
dpkg-deb --info "$DEB"
echo
echo "构建完成: $DEB"
