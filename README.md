# 易装 easyapt

新手友好的 apt 图形界面包管理器，用 PyQt5 编写，面向 deepin / Ubuntu / Debian 等 Debian 系发行版。

所有高风险操作（安装、卸载、清理、换源）执行前都会弹窗用大白话解释将要发生什么，确认后通过 pkexec 提权执行。

## 功能

- **软件管理**：搜索（按相关度排序）、安装 / 卸载 / 彻底卸载 / 重装、列表点表头排序、已安装 / 可升级 / 未安装筛选
- **本地 .deb 安装**：文件管理器右键"用易装打开"，或主界面"安装 .deb"按钮，支持多选
- **软件源管理**：查看当前源、测速、一键切换国内镜像（清华 / 阿里 / 中科大 / 华为等）
- **系统维护**：更新列表、一键升级（自动处理新依赖，不再"kept back"）、清理缓存、移除孤儿依赖、修复损坏依赖
- **开机更新检查**：自动更新 / 仅系统通知提醒 / 关闭 三种模式可选；通知走 freedesktop 标准，GNOME / KDE / DDE 通用
- **启动自动更新软件列表**（可在维护页关闭）
- **操作历史**：每次软件变更记录时间、动作、包名、结果与完整日志
- **状态准确**：以 dpkg 数据库为真值校准，可识别并卸载仓库中没有的本地安装包
- **内置 Symbola 符号字体**：缺 emoji 字体的系统也不再显示方框
- **任务可随时取消**：取消即真正终止整条 pkexec → helper → apt 进程链

## 安装

到 [Releases](https://github.com/sunny334481/easyapt/releases) 下载最新 `.deb`，然后：

```bash
sudo apt install ./easyapt_1.1.3_all.deb
```

依赖：`python3-pyqt5`、`policykit-1`、`apt`（桌面 Debian 系一般自带）。

## 卸载

```bash
sudo apt remove easyapt      # 保留配置
sudo apt purge easyapt       # 连同配置
```

用户级配置位于 `~/.config/easyapt/settings.json`，操作历史位于 `~/.local/share/easyapt/history.json`。

## 从源码构建

```bash
git clone https://github.com/sunny334481/easyapt.git
cd easyapt
bash build-deb.sh        # 产物在 dist/
```

## 项目结构

```
src/easyapt/        应用源码（PyQt5）
  app.py            入口、主窗口、关于界面、系统通知、开机检查流程
  helper.py         提权后执行的 apt 助手（安装/卸载/升级/换源，支持取消）
  backend.py        apt/dpkg 数据层（搜索、列表、状态校准、可升级统计）
  runner.py         任务输出终端窗口（实时日志、进度条、取消）
  tab_*.py          四个功能页
  settings.py       用户设置持久化
packaging/          desktop 文件、polkit 策略、图标、内置字体
build-deb.sh        一键打包脚本
```

## 兼容性

- deepin 20/23/25、Ubuntu 20.04+、Debian 11+ 及其他 Debian 系发行版
- 提权：pkexec（polkit）
- 通知：org.freedesktop.Notifications（DBus）→ notify-send 回退

## 许可

GPL-3.0+。内置 Symbola 字体 © George Douros，按其许可随包分发。

作者：sunny334481
