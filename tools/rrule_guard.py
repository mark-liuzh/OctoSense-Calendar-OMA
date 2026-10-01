#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""带修饰的 RRULE **不得被乱标** —— 负向回归（run_new.sh 的一步）。

背景（2026-09-30 自检抓到，注释与实现矛盾）：
  导入的 ICS `RRULE` 是**原样存下来**的（解析分支 `cur.rrule = value.trim()`），
  而 marked_days 对所有非空 rrule 都调 repeat_hits 去展开。repeat_hits 当初写的是
  `r.split("FREQ=MONTHLY").len() > 1` —— 它**连修饰一起匹配**，于是：

    · `FREQ=WEEKLY;INTERVAL=2`（隔周一次）  → 被当成**每周**标
    · `FREQ=MONTHLY;BYDAY=-1FR`（月末周五）→ 被按「和起始日同号」标，日期根本不对
    · `FREQ=YEARLY;UNTIL=…`                → 忽略 UNTIL，过期了还继续往后标

  而 README 与 repeat_hits 的注释都写着「表达不出来就不标」「宁可少标，不可乱标」。
  修法：rrule_plain() 白名单精确匹配 —— 只展开本应用自己写出的四种朴素规则。

本脚本用两个**故意带修饰**的事件来当那条防线的哨兵：
  A  `FREQ=WEEKLY;INTERVAL=2`  DTSTART 2026-09-02
  B  `FREQ=YEARLY;UNTIL=20261231` DTSTART 2026-09-11

断言（全部靠**截图回读的事件点像素**，不看状态文本）：
  2026-09  事件点 == 2   （就是两个 DTSTART 当天；修复前是 6：2/9/16/23/30 + 11）
  2027-09  事件点 == 0   （UNTIL 已过；修复前 B 会继续标 9/11）

⚠️ 第二条同时守住「不要矫枉过正」：如果为了让修饰规则不标而干脆把展开整个关掉，
   那 run_new.sh 里 newflow 段的「每年重复展开到次年」断言会立刻失败。
   两条一起看，才说明白名单是**精确**的。
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, ".runtime")
OCTO = os.environ.get("OCTO", "D:/Projects/OctoScript-App-Design-Flow/tools/octo")
PY = sys.executable
ICS = os.path.join(OUT, "rrule-guard.ics")
FAILS = []

ICS_BODY = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "PRODID:-//OMA//OctoSense rrule guard//CN\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:guard-biweekly-20260902@octosense.test\r\n"
    "DTSTART;VALUE=DATE:20260902\r\n"
    "SUMMARY:隔周例会\r\n"
    "RRULE:FREQ=WEEKLY;INTERVAL=2\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:guard-until-20260911@octosense.test\r\n"
    "DTSTART;VALUE=DATE:20260911\r\n"
    "SUMMARY:年度复盘\r\n"
    "RRULE:FREQ=YEARLY;UNTIL=20261231\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))


def run(*args):
    return subprocess.run([PY, os.path.join(ROOT, "tools", "e2e.py")] + [str(a) for a in args],
                          capture_output=True, text=True)


def node(i, s=None):
    for n in (s if s is not None else e2e.snap()):
        if n.get("i") == i:
            return n
    return None


def text_of(i):
    n = node(i)
    return str(n.get("t")) if n else None


def btn(t, s=None):
    for n in (s if s is not None else e2e.snap()):
        if n.get("ty") in ("Button", "ButtonFlat") and (n.get("t") or "").strip() == t:
            return n
    return None


def click_btn(t):
    n = btn(t)
    if not n:
        return False
    e2e.click_node(n)
    time.sleep(0.5)
    return True


def shot(tag):
    out = os.path.join(OUT, "evidence", "rg-%s.png" % tag)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run([PY, OCTO, "shot", str(e2e.PORT), out, "--settle", "0.9"],
                   capture_output=True)
    return out


def event_dots(tag, want_y, want_m):
    """当前月历里「事件点」（赤陶 #b4531f）的个数。

    ⚠️ 先把当前月份验一遍再取色。**必须这样**：一旦翻月没成功，采样会落在
       错误的月份上 —— 那可能给出「0 个事件点」这种**恰好符合期望**的假通过
       （2026-09-30 就踩到了：goto 失败停在 10 月，断言 UNTIL 那条反而过了）。
    """
    c = cur_month()
    if c != (want_y, want_m):
        return -1, "月份不对：当前 %s，期望 (%d, %d)" % (c, want_y, want_m)
    p = shot(tag)
    out = run("dotcolor", p).stdout
    for ln in out.splitlines():
        if ln.startswith("DOTKIND="):
            return ln[len("DOTKIND="):].count("EVENT"), ln[len("DOTKIND="):]
    return -1, out[:120]


