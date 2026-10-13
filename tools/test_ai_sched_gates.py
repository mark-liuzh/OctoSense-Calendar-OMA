#!/usr/bin/env python3
"""v0.5.5 AI 排程层 · 离线判定夹具（不需要宿主、不需要真模型）

为什么要有这个
───────────────
`model.complete` 的成功路径本机验不了：card-host 不注册该服务。
但我们可以离线验证"模型返回的解析结果"在写入前要经过哪些校验：
  · 时间字符串 "HH:MM" 是否正确转成分钟
  · 目标日期是否真实存在
  · 目标时段是否与已有事件冲突（含全天事件）
  · 自动挑选替代时段的逻辑是否正确

用法
────
  python3 tools/test_ai_sched_gates.py
"""
import sys
import os

# ── 复刻 bundle/main.splash 的工具函数 ───────────────────────────────

def date_of(raw):
    if raw is None:
        return ""
    if raw.endswith("Z"):
        raw = raw[:-1]
    return raw[:8]


def ipart(x):
    return int(x)


def to_f64(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def is_leap(y):
    return (y % 4 == 0 and y % 100 != 0) or y % 400 == 0


def days_in_month(y, m):
    return [31, 29 if is_leap(y) else 28, 31, 30, 31, 30,
            31, 31, 30, 31, 30, 31][m - 1]


def ics_date_ok(raw):
    """复刻 bundle/main.splash 的 ics_date_ok。"""
    d = date_of(raw)
    if len(d) < 8:
        return False
    n = to_f64(d)
    if not (n >= 20000101):
        return False
    if not (n <= 20991231):
        return False
    y = ipart(to_f64(d[0:4]))
    m = ipart(to_f64(d[4:6]))
    dd = ipart(to_f64(d[6:8]))
    if not (m >= 1 and m <= 12):
        return False
    return dd >= 1 and dd <= days_in_month(y, m)


def valid8(d8):
    if d8 is None:
        return False
    if len(str(d8)) != 8:
        return False
    return ics_date_ok(d8)


def date_num(raw):
    if raw is None:
        return -1
    d = date_of(raw)
    if len(d) < 8:
        return -1
    n = to_f64(d)
    if not (n >= 0):
        return -1
    return n


def abs_start(ev):
    return date_num(ev["dtstart"]) * 1440 + ev["start_minutes"]


def abs_end(ev):
    return abs_start(ev) + (ev["end_minutes"] - ev["start_minutes"])


def time_to_min(t):
    """复刻 bundle/main.splash 的 time_to_min。"""
    s = str(t)
    if len(s) < 4 or len(s) > 5:
        return -1
    c0 = s.find(":")
    if c0 < 0:
        return -1
    h = to_f64(s[0:c0])
    m = to_f64(s[c0 + 1:])
    if not (h >= 0 and h <= 23):
        return -1
    if not (m >= 0 and m <= 59):
        return -1
    return ipart(h * 60 + m)


def check_conflict_for_slot(day, s, e, skip_uid, events):
    """复刻 bundle/main.splash 的 check_conflict_for_slot。"""
    out = []
    if skip_uid is None:
        skip_uid = ""
    for ev in events:
        if ev.get("status") == "CANCELLED":
            continue
        if ev["uid"] == skip_uid:
            continue
        if ev.get("all_day"):
            if date_num(ev["dtstart"]) == to_f64(day):
                out.append(ev["summary"])
            continue
        ss = to_f64(day) * 1440 + s
        se = to_f64(day) * 1440 + e
        if se <= abs_start(ev):
            continue
        if abs_end(ev) <= ss:
            continue
        out.append(ev["summary"])
    return out


def add_days(d8, n):
    """复刻 bundle/main.splash 的 add_days。"""
    if not valid8(d8):
        return d8
    y = ipart(to_f64(d8[0:4]))
    m = ipart(to_f64(d8[4:6]))
    d = ipart(to_f64(d8[6:8]))
    k = n
    while k > 0:
        d = d + 1
        if d > days_in_month(y, m):
            d = 1
            m = m + 1
        if m > 12:
            m = 1
            y = y + 1
        k = k - 1
    while k < 0:
        d = d - 1
        if d < 1:
            m = m - 1
            if m < 1:
                m = 12
                y = y - 1
            d = days_in_month(y, m)
        k = k + 1
    return "%04d%02d%02d" % (y, m, d)


def propose_slots_for_draft(day, dur, events):
    """复刻 bundle/main.splash 的 propose_slots_for_draft（简化版）。"""
    out = []
    d = day
    for _ in range(8):
        if len(out) >= 3:
            break
        t = 540  # 09:00
        while t + dur <= 1260:  # 21:00
            if len(check_conflict_for_slot(d, t, t + dur, "", events)) == 0:
                out.append({"d8": d, "start": t, "end": t + dur})
                if len(out) >= 3:
                    break
                t = t + dur
            else:
                t = t + 30
        d = add_days(d, 1)
    return out


# ── 夹具数据 ─────────────────────────────────────────────────────────

def fixture_events():
    """一个典型的事件库：全天事件 + 定时事件。"""
    return [
        {"uid": "all-day-1@oma", "summary": "国庆假期",
         "dtstart": "20261001", "start_minutes": 0, "end_minutes": 1440,
         "all_day": True, "status": ""},
        {"uid": "meeting@oma", "summary": "周会",
         "dtstart": "20261013T100000", "start_minutes": 600, "end_minutes": 660,
         "all_day": False, "status": ""},
        {"uid": "review@oma", "summary": "代码评审",
         "dtstart": "20261013T140000", "start_minutes": 840, "end_minutes": 900,
         "all_day": False, "status": ""},
    ]


# ── 用例 ─────────────────────────────────────────────────────────────

def cases():
    events = fixture_events()
    c = []
    add = lambda want, name, fn, *args: c.append((name, want, fn, args))

    # time_to_min
    add(600, "time_to_min 10:00", time_to_min, "10:00")
    add(0,   "time_to_min 00:00", time_to_min, "00:00")
    add(1439, "time_to_min 23:59", time_to_min, "23:59")
    add(-1,  "time_to_min 24:00 非法", time_to_min, "24:00")
    add(-1,  "time_to_min 文字非法", time_to_min, "abc")
    add(-1,  "time_to_min 空串非法", time_to_min, "")

    # valid8 / ics_date_ok
    add(True,  "valid8 20261013", valid8, "20261013")
    add(False, "valid8 20260230 非法", valid8, "20260230")
    add(False, "valid8 19990101 越界", valid8, "19990101")

    # check_conflict_for_slot：空档
    add([], "10-13 09:00-10:00 无冲突",
         check_conflict_for_slot, "20261013", 540, 600, "", events)

    # check_conflict_for_slot：撞定时事件
    add(["周会"], "10-13 10:00-11:00 撞周会",
         check_conflict_for_slot, "20261013", 600, 660, "", events)

    # check_conflict_for_slot：撞全天事件
    add(["国庆假期"], "10-01 09:00-10:00 撞全天国庆假期",
         check_conflict_for_slot, "20261001", 540, 600, "", events)

    # check_conflict_for_slot：skip_uid 自身不算冲突
    add([], "skip_uid 自身不算冲突",
         check_conflict_for_slot, "20261013", 600, 660, "meeting@oma", events)

    # check_conflict_for_slot：CANCELLED 不算冲突
    events_cancelled = events + [
        {"uid": "cancelled@oma", "summary": "已取消会议",
         "dtstart": "20261013T100000", "start_minutes": 600, "end_minutes": 660,
         "all_day": False, "status": "CANCELLED"}
    ]
    add([], "CANCELLED 事件不算冲突",
         check_conflict_for_slot, "20261013", 600, 660, "", events_cancelled)

    # propose_slots_for_draft：10-13 只剩 11:30 之后或次日
    slots = propose_slots_for_draft("20261013", 60, events)
    add(3, "propose_slots_for_draft 返回最多 3 个", lambda x: len(x), slots)
    add(True, "propose_slots_for_draft 第一个在 10-13 11:30 或之后",
         lambda x: x[0]["start"] >= 690 if x else False, slots)

    return c


# ── 运行 ─────────────────────────────────────────────────────────────

def run():
    PASS = 0
    FAIL = 0
    for name, want, fn, args in cases():
        try:
            got = fn(*args)
        except Exception as e:
            print(f"  FAIL {name} —— 异常：{e}")
            FAIL += 1
            continue
        if got == want:
            print(f"  OK   {name}")
            PASS += 1
        else:
            print(f"  FAIL {name} —— 期望 {want!r}，实得 {got!r}")
            FAIL += 1
    print(f"\n结果：{PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
