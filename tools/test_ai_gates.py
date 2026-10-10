#!/usr/bin/env python3
"""v0.5.0 AI 改期层 · 七道闸的离线判定夹具（不需要宿主、不需要真模型）

为什么要有这个
───────────────
`model.complete` 的**成功路径**本机验不了：card-host 不注册该服务，
真机又要求 v0.5.0 先提交进 App Hub 商店才能装上。
于是成功路径里**唯一能在本机验的部分**就是 `ai_verify()` 的判定逻辑 ——
模型给的东西会不会被正确放行、或被正确拦下。

⚠️ 本文件的性质要说清楚：**它是 `ai_verify` 的独立复刻**，不是宿主里跑的代码。
所以它验的是「判定规则本身对不对」，**验不到**「bundle 里的那份实现和这份一致」。
要补上后者，靠下面第 3 条：改完必须跑 `test_ai_gates.py --sync`，
它会从 main.splash 里抽出闸的原文字符串做逐字比对。

七道闸的语义（与 bundle/main.splash 的 ai_verify 逐条对应）
──────────────────────────────────────────────────────────
闸 1 形状   字段齐、类型对、时长为正
闸 2 身份   只能动规则引擎判定「可动」的那条
闸 3 日期   8 位、真实存在的日历日、偏移 -1..+7 天
闸 4 时段   起点<终点、不跨 24:00、对齐整分
闸 5 日历   不撞任何事件（含跨天与全天）
闸 6 同意   用户点采纳才写（在 apply_model_plan，不在本文件）
闸 7 复核   写入后冲突未减少则回滚（同上）

用法
────
  python3 tools/test_ai_gates.py           # 跑全部用例
  python3 tools/test_ai_gates.py --sync    # 顺便核对 bundle 里的原文字符串
"""
import sys, os, re

# ── 被测规则：从 ai_verify 复刻 ────────────────────────────────────

def ics_date_ok(raw):
    """复刻 bundle/main.splash 的 ics_date_ok。

    ⚠️ 与 bundle 同款的三道粗筛，顺序都不能改：
      ① `len(date_of(raw)) < 8` → 拒（是 `< 8`，不是 `!= 8`）
      ② `to_f64` 量级落在 [20000101, 20991231] → 非数字与少一位都会被拦
      ③ 按 days_in_month 判当天数（闰年由 days_in_month 自己处理）
    夹具早先写成 `len(day) != 8 or not day.isdigit()`，
    会把 `20261004T103000` 这类**合法**输入误判为非法 —— 与被测代码不一致，
    造出的红是假的。（真 bug 与假 bug 必须分清，否则会去改本来正确的代码。）
    """
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


def days_in_month(y, m):
    return [31, 29 if is_leap(y) else 28, 31, 30, 31, 30,
            31, 31, 30, 31, 30, 31][m - 1]


def is_leap(y):
    return (y % 4 == 0 and y % 100 != 0) or y % 400 == 0


def date_of(raw):
    """复刻 bundle/main.splash 的 date_of：剥掉尾部的 Z，取前 8 位。"""
    if raw is None:
        return ""
    if raw.endswith("Z"):
        raw = raw[:-1]
    return raw[:8]


def date_num(raw):
    """复刻 bundle/main.splash 的 date_num：date_of 之后 to_f64，NaN/过短都返回 -1。

    ⚠️⚠️ 早先这里写的是 `int(d) if len(d) == 8` —— **比被测代码更严格**：
    bundle 的 date_num 对 `20261004T103000` 这类完整 datetime 是**能**解析的
    （date_of 先取前 8 位），而夹具会返回 -1 ⇒ abs_start/abs_end 全成负数
    ⇒ 闸 5 的所有「撞车」用例集体假绿（夹具写错，被测代码反而是对的）。
    ⇒ **复刻这类解析函数时，宽度判断必须跟被测代码一致，多一分少一分都会造出假绿。**
    """
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


def ipart(x):
    return int(x)