def cur_month():
    """月历标题 → (年, 月)。标题形如「2026 年 10 月」。

    ⚠️ 用「把所有数字段收集起来」，不能只累加**连续**数字：
       标题里年月之间隔着一个「年」字，读到 2026 就断了 —— 第一版就是栽在这，
       返回 None 让翻月循环一次都没执行（而日志只显示「已翻到 … None」，
       看着像翻月按钮坏了）。
    """
    t = text_of("month_title") or ""
    runs, cur = [], ""
    for ch in t:
        if ch.isdigit():
            cur += ch
        elif cur:
            runs.append(cur)
            cur = ""
    if cur:
        runs.append(cur)
    if len(runs) < 2:
        return None
    return int(runs[0]), int(runs[1])


def goto(y, m):
    """翻到指定月份。用标题做闭环，不假设起点。"""
    for _ in range(40):
        c = cur_month()
        if c is None:
            return False
        if c == (y, m):
            return True
        delta = (y * 12 + m) - (c[0] * 12 + c[1])
        run("months", 1 if delta > 0 else -1)
        time.sleep(0.45)
    return False


def main():
    # ── 1) 清空事件库（清空按钮在关于页里）──────────────────────────────
    # 先清干净：上一步写进来的「妈妈生日（每年 9/15）」会在 2026-09 多出一个
    # 事件点，把计数搅浑。实测踩过：不清空时断言差 1，会误判成修复失效。
    run("about")
    time.sleep(0.7)
    if not click_btn("清空事件库"):
        print("FAIL: 找不到「清空事件库」（关于页没打开？）")
        return 1
    time.sleep(0.5)
    # 标题栏那个「关于」按钮是 toggle，再点一次关掉关于页
    # （面板自己的按钮写「收起」，标题栏那个**一直**写「关于」）
    if btn("关于"):
        e2e.click_node(btn("关于"))
        time.sleep(0.5)
    check("事件库已清空", (text_of("metric_events") or "") == "0",
          "指标事件 = %s" % text_of("metric_events"))

    # ── 2) 灌入两个带修饰 RRULE 的事件 ────────────────────────────────
    with open(ICS, "w", encoding="utf-8", newline="") as f:
        f.write(ICS_BODY)
    if not node("entry"):
        run("open")
        time.sleep(0.8)
    r = run("fill", ICS)
    check("ICS 已灌入输入框", "已灌入" in r.stdout, r.stdout.strip().splitlines()[-1:] or "")
    r = run("parse")
    check("解析到 2 个事件", "解析 2 个" in r.stdout, r.stdout.strip().splitlines()[-1:] or "")
    r = run("write")
    time.sleep(0.5)
    check("写入后事件数 = 2", (text_of("metric_events") or "") == "2",
          "指标事件 = %s" % text_of("metric_events"))

    # ── 3) 2026-09：只应有 2 个事件点（两个 DTSTART 当天）─────────────
    check("已翻到 2026 年 9 月", goto(2026, 9), "当前 %s" % (cur_month(),))
    n, kinds = event_dots("2026-09", 2026, 9)
    check("2026-09 事件点 == 2（修饰规则未被展开）", n == 2,
          "实得 %d  EVENT 点：%s" % (n, kinds))
    if n != 2:
        print("     修复前这里会是 6：隔周被当成每周 → 2/9/16/23/30，加 UNTIL 事件 9/11")
        print("     若实得 0 —— 说明矫枉过正，把合法展开也关掉了（看 newflow 的 E 段）")

    # ── 4) 2027-09：UNTIL 已过，一个点都不该有 ────────────────────────
    check("已翻到 2027 年 9 月", goto(2027, 9), "当前 %s" % (cur_month(),))
    n2, kinds2 = event_dots("2027-09", 2027, 9)
    check("2027-09 事件点 == 0（UNTIL 生效，不越界标）", n2 == 0,
          "实得 %d  EVENT 点：%s" % (n2, kinds2))

    print()
    if FAILS:
        print("rrule-guard 失败 %d 项：%s" % (len(FAILS), FAILS))
        return 1
    print("rrule-guard 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
