#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把界面摆到「点了一天、正在写标题、重复切到每年」的状态，供商店截图用。

为什么单独一个脚本：这一步需要点**无 id 的日期格**（只能用几何特征认），
而 shots.sh 是 bash，做不了这件事。截图本身仍由 shots.sh 的 shot() 抓
（那里有「相邻两张字节相同即判失败」的防线，不能绕开）。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e  # noqa: E402


def cells(s=None):
    """42 个日期格。

    它们是**无 id** 的静态 ButtonFlat，只能按几何特征认：
    ty ∈ (Button, ButtonFlat) + 文本为空 + 高宽都在 52±4。
    ⚠️ /snap 的 r 是 4 元数组 [x, y, w, h]，不是字典。
    """
    s = s if s is not None else e2e.snap()
    out = []
    for n in s:
        if n.get("ty") not in ("Button", "ButtonFlat"):
            continue
        if (n.get("t") or "").strip() != "":
            continue
        r = n.get("r")
        if not isinstance(r, (list, tuple)) or len(r) < 4:
            continue
        if 48 <= r[3] <= 56 and 48 <= r[2] <= 56:
            out.append(n)
    out.sort(key=lambda n: (round(n["r"][1] / 4.0), n["r"][0]))
    return out


def node(i, s=None):
    for n in (s if s is not None else e2e.snap()):
        if n.get("i") == i:
            return n
    return None


def main():
    cs = cells()
    if len(cs) != 42:
        print("FAIL: 只认到 %d 个日期格（期望 42）" % len(cs))
        return 1

    # 挑一格「在月中、又不是今天」的日子，写一条生日类日程（截图里看得清楚）。
    pick = cs[15]
    e2e.click_node(pick)
    time.sleep(0.9)

    nt = node("nt_input")
    if not nt:
        print("FAIL: 点格子没打开新建面板")
        return 1
    e2e.click_node(nt)
    time.sleep(0.3)
    e2e.type_text("妈妈生日")
    time.sleep(0.5)

    # 重复档位：不重复 → 每天 → 每周 → 每月 → 每年（按 id 连点，文案每次都在变）
    for _ in range(4):
        e2e.click_node(node("nr_btn"))
        time.sleep(0.35)

    rep = str((node("nr_btn") or {}).get("t"))
    tit = str((node("nt_input") or {}).get("t"))
    dat = str((node("nd_input") or {}).get("t"))
    print("  状态: 标题=%r  日期=%r  重复=%r" % (tit, dat, rep))
    if rep != "每年" or "妈妈生日" not in tit:
        print("FAIL: 状态没摆对")
        return 1

    # 不滚屏：新建面板展开时 metrics / fest_bar 会让位，整页正好装得下
    # （实测布局：月历 358..659、工具条 661..693、面板 715..892），一屏同框。
    return 0


if __name__ == "__main__":
    sys.exit(main())