def to_f64(x):
    """复刻 Splash 的 to_f64：空串/非数字得 NaN，而 NaN 与任何值比较为 false。"""
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def ai_verify(p, advice, events):
    """返回 None 表示放行；返回字符串表示拒绝原因。逐条对应 bundle 的 ai_verify。"""
    # 闸 1 形状
    if p is None:
        return "模型没有给出方案"
    if p.get("mover") is None or p.get("day") is None \
            or p.get("start") is None or p.get("end") is None:
        return "方案字段不全"
    s = to_f64(p["start"])
    e = to_f64(p["end"])
    if not (s >= 0):
        return "开始时刻不是数字"
    if not (e > s):
        return "结束时刻必须晚于开始时刻"
    if not advice:
        return "当前没有待处理的冲突"
    a = advice[0]
    # 闸 2 身份
    if p["mover"] != a["mover"]:
        return "只能移动规则引擎判定可动的那条"
    # 闸 3 日期
    day = str(p["day"])
    if len(day) != 8:
        return "日期必须是 8 位"
    if not ics_date_ok(day):
        return "日期 " + day + " 不是真实存在的日子"
    base = date_num(a["day"])
    off = date_num(day) - base
    if off < -1 or off > 7:
        return "目标日期离原日期太远（只允许 -1 到 +7 天）"
    # 闸 4 时段
    if s < 0 or e > 24 * 60:
        return "时段必须在一天之内"
    if s != ipart(s) or e != ipart(e):
        return "时段必须对齐到整分"
    # 闸 5 日历
    ss = date_num(day) * 1440 + s
    se = date_num(day) * 1440 + e
    for ev in events:
        if ev.get("status") == "CANCELLED":
            continue
        if ev["uid"] == p["mover"]:
            continue
        if ev.get("all_day"):
            if date_num(day) == date_num(ev["dtstart"]):
                return "这一天是全天事件，不能安排别的"
            continue
        if se <= abs_start(ev):
            continue
        if abs_end(ev) <= ss:
            continue
        return "与「" + ev["summary"] + "」重叠"
    return None


# ── 夹具数据 ───────────────────────────────────────────────────────

def fixture():
    """seed.ics(3) + conflict.ics(1) 导入后的事件库（run_conflict.sh 实测同款）。

    冲突：黑客松初赛截止 10:00-11:00（硬承诺，保留）
          复赛宣讲会   10:30-11:30（有约在前，可动）
    另有两块空档：09:00-10:00 与 11:30 之后。

    ⚠️⚠️ `dtstart` 必须是 **紧凑无分隔** 形式 `YYYYMMDDTHHMMSS`（可带 `Z`）——
       这不是笔误，是本应用真实存储的形态：`reschedule()` 写的是
       `dtstart: dp + "T" + clock_compact(h) + "00" + sfx`，其中 `dp = date_of(e.dtstart)`
       已经把 `Z` 摘掉了，UTC 标志单独存在 `start_utc` 里。
       夹具早先写成 `20261004T100000Z`，而 `date_num` 是「取 8 位前缀转数字」——
       带 `Z` 会让它取到 `20261004T` 这一串的子串失败 ⇒ 返回 -1 ⇒
       所有绝对分钟轴变成负数 ⇒ 闸 5 全部「不撞」，用例集体假绿。
       ⇒ **改这份夹具的 dtstart 前先读 reschedule() 的真实写法。**
    """
    advice = [{
        "mover": "rehearsal@oma", "mover_summary": "复赛宣讲会",
        "keeper_summary": "黑客松初赛截止", "day": "20261004",
        "dur": 60, "has_slot": True, "slot_start": 690, "slot_end": 750,
    }]
    events = [
        {"uid": "hackathon-deadline@oma", "summary": "黑客松初赛截止",
         "dtstart": "20261004T100000", "start_minutes": 600, "end_minutes": 660,
         "all_day": False, "status": ""},
        {"uid": "rehearsal@oma", "summary": "复赛宣讲会",
         "dtstart": "20261004T103000", "start_minutes": 630, "end_minutes": 690,
         "all_day": False, "status": ""},
        {"uid": "oma-sync@oma", "summary": "OMA 队伍同步会",
         "dtstart": "20261005T143000", "start_minutes": 870, "end_minutes": 960,
         "all_day": False, "status": ""},
        {"uid": "freeze@oma", "summary": "复赛版本冻结",
         "dtstart": "20261007T120000", "start_minutes": 720, "end_minutes": 780,
         "all_day": False, "status": ""},
    ]
    return advice, events


def plan(**kw):
    """造一个模型方案；未给的字段取「合法默认值」，这样每个用例只测一处。"""
    base = {"mover": "rehearsal@oma", "day": "20261004",
            "start": 750, "end": 810, "reason": "挪到冲突结束之后"}
    base.update(kw)
    return base


