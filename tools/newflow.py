#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新建日程流程 + 格子点击/选中高亮的实测驱动（run_new.sh 调用）。

为什么单独写一个驱动：这条流程是「点格子 → 点标题框 → 打字 → 按 id 点重复按钮
→ 保存」，每一步的坐标都随面板开合而变，写死坐标必然扑空。所以所有坐标一律
从 /snap 现取。

它同时是**唯一**验证「格子可点」的流程 —— 42 个格子按钮是无 id 的静态
ButtonFlat，只能按「空文本 + 52×52」的几何特征识别（见 cells() 的说明）。
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, ".runtime")
OCTO = os.environ.get("OCTO", "D:/Projects/OctoScript-App-Design-Flow/tools/octo")
PY = sys.executable

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))


def cells(s=None):
    """42 个格子按钮。

    ⚠️ 它们是**无 id** 的静态 ButtonFlat（只需 on_click，不需要 ui.xxx 引用），
       所以只能用几何特征认：空文本 + 高 52 + 宽 52（±4，含 DPI 取整）。
       ⚠️ /snap 的 r 是 **4 元数组 [x, y, w, h]**，不是字典。
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


def center(n):
    r = n["r"]
    return r[0] + r[2] / 2.0, r[1] + r[3] / 2.0


def shot(tag):
    out = os.path.join(OUT, "evidence", "nf-%s.png" % tag)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run([PY, OCTO, "shot", str(e2e.PORT), out, "--settle", "0.9"],
                   capture_output=True)
    return out


def px_at(png, lx, ly):
    import zoom
    w, h, ch, buf = zoom.read_png(png)
    sc = w / 412.0
    o = (int(ly * sc) * w + int(lx * sc)) * ch
    return "#%02x%02x%02x" % (buf[o], buf[o + 1], buf[o + 2])


def node_by_id(i, s=None):
    for n in (s if s is not None else e2e.snap()):
        if n.get("i") == i:
            return n
    return None


def text_of(i):
    n = node_by_id(i)
    return str(n.get("t")) if n else None


def btn_by_text(t):
    for n in e2e.snap():
        if n.get("ty") in ("Button", "ButtonFlat") and (n.get("t") or "").strip() == t:
            return n
    return None


def click_btn(t):
    n = btn_by_text(t)
    if not n:
        print("  !! 找不到按钮 %r" % t)
        return False
    e2e.click_node(n)
    time.sleep(0.45)
    return True


print("=== A 格可点 + 点中的格子被高亮（画布画出来，不依赖动画器）===")
cs = cells()
check("识别到 42 个格子按钮", len(cs) == 42, "实得 %d" % len(cs))
if len(cs) != 42:
    sys.exit(1)
e2e.click(*center(cs[15]))
time.sleep(0.9)
nd = node_by_id("nd_input")
check("点格子打开新建面板且日期预填 2026-09-15",
      bool(nd) and "2026-09-15" in str(nd.get("t")), str(nd.get("t")) if nd else "无输入框")
cs2 = cells()
p = shot("sel")
check("第 15 格底 = c_sel_bg #f6dcc7", px_at(p, *center(cs2[15])) == "#f6dcc7",
      "实得 %s" % px_at(p, *center(cs2[15])))
check("相邻第 14 格仍白底 #ffffff", px_at(p, *center(cs2[14])) == "#ffffff",
      "实得 %s" % px_at(p, *center(cs2[14])))

print("=== B 写标题 + 重复点到「每年」+ 保存 ===")
e2e.click_node(node_by_id("nt_input"))
time.sleep(0.3)
e2e.type_text("妈妈生日")
time.sleep(0.5)
check("标题已写入", "妈妈生日" in str((node_by_id("nt_input") or {}).get("t")),
      str((node_by_id("nt_input") or {}).get("t")))
seen = []
for _ in range(4):
    # 文案每次都变（不重复→每天→每周→每月→每年），所以按 **id** 点
    n = node_by_id("nr_btn")
    e2e.click_node(n)
    time.sleep(0.4)
    seen.append(text_of("nr_btn"))
print("     重复按钮文案序列:", seen)
check("循环顺序正确", seen == ["每天", "每周", "每月", "每年"], str(seen))
click_btn("保存")
time.sleep(1.0)
s = e2e.snap()
check("指标「事件」= 1", text_of("metric_events") == "1", str(text_of("metric_events")))
st = [n.get("t") for n in s if str(n.get("t") or "").startswith("已新建")]
check("状态条报了新建且带「每年重复」", bool(st) and "每年重复" in str(st[0]), str(st[:1]))
check("「最近日程」= 09-15", text_of("metric_latest") == "09-15", str(text_of("metric_latest")))
cs3 = cells(s)
p = shot("saved")
# ★ 2026-10-01：期望值从「白底」改成「热度 1 的底色」。
#   低层原因：格子底色现在是**事件热度热力图**（1 个事件 → c_heat1 #fef8f4，
#   2 个 → c_heat2 #fcecdf …）。9-15 刚存了一条「妈妈生日」，所以它本来就**不该**是白的。
#   这条断言的真正意图是「选中态被清掉了」，因此判据改成
#   「不再是选中色 #f6dcc7」**且**「确实是热度 1 的底色」—— 比原来的白底断言更严，
#   顺带把热力图本身也钉住了（底色算错档位同样会红）。
bg15 = px_at(p, *center(cs3[15]))
check("保存后选中态已清（回热度 1 底色，既不是白底也不是选中色）",
      bg15 == "#fef8f4" and bg15 != "#f6dcc7",
      "实得 %s" % bg15)

print("=== C 再选一格 → 取消 → 选中态应清掉 ===")
e2e.click(*center(cs3[20]))
time.sleep(0.8)
cs4 = cells()
p = shot("sel2")
check("第 20 格被选中", px_at(p, *center(cs4[20])) == "#f6dcc7",
      "实得 %s" % px_at(p, *center(cs4[20])))
click_btn("取消")
time.sleep(0.8)
cs5 = cells()
p = shot("cancel")
check("取消后清掉选中态", px_at(p, *center(cs5[20])) == "#ffffff",
      "实得 %s" % px_at(p, *center(cs5[20])))

print("=== D 面板开着换日期不许丢字 / 翻月收起面板并清选中 ===")
e2e.click(*center(cs5[21]))
time.sleep(0.9)
nd = node_by_id("nd_input")
check("点第 21 格打开面板且日期 = 2026-09-21",
      bool(nd) and "2026-09-21" in str(nd.get("t")), str(nd.get("t")) if nd else "面板没开")
# D1：面板已经开着时再点别的格子 = 只换日期。
#     这条是防回归：pick_cell 原来直接调 open_new_on，而它无条件
#     `set_text("")` + `new_repeat = 0` —— 用户敲了标题再改日期，标题和
#     重复档位会被悄悄清掉（未保存输入的数据丢失）。
e2e.click_node(node_by_id("nt_input"))
time.sleep(0.3)
e2e.type_text("换日期不丢字")
time.sleep(0.5)
# 重复按钮的文案每次都变（不重复→每天→每周→每月→每年），只能按 **id** 连点。
# ⚠️ 不能写 click_btn("每年")：按钮此刻显示的还不是「每年」，按文本找必然扑空
#    （2026-09-30 就这么写过一次，报「找不到按钮 '每年'」）。
for _ in range(4):
    e2e.click_node(node_by_id("nr_btn"))
    time.sleep(0.4)
check("已把重复档位点到「每年」", text_of("nr_btn") == "每年", str(text_of("nr_btn")))
csD = cells()
e2e.click(*center(csD[24]))
time.sleep(0.9)
ndD = node_by_id("nd_input")
check("换格后日期已改到 2026-09-24",
      bool(ndD) and "2026-09-24" in str(ndD.get("t")), str(ndD.get("t")) if ndD else "面板没开")
tit = str((node_by_id("nt_input") or {}).get("t"))
check("换格后标题保留（不被清空）", "换日期不丢字" in tit, tit)
rep = str((node_by_id("nr_btn") or {}).get("t"))
check("换格后重复档位保留（不被退回不重复）", rep == "每年", rep)
# D2：翻月 → 面板必须一并收起。只清高亮不关面板会留下三方不一致：
#     面板写着 9-24、月历显示 10 月、格子上又没有高亮。
click_btn(">")
time.sleep(1.0)
cs7 = cells()
check("月份已翻到 10 月", text_of("month_title") == "2026 年 10 月", str(text_of("month_title")))
check("翻月把新建面板一并收起", node_by_id("nd_input") is None,
      "面板还在" if node_by_id("nd_input") else "")
p = shot("navclear")
check("翻月后同一格子无高亮", px_at(p, *center(cs7[21])) == "#ffffff",
      "实得 %s" % px_at(p, *center(cs7[21])))

print("=== E 每年重复要展开到明年（2027-09 有事件点，2026-10 没有）===")
# 从 2026-10 往后 11 个月 → 2027-09
subprocess.run([PY, os.path.join(ROOT, "tools", "e2e.py"), "months", "11"],
               capture_output=True)
time.sleep(0.8)
check("已到 2027 年 9 月", text_of("month_title") == "2027 年 9 月", str(text_of("month_title")))
p = shot("yearly-next")
out = subprocess.run([PY, os.path.join(ROOT, "tools", "e2e.py"), "dotcolor", p],
                     capture_output=True, text=True).stdout
kinds = [l for l in out.splitlines() if l.startswith("DOTKIND=")]
nev = (kinds[0].count("EVENT") if kinds else 0)
check("2027-09 出现事件点（每年规则确实展开到明年）", nev >= 1, kinds[0] if kinds else out[:120])

# 回到 2026-10：它不是每月重复，应该一个事件点都没有
subprocess.run([PY, os.path.join(ROOT, "tools", "e2e.py"), "months", "-11"],
               capture_output=True)
time.sleep(0.8)
check("已回到 2026 年 10 月", text_of("month_title") == "2026 年 10 月", str(text_of("month_title")))
p = shot("monthly-no")
out = subprocess.run([PY, os.path.join(ROOT, "tools", "e2e.py"), "dotcolor", p],
                     capture_output=True, text=True).stdout
kinds = [l for l in out.splitlines() if l.startswith("DOTKIND=")]
nev = (kinds[0].count("EVENT") if kinds else 0)
check("2026-10 没有事件点（不是每月/每天重复）", nev == 0, kinds[0] if kinds else out[:120])

print()
if FAILS:
    print("newflow 失败 %d 项：%s" % (len(FAILS), FAILS))
    sys.exit(1)
print("newflow 全部通过")
sys.exit(0)
