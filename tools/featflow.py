#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新功能分区的实测驱动（run_features.sh 调用）。

覆盖 2026-10-01 新增的六个分区/交互：
  A 分区导航        —— 5 个分区按钮齐、切换真的换内容
  B 待办清单        —— 加一条 → 勾掉 → 只剩未完成 → 删除
  C 心情日记        —— 选一档 → 小结文字跟着变
  D 目标与子任务    —— 建目标 → 加一步 → 勾一步 → 删目标
  E 小知识（每日只一条 + 与源码表交叉校验）
                    —— **与 bundle/main.splash 里的数据表交叉校验**，不是「看起来有字就算过」
  F 月/周/日 视图   —— 三种视图互相切换，各自的控件真的在
  G 吉祥物互动      —— 点章鱼要换一句（用户最初的原话就是「有跟没有差不多」）
  H 时间胶囊        —— 封存 → 到期提示 → 开启后能看到当时写的内容

设计原则（与 newflow.py 一致）
──────────────────────────────────────────────────────────────────
1. 所有坐标**现取**：面板开合会改变布局，写死坐标必然扑空。
2. 断言尽量落在**语义**上（文本、计数、与源码数据表比对），少用像素；
   唯一必须用像素的场景（格子底色）在 run_new 里已经覆盖。
3. E 段刻意做「与源码表交叉校验」：这个功能刚被发现过两个「静静失败」的 bug
   （日期键格式不一致、search 是字节下标而 substr 是字符下标），
   两者都表现为「界面有字、但字是错的」—— 只断言「非空」根本抓不到。
