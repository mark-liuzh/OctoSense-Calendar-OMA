#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本号一致性门禁（v0.5.9 A1）。

背景：v0.5.8 关于页写死「版本 0.5.4 · Apache-2.0」，而 manifest.json 已是
0.5.8 —— 用户无法确认实际运行版本（v0.5.8 Windows 报告 P1，本地已核实）。
发版流程以 manifest.json 的 version 为唯一版本源；本门禁保证
manifest.version == 关于页版本串，漂移即红。

用法（与其余静态门禁一致）：
    python3 tools/version_gate.py bundle/main.splash
退出码：0 = 一致；1 = 漂移或任一处缺失。
"""
import json
import os
import re
import sys

# 只认关于页 Label 的 text 串（注释里回溯历史版本不算数——
# v0.5.9 首跑就抓到 L10622 注释里的「版本 0.5.2 ·」误报）。
ABOUT_RE = re.compile(r'text:\s*"版本\s+(\d+\.\d+\.\d+)\s*·')


def fail(msg):
    print("FAIL: " + msg)
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        fail("用法: version_gate.py <main.splash>")
    splash_path = sys.argv[1]
    manifest_path = os.path.join(os.path.dirname(os.path.abspath(splash_path)),
                                 "manifest.json")
    if not os.path.exists(manifest_path):
        fail("找不到 manifest.json（应与 main.splash 同目录）：" + manifest_path)
    try:
        manifest = json.load(open(manifest_path, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        fail("manifest.json 解析失败：%s" % e)
    mver = str(manifest.get("version") or "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", mver):
        fail("manifest.version 不是 X.Y.Z 形状：%r" % mver)

    try:
        src = open(splash_path, encoding="utf-8").read()
    except Exception as e:  # noqa: BLE001
        fail("读不到 %s：%s" % (splash_path, e))
    hits = ABOUT_RE.findall(src)
    if not hits:
        fail("main.splash 里没有「版本 X.Y.Z ·」形状的关于页版本串")
    distinct = sorted(set(hits))
    if len(distinct) > 1:
        fail("关于页出现多个不同版本串 %s —— 必须唯一" % distinct)
    if distinct[0] != mver:
        fail("版本漂移：manifest=%s，关于页=%s —— 以 manifest 为唯一源改齐"
             % (mver, distinct[0]))
    print("version_gate PASS: manifest = 关于页 = %s" % mver)
    sys.exit(0)


if __name__ == "__main__":
    main()
