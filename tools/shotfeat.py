#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把界面摆到新分区（待办 / 心情 / 目标 / 彩蛋）的**有数据**状态，供商店截图用。

为什么单独一个脚本：这一步要做两件 bash 做不了的事 ——
  ① 按**分区名**点顶部导航按钮（位置随面板开合而变，写死坐标必然扑空）；
  ② 往**带 id 的输入框**里打字（页面上一共有好几个 TextInput，只有 id 认得出）。
截图本身仍由 shots.sh 的 shot() 抓 —— 那里有「相邻两张字节完全相同即判失败」
的防线（曾经抓到过三张一模一样的商店截图），不能绕开。

用法: python tools/shotfeat.py <todo|mood|goal|egg>
退出码: 0 = 状态已摆好；非 0 = 没摆对（shots.sh 会因此判 FAIL）
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e  # noqa: E402


def node(i, s=None):
    for n in (s if s is not None else e2e.snap()):
        if n.get("i") == i:
            return n
    return None


def click_label(label, wait=0.8):
    n, _ = e2e.wait_btn(label)
    if not n:
        print("FAIL: 找不到按钮「%s」" % label)
        return False
    e2e.click_node(n)
    time.sleep(wait)
    return True


def type_into(i, text, wait=0.6):
    n = node(i)
    if not n:
        print("FAIL: 找不到输入框 %s" % i)
        return False
    e2e.click_node(n)
    time.sleep(0.3)
    e2e.type_text(text)
    time.sleep(wait)
    return True


def tab(name):
    return click_label(name, 0.9)


def expect_text(i, want):
    got = str((node(i) or {}).get("t") or "")
    if want in got:
        print("  OK   %s = %r" % (i, got))
        return True
    print("FAIL: %s 期望含 %r，实得 %r" % (i, want, got))
    return False


def st_todo():
    if not tab("待办"):
        return 1
    # 三条待办，勾掉第一条 —— 截图里能同时看到 [x] 与 [ ]，比全空或全满都有信息量
    for t in ("交初赛材料", "录 2 分钟演示视频", "跑一遍全量回归"):
        if not type_into("todo_in", t):
            return 1
        if not click_label("添加"):
            return 1
    n = node("td_b0")
    if not n:
        print("FAIL: 找不到第一条待办的勾选框 td_b0")
        return 1
    e2e.click_node(n)
    time.sleep(0.5)
    ok = expect_text("todo_stat", "已完成 1 / 3")
    return 0 if ok else 1


def st_mood():
    if not tab("心情"):
        return 1
    n = node("mood_b0")
    if not n:
        print("FAIL: 找不到心情档位按钮 mood_b0")
        return 1
    e2e.click_node(n)
    time.sleep(0.5)
    if not type_into("mood_in", "把冲突消解那条不报错的 bug 揪出来了"):
        return 1
    if not click_label("存备注"):
        return 1
    ok = expect_text("mood_sum", "心情：")
    return 0 if ok else 1


def st_goal():
    if not tab("目标"):
        return 1
    if not type_into("goal_in", "AP 考试"):
        return 1
    if not click_label("新建目标"):
        return 1
    # 两步子任务 + 勾掉第一步 → 进度条正好半格（字符串进度条，看得见）
    for t in ("背 300 个单词", "做一套真题"):
        if not type_into("goal_in", t):
            return 1
        if not click_label("加一步"):
            return 1
    n = node("gs_b00")
    if not n:
        print("FAIL: 找不到第一个子任务的勾选框 gs_b00")
        return 1
    e2e.click_node(n)
    time.sleep(0.5)
    ok1 = expect_text("gc_p0", "1/2 步")
    ok2 = expect_text("gc_bar0", "#####-----")
    return 0 if (ok1 and ok2) else 1


# 「历史上的今天」为空时应用自己会打这句话（见 main.splash 的 history_on）。
# 用它当**探针**比解析源码里的 HISTORY 表更稳：数据改了这里也不用跟着改。
# 2026-10-01 改造：「今日」卡无内容时**整张不渲染**，所以空判定改成看 `egg_today_tag` 在不在 /snap 里。
EMPTY_HIST = "这一天暂时没有收录"


def st_egg():
    if not tab("时光"):
        return 1
    # ⚠️ 为什么要往后走：前面的步骤点过日历格子（第 08 步摆「点格子写日程」），
    #    focus 因此被挪到了那一格 —— 而 9 月 15 日三张表都没收录，
    #    「今日」卡会整张消失（不是占位），整屏只有「时间胶囊」。
    #    商店截图更应该展示有内容的样子，所以往后走到 `egg_today_tag` 出现为止。
    #    往后而不是往前：9–12 月每月都有收录，最多走几步就能命中；并且**不解析源码表**，
    #    判定用的是「tag 是否在 /snap 里」，数据改动也不会让这里失效。
    for _ in range(20):
        if node("egg_today_tag"):
            break
        if not click_label("后一天", 0.45):
            print("FAIL: 找不到「后一天」按钮")
            return 1
    else:
        print("FAIL: 往后走了 20 天也没遇到有「今日」内容的日子")
        return 1

    for i in ("egg_date_l", "egg_today_tag", "egg_today_title"):
        if not str((node(i) or {}).get("t") or ""):
            print("FAIL: %s 是空的" % i)
            return 1
    print("  OK   时光分区已就位 · 日期=%r · tag=%r · title=%r"
          % (str((node("egg_date_l") or {}).get("t")),
             str((node("egg_today_tag") or {}).get("t")),
             str((node("egg_today_title") or {}).get("t"))))
    return 0


STATES = {"todo": st_todo, "mood": st_mood, "goal": st_goal, "egg": st_egg}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in STATES:
        print("用法: python tools/shotfeat.py <%s>" % "|".join(STATES))
        return 2
    return STATES[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