# ── 用例 ───────────────────────────────────────────────────────────

def cases():
    A, E = fixture()
    c = []
    add = lambda want, name, p, advice=None, events=None: c.append(
        (name, want, p, advice if advice is not None else A, events if events is not None else E))

    # —— 放行 ——
    add(None, "① 合法方案（挪到 12:30-13:30）", plan())
    add(None, "② 挪到前一天", plan(day="20261003", start=600, end=660))
    add(None, "③ 挪到一周后（偏移 +7 边界）", plan(day="20261011", start=600, end=660))
    add(None, "④ 跨 24:00 前最后 60 分钟", plan(start=1380, end=1440))

    # —— 闸 1 形状 ——
    add("模型没有给出方案", "⑤ 方案为 nil", None)
    add("方案字段不全", "⑥ 缺 end", {k: v for k, v in plan().items() if k != "end"})
    add("方案字段不全", "⑦ day 为 null",
        {**plan(), "day": None})
    add("开始时刻不是数字", "⑧ start 非数字", plan(start="下午"))
    add("结束时刻必须晚于开始时刻", "⑨ end < start", plan(start=810, end=750))
    add("结束时刻必须晚于开始时刻", "⑩ end == start（零时长）",
        plan(start=750, end=750))
    # -1 不是 >= 0 ⇒ 在 Splash 里 `!(s >= 0)` 为真，先撞「开始时刻不是数字」，
    # 走不到闸 4 的「时段必须在一天之内」。两处都能拦下，这里只钉住实际路径。
    add("开始时刻不是数字", "⑪ start 为负（-1）", plan(start=-1, end=810))
    add("开始时刻不是数字", "⑫ start 为空串", plan(start=""))

    # —— 闸 2 身份 ——
    add("只能移动规则引擎判定可动的那条", "⑬ 试图动「保留方」",
        plan(mover="hackathon-deadline@oma"))
    add("只能移动规则引擎判定可动的那条", "⑭ uid 不存在",
        plan(mover="ghost@oma"))
    add("只能移动规则引擎判定可动的那条", "⑮ uid 大小写不同",
        plan(mover="Rehearsal@oma"))

    # —— 闸 3 日期 ——
    add("日期必须是 8 位", "⑯ 日期 7 位", plan(day="2026100"))
    add("日期必须是 8 位", "⑰ 日期 9 位", plan(day="202610041"))
    add("日期 20260230 不是真实存在的日子", "⑱ 2 月 30 日", plan(day="20260230"))
    add("日期 20260229 不是真实存在的日子", "⑲ 平年 2 月 29 日", plan(day="20260229"))
    add("日期 20261301 不是真实存在的日子", "⑳ 13 月", plan(day="20261301"))
    add("日期 20261000 不是真实存在的日子", "㉑ 日为 00", plan(day="20261000"))
    add("日期 19991004 不是真实存在的日子", "㉒ 年份越界", plan(day="19991004"))
    add("日期 abc10304 不是真实存在的日子", "㉓ 非纯数字", plan(day="abc10304"))
    add("目标日期离原日期太远（只允许 -1 到 +7 天）", "㉔ 提前 2 天",
        plan(day="20261002", start=600, end=660))
    add("目标日期离原日期太远（只允许 -1 到 +7 天）", "㉕ 推迟 8 天",
        plan(day="20261012", start=600, end=660))

    # —— 闸 4 时段 ——
    add("时段必须在一天之内", "㉖ 结束超过 24:00", plan(start=1400, end=1500))
    add("时段必须对齐到整分", "㉗ 结束 12:30:30", plan(start=750, end=810.5))
    add("时段必须在一天之内", "㉘ 正好 24:00 起", plan(start=1440, end=1500))

    # —— 闸 5 日历 ——
    add("与「黑客松初赛截止」重叠", "㉙ 撞保留方（部分重叠）",
        plan(start=630, end=690))
    add("与「黑客松初赛截止」重叠", "㉚ 完全覆盖保留方",
        plan(start=600, end=660))
    # mover 自己（复赛宣讲会 10:30-11:30）必须被排除，否则「挪回自己的原时段」
    # 这种等价改期会被误判成撞车。用例把事件库换成「mover 独占一天」，
    # 目标时段正好是它自己的老位置 ⇒ 只有不排除自己才会被拦。
    solo = [
        {"uid": "rehearsal@oma", "summary": "复赛宣讲会",
         "dtstart": "20261004T103000", "start_minutes": 630, "end_minutes": 690,
         "all_day": False, "status": ""},
    ]
    add(None, "㉛ mover 自己被正确排除（挪回原时段不算撞车）",
        plan(start=630, end=690), advice=A, events=solo)
    add("与「OMA 队伍同步会」重叠", "㉜ 撞次日事件",
        plan(day="20261005", start=870, end=930))

    # 边界：紧邻不重叠（end == 别人 start）应该放行
    add(None, "㉝ 紧贴前一条之后（end == 对方 start）", plan(start=660, end=720))
    add(None, "㉞ 紧贴后一条之前", plan(start=780, end=840))

    # CANCELLED 的事件不该拦
    ev_cancel = [dict(E[0]), dict(E[1]), dict(E[2], status="CANCELLED")]
    add(None, "㉟ 已取消的事件不拦", plan(start=870, end=930),
        advice=A, events=ev_cancel)

    # 全天事件
    allday = [dict(E[0]), dict(E[1]),
              {"uid": "trip@oma", "summary": "外出", "dtstart": "20261008T000000",
               "start_minutes": 0, "end_minutes": 1439, "all_day": True, "status": ""}]
    add("这一天是全天事件，不能安排别的", "㊱ 撞全天事件当天",
        plan(day="20261008", start=600, end=660), advice=A, events=allday)
    add(None, "㊲ 全天事件在别天，不拦",
        plan(day="20261004", start=750, end=810), advice=A, events=allday)

    # 无冲突时
    add("当前没有待处理的冲突", "㊳ advice 为空",
        plan(), advice=[], events=E)

    return c


