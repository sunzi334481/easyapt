#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
easyapt 用户设置（存于 ~/.config/easyapt/settings.json）

开机自动检查更新的三种模式:
  auto   开机后自动执行“更新软件列表 + 升级全部软件”（弹出一次密码框）
  notify 开机后静默检查，有更新时弹窗提醒，由用户决定是否升级
  off    开机不做任何检查
开机检查由 /etc/xdg/autostart/easyapt-updates.desktop 触发，
是否处理完全由这里的模式决定。
"""
import json
import os

CFG_DIR = os.path.expanduser(os.path.join("~", ".config", "easyapt"))
CFG_FILE = os.path.join(CFG_DIR, "settings.json")

MODE_AUTO = "auto"
MODE_NOTIFY = "notify"
MODE_OFF = "off"
MODES = (MODE_AUTO, MODE_NOTIFY, MODE_OFF)

_DEFAULTS = {"update_mode": MODE_NOTIFY, "update_on_launch": True}


def load():
    cfg = dict(_DEFAULTS)
    try:
        with open(CFG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in _DEFAULTS})
    except Exception:
        pass
    if cfg["update_mode"] not in MODES:
        cfg["update_mode"] = MODE_NOTIFY
    if not isinstance(cfg["update_on_launch"], bool):
        cfg["update_on_launch"] = True
    return cfg


def save(cfg):
    os.makedirs(CFG_DIR, exist_ok=True)
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_update_mode():
    return load()["update_mode"]


def set_update_mode(mode):
    if mode not in MODES:
        raise ValueError("未知的更新模式: %r" % (mode,))
    cfg = load()
    cfg["update_mode"] = mode
    save(cfg)


def get_update_on_launch():
    """主程序启动后是否自动更新软件列表。"""
    return load()["update_on_launch"]


def set_update_on_launch(enabled):
    cfg = load()
    cfg["update_on_launch"] = bool(enabled)
    save(cfg)