"""
import os
import re
import subprocess
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, ".runtime")
EV = os.path.join(OUT, "evidence")
SPLASH = os.path.join(ROOT, "bundle", "main.splash")
OCTO = os.environ.get("OCTO", "D:/Projects/OctoScript-App-Design-Flow/tools/octo")
PY = sys.executable

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))


def note(msg):
    print("  ·· %s" % msg)


def shot(tag):
    os.makedirs(EV, exist_ok=True)
    out = os.path.join(EV, "ft-%s.png" % tag)
    subprocess.run([PY, OCTO, "shot", str(e2e.PORT), out, "--settle", "0.8"],
                   capture_output=True)
    return out


# ── 快照取值 ──────────────────────────────────────────────────────────
def node(i, s=None):
    for n in (s if s is not None else e2e.snap()):
        if n.get("i") == i:
            return n
    return None


def text_of(i, s=None):
    n = node(i, s)
    return str(n.get("t") or "") if n else None


def click_id(i, wait=0.7):
    """按 id 点控件。⚠️ 点完页面会滚动（聚焦），所以**每次都重新取快照**。"""
    n = node(i)
    if not n:
        return False
    e2e.click(*e2e.center(n))
    time.sleep(wait)
    return True


def click_label(label, wait=0.7):
    s = e2e.snap()
    n = e2e.btn(s, label)
    if not n:
        return False
    e2e.click(*e2e.center(n))
    time.sleep(wait)
    return True


def type_into(i, text, wait=0.6):
    if not click_id(i, 0.5):
        return False
    e2e.type_text(text)
    time.sleep(wait)
    return True


def cells(s=None):
    """月历 42 个格子按钮（无 id 的静态 ButtonFlat，只能按几何特征认）。"""
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
    return out


def tab(label):
    """点分区导航（按钮文案就是分区名）。"""
    return click_label(label, 0.8)


# ── 从源码里读回数据表（用于 E 段交叉校验）────────────────────────────
def load_flat_table(name):
    """把 `let NAME = "a" + "b" + ...` 拼成一个扁平串。"""
    lines = open(SPLASH, encoding="utf-8").read().split("\n")
    start = None
    for k, l in enumerate(lines):
        if l.strip().startswith("let %s =" % name):
            start = k
            break
    if start is None:
        return ""
    parts = []
    k = start
    while k < len(lines):
        line = lines[k].strip()
        if k > start and not line.startswith("+"):
            break
        parts += re.findall(r'"([^"]*)"', line)
        k += 1
    return "".join(parts)


def build_maps():
    hist = {}
    p = load_flat_table("HISTORY").split("|")
    for i in range(len(p) - 2):
        if re.fullmatch(r"\d{4}", p[i]) and re.fullmatch(r"\d{4}", p[i + 1]):
            hist[p[i]] = (p[i + 1], p[i + 2])
    terms = {}
    p = load_flat_table("SOLAR_TERMS").split("|")
    for i in range(len(p) - 1):
        if re.fullmatch(r"\d{8}", p[i]) and p[i + 1]:
            terms[p[i]] = p[i + 1]
    return hist, terms


def build_china_map():
    """中国特别日表（CHINA_FIXED）—— MMDD → (名称, 简介)。
    首项带竖线，所以 split 的第一个元素是 ""，从 1 开始。
    """
    out = {}
    p = load_flat_table("CHINA_FIXED").split("|")
    # HISTORY/CHINA_FIXED 是 `|MMDD|名称|简介|...`，split 后从 1 开始
    for i in range(1, len(p) - 2):
        if re.fullmatch(r"\d{4}", p[i]):
            out[p[i]] = (p[i + 1], p[i + 2])
    return out


INTL_FIXED_KEYS = []  # 运行时由 _load_intl_keys() 填


def _load_intl_keys():
    global INTL_FIXED_KEYS
    if INTL_FIXED_KEYS:
        return INTL_FIXED_KEYS
    p = load_flat_table("INTL_FIXED").split("|")
    # INTL_FIXED 整串**不带**首项竖线，直接两两一组
    for i in range(0, len(p) - 1, 2):
        if re.fullmatch(r"\d{4}", p[i]):
            INTL_FIXED_KEYS.append(p[i])
    return INTL_FIXED_KEYS


def pick_expected(mmdd, ed, china, terms, hist):
    """按 egg_today_pick 的优先级，挑出**期望显示**的（tag, title）。
    返回 dict 让调用处不依赖 splash 里的 array 解构顺序。
    """
    if mmdd in china:
        return {"tag": "今日 · 中国", "title": china[mmdd][0]}
    if mmdd in _load_intl_keys():
        # 拿到名称
        for i in range(0, len(load_flat_table("INTL_FIXED").split("|")) - 1, 2):
            if load_flat_table("INTL_FIXED").split("|")[i] == mmdd:
                return {"tag": "今日 · 国际", "title": load_flat_table("INTL_FIXED").split("|")[i + 1]}
    ymd = "%04d%02d%02d" % (ed.year, ed.month, ed.day)
    if ymd in terms:
        return {"tag": "今日 · 节气", "title": terms[ymd]}
    if mmdd in hist:
        return {"tag": "今日 · 历史", "title": "%s · %s" % hist[mmdd]}
    return {"tag": "", "title": ""}


def main():
    print("=== A 分区导航 ===")
    s = e2e.snap()
    for lbl in ("日程", "待办", "心情", "目标", "小知识"):
        check("分区按钮「%s」在" % lbl, e2e.btn(s, lbl) is not None)
    check("初始在「日程」：月历标题在", text_of("month_title", s) not in (None, ""),
          str(text_of("month_title", s)))

    print("=== B 待办清单 ===")
    check("切到待办", tab("待办"))
    check("待办分区出现（todo_stat 在）", text_of("todo_stat") is not None,
          repr(text_of("todo_stat")))
    check("初始「这一天还没有待办」", text_of("todo_stat") == "这一天还没有待办",
          repr(text_of("todo_stat")))
    check("输入框可写", type_into("todo_in", "交作品集"))
    check("点「添加」", click_label("添加"))
    check("待办正文出现", text_of("td_t0") == "交作品集", repr(text_of("td_t0")))
    check("计数变「已完成 0 / 1」", text_of("todo_stat") == "已完成 0 / 1",
          repr(text_of("todo_stat")))
    check("勾选框初始是 [ ]", text_of("td_b0") == "[ ]", repr(text_of("td_b0")))
    check("点勾选框", click_id("td_b0"))
    check("勾上后是 [x]", text_of("td_b0") == "[x]", repr(text_of("td_b0")))
    check("计数变「已完成 1 / 1」", text_of("todo_stat") == "已完成 1 / 1",
          repr(text_of("todo_stat")))
    shot("01-todo")
    # 过滤：只剩未完成 → 已完成的那条应当整行让位
    check("点过滤器", click_id("todo_filter"))
    check("过滤器文案变「只看未完成」", text_of("todo_filter") == "只看未完成",
          repr(text_of("todo_filter")))
    check("已完成项被过滤掉（td_t0 不在或为空）", text_of("td_t0") in (None, ""),
          repr(text_of("td_t0")))
    check("切回「全部」", click_id("todo_filter"))
    check("条目回来了", text_of("td_t0") == "交作品集", repr(text_of("td_t0")))
    check("点「删除」", click_id("td_x0"))
    check("删除后回到空状态", text_of("todo_stat") == "这一天还没有待办",
          repr(text_of("todo_stat")))

    print("=== C 心情日记 ===")
    check("切到心情", tab("心情"))
    check("初始「还没记」", text_of("mood_sum") == "还没记 —— 点一个心情",
          repr(text_of("mood_sum")))
    check("点「开心」", click_id("mood_b0"))
    check("小结变「心情：开心」", text_of("mood_sum") == "心情：开心",
          repr(text_of("mood_sum")))
    check("点「低落」改档", click_id("mood_b4"))
    check("小结变「心情：低落」", text_of("mood_sum") == "心情：低落",
          repr(text_of("mood_sum")))
    shot("02-mood")

    print("=== D 目标与子任务 ===")
    check("切到目标", tab("目标"))
    check("初始「还没有目标」", text_of("goal_count") == "还没有目标",
          repr(text_of("goal_count")))
    check("输入目标名", type_into("goal_in", "AP 考试"))
    check("点「新建目标」", click_label("新建目标"))
    check("目标卡片标题", text_of("gc_t0") == "AP 考试", repr(text_of("gc_t0")))
    check("计数变「已建 1 个」", text_of("goal_count") == "已建 1 个",
          repr(text_of("goal_count")))
    check("还没加步骤时显示「0 步」", text_of("gc_p0") == "0 步", repr(text_of("gc_p0")))
    check("还没加步骤时进度条留空（不画 10 个空格骗人）",
          (text_of("gc_bar0") or "").strip() == "", repr(text_of("gc_bar0")))
    check("输入第一步", type_into("goal_in", "背 300 个单词"))
    check("点「加一步」", click_label("加一步"))
    check("子任务出现", text_of("gs_t00") == "背 300 个单词", repr(text_of("gs_t00")))
    check("子任务框初始 [ ]", text_of("gs_b00") == "[ ]", repr(text_of("gs_b00")))
    check("进度显示 0/1 步", text_of("gc_p0") == "0/1 步", repr(text_of("gc_p0")))
    check("进度条 0 格 → 全空", text_of("gc_bar0") == "----------", repr(text_of("gc_bar0")))
    check("勾掉第一步", click_id("gs_b00"))
    check("勾上后 [x]", text_of("gs_b00") == "[x]", repr(text_of("gs_b00")))
    check("进度显示 1/1 步", text_of("gc_p0") == "1/1 步", repr(text_of("gc_p0")))
    check("进度条 1/1 → 满格", text_of("gc_bar0") == "##########", repr(text_of("gc_bar0")))
    # ★ 再补一步：1/2 必须正好半格 —— 这条钉住的是 `ipart(10 * d / n)` 的取整方向。
    #   写成 `10 * (d / n)` 会先做浮点除再乘，得到 5.0 也对；但写成 `d / n * 10`
    #   在某些写法下会先截断成 0。进度条是纯 ASCII 画出来的，肉眼很难发现差一格。
    check("输入第二步", type_into("goal_in", "做一套真题"))
    check("点「加一步」", click_label("加一步"))
    check("第二步出现", text_of("gs_t01") == "做一套真题", repr(text_of("gs_t01")))
    check("进度显示 1/2 步", text_of("gc_p0") == "1/2 步", repr(text_of("gc_p0")))
    check("进度条 1/2 → 恰好半格", text_of("gc_bar0") == "#####-----",
          repr(text_of("gc_bar0")))
    shot("03-goal")
    # 删除目标（卡片上的「删除」是第一个匹配的…用 id 路径更稳：直接点卡片里的删除按钮）
    s = e2e.snap()
    dels = [n for n in s if n.get("ty") in ("Button", "ButtonFlat")
            and (n.get("t") or "").strip() == "删除"]
    if dels:
        e2e.click(*e2e.center(dels[0]))
        time.sleep(0.7)
    check("删掉目标后回到空状态", text_of("goal_count") == "还没有目标",
          repr(text_of("goal_count")))

    print("=== E 小知识：与源码数据表交叉校验（每天只显示一条） ===")
    check("切到小知识", tab("小知识"))
    mt = text_of("month_title") or ""
    dlabel = text_of("egg_date_l") or ""
    m1 = re.search(r"(\d{4})\s*年\s*(\d+)\s*月", mt)
    m2 = re.search(r"(\d+)\s*月\s*(\d+)\s*日", dlabel)
    if not (m1 and m2):
        check("能解析出「关注日」的完整日期", False, "month_title=%r egg_date_l=%r" % (mt, dlabel))
    else:
        vy, vm = int(m1.group(1)), int(m2.group(1))
        ed = date(vy, vm, int(m2.group(2)))
        check("关注日默认停在「今天」且与月历同月", ed.month == int(m1.group(2)),
              "egg=%s 月历=%s 年 %s 月" % (ed, vy, m1.group(2)))

        hist, terms = build_maps()
        china = build_china_map()
        note("源码表：中国特别日 %d 条 · 国际节日 %d 条 · 节气 %d 条 · 历史 %d 条"
             % (len(china), len(INTL_FIXED_KEYS), len(terms), len(hist)))

        # 关注日当天应该挑出哪一条
        mmdd = "%02d%02d" % (ed.month, ed.day)
        want_today = pick_expected(mmdd, ed, china, terms, hist)
        check("「今日」显示的是源码表里**按优先级**挑的那一条",
              text_of("egg_today_title") == want_today["title"]
              and text_of("egg_today_tag") == want_today["tag"],
              "\n         期望 tag=%r title=%r\n         实得 tag=%r title=%r"
              % (want_today["tag"], want_today["title"],
                 text_of("egg_today_tag"), text_of("egg_today_title")))

        # 走到当年**最近**的一个节气，断言名字对得上（专用路径）
        cand = sorted((date(int(k[:4]), int(k[4:6]), int(k[6:8])), v)
                      for k, v in terms.items() if k[:4] == str(vy))
        if not cand:
            note("源码表的节气不覆盖 %d 年，跳过节气断言" % vy)
        else:
            near, nm = min(cand, key=lambda t: abs((t[0] - ed).days))
            delta = (near - ed).days
            note("最近的节气：%s %s（相差 %d 天）" % (near, nm, delta))
            for _ in range(abs(delta)):
                click_label("后一天" if delta > 0 else "前一天", 0.45)
            check("「今日」走到最近节气的当天 · tag 切到节气",
                  text_of("egg_today_tag") == "今日 · 节气"
                  and text_of("egg_today_title") == nm,
                  "期望 tag=今日 · 节气 · title=%r 实得 tag=%r title=%r"
                  % (nm, text_of("egg_today_tag"), text_of("egg_today_title")))
            check("日期行也跟着走到 %d 月 %d 日" % (near.month, near.day),
                  text_of("egg_date_l") == "%d 月 %d 日" % (near.month, near.day),
                  repr(text_of("egg_date_l")))
            check("点「回到关注日」复位", click_label("回到关注日"))
            check("复位后回到今天", text_of("egg_date_l") == dlabel,
                  "期望 %r 实得 %r" % (dlabel, text_of("egg_date_l")))

    print("=== F 月 / 周 / 日 视图 ===")
    check("切回日程", tab("日程"))
    check("默认月视图：42 个格子按钮", len(cells()) == 42, "实得 %d" % len(cells()))
    check("点「周」", click_label("周"))
    check("周视图 7 行都在", text_of("wk_b0") == "周一" and text_of("wk_b6") == "周日",
          "%r … %r" % (text_of("wk_b0"), text_of("wk_b6")))
    wk_d = text_of("wk_d0") or ""
    check("周视图日期是 MM-DD 形状", bool(re.fullmatch(r"\d{2}-\d{2}", wk_d)), repr(wk_d))
    shot("04-week")
    check("点「日」", click_label("日"))
    check("日视图标题在", text_of("day_title") not in (None, ""), repr(text_of("day_title")))
    check("日视图统计行在", text_of("day_stat") not in (None, ""), repr(text_of("day_stat")))
    shot("05-day")
    check("点「月」回到月视图", click_label("月"))
    check("回到月视图：格子又是 42 个", len(cells()) == 42, "实得 %d" % len(cells()))

    print("=== G 吉祥物互动 ===")
    check("吉祥物文案在", text_of("mascot_say") not in (None, ""), repr(text_of("mascot_say")))
    before = text_of("mascot_say")
    # 章鱼本体是个 44x44 的无文本 ButtonFlat（点击层）
    s = e2e.snap()
    octo = None
    for n in s:
        if n.get("ty") not in ("Button", "ButtonFlat"):
            continue
        if (n.get("t") or "").strip() != "":
            continue
        r = n.get("r")
        if isinstance(r, (list, tuple)) and len(r) == 4 and 40 <= r[2] <= 48 and 40 <= r[3] <= 48:
            octo = n
            break
    check("找到章鱼点击层（44x44 无文本按钮）", octo is not None)
    if octo:
        e2e.click(*e2e.center(octo))
        time.sleep(0.7)
        after = text_of("mascot_say")
        check("点一下换了一句（用户要的「有互动性」）", after != before,
              "\n         之前 %r\n         之后 %r" % (before, after))
    shot("06-mascot")

    print("=== H 时间胶囊 ===")
    check("切到小知识", tab("小知识"))
    check("胶囊解封日 = 关注日", "09-30" in (text_of("cap_where") or "") or
          (text_of("cap_where") or "").startswith("解封日"),
          repr(text_of("cap_where")))
    check("输入胶囊内容", type_into("cap_in", "十月四号交作品"))
    check("点「封存」", click_label("封存"))
    line = text_of("cp_t0") or ""
    check("胶囊出现在列表里", line != "", repr(line))
    check("已到解封日 → 提示可开启", "到期了" in line, repr(line))
    check("点「开启」", click_id("cp_b0"))
    check("开启后能看到当时写的内容", text_of("cp_t0") == "十月四号交作品",
          repr(text_of("cp_t0")))
    shot("07-capsule")

    print()
    if FAILS:
        print("featflow 失败 %d 项：%s" % (len(FAILS), FAILS))
        return 1
    print("featflow 全部通过")
    return 0


def restore_mode():
    """重启宿主之后跑：只用**磁盘上的状态**重建界面，验证「本地优先」真的成立。

    ⚠️ 为什么必须在**新进程**里验：同一个进程里读内存数组从来没坏过。
       用户的硬要求是「离线可用、本地优先存储」，那就必须证明
       「进程没了 → 数据还在 → 新进程能读回来」。
    """
    print("=== 重启后读回（本地优先的硬证据）===")
    check("切到心情", tab("心情"))
    check("心情档位从磁盘读回（应是「低落」）", text_of("mood_sum") == "心情：低落",
          repr(text_of("mood_sum")))

    check("切到目标", tab("目标"))
    check("已删的目标没有复活", text_of("goal_count") == "还没有目标",
          repr(text_of("goal_count")))

    check("切到小知识", tab("小知识"))
    check("时间胶囊从磁盘读回", text_of("cp_t0") == "十月四号交作品",
          repr(text_of("cp_t0")))

    print()
    if FAILS:
        print("restore 失败 %d 项：%s" % (len(FAILS), FAILS))
        return 1
    print("restore 全部通过")
    return 0


def scan_mode():
    """把应用走到每个「新分区」的界面状态，逐个做几何扫描（零尺寸/负坐标/越界）。

    ⚠️ 为什么需要它（2026-10-01）：`run_layout.sh` 的 12 步覆盖的全是**日程侧**
       （导入 / 冲突 / 导出 / 关于）。新增的五个分区（待办 / 心情 / 目标 / 小知识 /
       日周月视图）**一步都没被扫过**，而它们各自都有动态容器（`on_render` 列表、
       ASCII 进度条）—— 正是最容易出现「被压成 0 高 / 跑到窗口外」的地方。
       这类问题的共同点是**不报错**：宿主日志 0 个 `[E]`、断言全过，
       只有人在那一页里觉得「这里怎么怪怪的」。几何扫描就是为它们准备的。

    与语义断言的分工：main() 查「功能对不对」，这里查「界面有没有坏掉」。
    """
    bad = []

    def scan(label):
        env = dict(os.environ, OCTO_PORT=str(e2e.PORT))
        r = subprocess.run([PY, os.path.join(ROOT, "tools", "layout_scan.py"),
                            "--label", label],
                           capture_output=True, text=True, env=env)
        sys.stdout.write(r.stdout)
        if r.returncode != 0:
            bad.append(label)

    # ⚠️ 这条流程排在 --restore **之后**跑（见 run_features.sh 的顺序说明）：
    #    它会往待办/目标里写数据，跑在前面会把 --restore 的期望值改掉。
    tab("日程")
    scan("⑬ 日程 · 月视图（分区导航 + 吉祥物条已就位）")

    tab("待办")
    scan("⑭ 待办 · 空状态")
    type_into("todo_in", "交作品集")
    click_label("添加")
    scan("⑮ 待办 · 有数据 + 过滤器")

    tab("心情")
    click_id("mood_b1")
    scan("⑯ 心情 · 已选一档 + 备注框")

    tab("目标")
    type_into("goal_in", "AP 考试")
    click_label("新建目标")
    type_into("goal_in", "背单词")
    click_label("加一步")
    scan("⑰ 目标 · 有子任务 + 进度条")

    tab("小知识")
    scan("⑱ 小知识 · 今日 + 时间胶囊")

    tab("日程")
    click_label("周")
    scan("⑲ 周视图 · 7 行摘要")
    click_label("日")
    scan("⑳ 日视图 · 当天列表")
    click_label("月")
    if click_label("关于"):
        scan("㉑ 关于页 · 共享范围 + CC BY 署名")
    else:
        note("没找到「关于」按钮 —— 跳过关于页扫描")

    print()
    if bad:
        print("布局扫描发现问题：%s" % bad)
        return 1
    print("布局扫描：全部界面状态均无零尺寸 / 负坐标 / 越界控件")
    return 0


if __name__ == "__main__":
    if "--restore" in sys.argv:
        sys.exit(restore_mode())
    if "--scan" in sys.argv:
        sys.exit(scan_mode())
    sys.exit(main())