# ── 与 bundle 里的原文字符串核对（--sync）──────────────────────────

LITERAL = [
    "模型没有给出方案", "方案字段不全", "开始时刻不是数字",
    "结束时刻必须晚于开始时刻", "当前没有待处理的冲突",
    "只能移动规则引擎判定可动的那条", "日期必须是 8 位",
    "不是真实存在的日子", "目标日期离原日期太远（只允许 -1 到 +7 天）",
    "时段必须在一天之内", "时段必须对齐到整分",
    "这一天是全天事件，不能安排别的", "重叠",
]


def sync_check(path=".runtime/bundle-v050/main.splash"):
    """把夹具里用到的拒绝理由与 bundle 的 ai_verify 逐字比对。

    路径默认指向开发副本；找不到就**跳过而不是判失败** ——
    `bundle/`（当前是已发布的 v0.4.1）里还没有 AI 层，这很正常。
    想强制指定：`python3 tools/test_ai_gates.py --sync <main.splash 路径>`
    """
    if len(sys.argv) > 2 and not sys.argv[2].startswith("--"):
        path = sys.argv[2]
    if not os.path.exists(path):
        print("SKIP  找不到 %s（bundle 尚无 AI 层时属正常）" % path)
        return 0
    src = open(path, encoding="utf-8").read()
    body = re.search(r"fn ai_verify\(p\) \{.*?\n\}", src, re.S)
    if not body:
        # ⚠️ 必须 SKILL 而不是 FAIL：`bundle/` 现在是已发布的 v0.4.1，
        # 它合法地没有 AI 层。判失败会让 static_gate 卡死所有回归脚本
        #（run_e2e / run_conflict / … 全部先跑 static_gate）。
        print("SKIP  %s 里没有 ai_verify（该 bundle 尚无 AI 层）" % path)
        return 0
    body = body.group(0)
    missing = [s for s in LITERAL if s not in body]
    if missing:
        print("FAIL  以下字符串在 bundle 的 ai_verify 里不存在：")
        for s in missing:
            print("        " + s)
        return 1
    print("OK    %d 条拒绝理由与 %s 的 ai_verify 逐字一致" % (len(LITERAL), path))
    return 0


# ── main ───────────────────────────────────────────────────────────

def main():
    do_sync = "--sync" in sys.argv
    if do_sync:
        rc = sync_check()
        if rc:
            return rc

    ok = fail = 0
    for name, want, p, advice, events in cases():
        got = ai_verify(p, advice, events)
        if got == want:
            ok += 1
        else:
            fail += 1
            print("FAIL  %s" % name)
            print("        期望 %r" % (want if want else "放行"))
            print("        实得 %r" % (got if got else "放行"))
    print("")
    print("七道闸判定: PASS=%d FAIL=%d" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())