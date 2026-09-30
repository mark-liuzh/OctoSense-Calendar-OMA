#!/usr/bin/env python3
"""运行时布局扫描：在 /snap 快照上找「肉眼难发现、但确实是坏掉」的控件。

为什么要它
──────────────────────────────────────────────────────────────────
`/snap` 给的是**可见控件**的布局后 rect（`r = [x, y, w, h]`）。
像素断言只能覆盖「我特意去取色的那几个点」，而布局错误往往出现在
别处：一个被压成 0 高的 Label、一个跑到窗口外的按钮 —— 它们不会让
任何断言失败，只会让人在某个页面里觉得「这里怎么怪怪的」。

检查项
──────────────────────────────────────────────────────────────────
  · 零尺寸：可见控件的 w 或 h <= 0（被完全压扁 —— 铁律说的「CJK 被
    裁成几条横」在极端情况下就是 h 变成个位数，这里先拦 0）
  · 负坐标：x 或 y < 0（跑到窗口左/上侧外面）
  · 水平越界：x + w > 窗口宽 + 容差（右侧被切）
  · 文本被切：Label/Button 的 rect 比它自己声明的宽还小很多（可选）

不检查「y 超出窗口底部」—— 页面是 ScrollYView，滚动区里的内容本来
就可以在视口外，那不算错。

用法:
  python tools/layout_scan.py [--port 8932] [--label 页面名]
退出码: 0 = 无异常；1 = 有异常（会打印清单）。
"""
import json
import os
import sys
import urllib.request

PORT = os.environ.get("OCTO_PORT", "8932")
LABEL = ""
args = sys.argv[1:]
for i, a in enumerate(args):
    if a == "--port" and i + 1 < len(args):
        PORT = args[i + 1]
    elif a == "--label" and i + 1 < len(args):
        LABEL = args[i + 1]

W_TOL = 1.0     # 亚像素舍入容差

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
status = json.load(op.open("http://127.0.0.1:%s/s" % PORT, timeout=10))
win = status["w"][0]
W, H = win["sz"][0], win["sz"][1]

d = json.load(op.open("http://127.0.0.1:%s/snap?q=1" % PORT, timeout=10))
items = d["s"]

issues = []
for it in items:
    r = it.get("r")
    if not r or len(r) != 4:
        issues.append(("r 字段异常", it, ""))
        continue
    x, y, w, h = r
    ty = it.get("ty", "?")
    txt = (it.get("t") or "").replace("\n", " ")[:26]
    tag = "%s %r" % (ty, it.get("i"))

    if w <= 0 or h <= 0:
        issues.append(("零尺寸", it, "w=%s h=%s" % (w, h)))
    if x < -W_TOL or y < -W_TOL:
        issues.append(("负坐标", it, "(x=%s y=%s)" % (x, y)))
    if x + w > W + W_TOL:
        issues.append(("右侧越界", it, "x+w=%.0f > 窗口 %d" % (x + w, W)))

head = "[%s] " % LABEL if LABEL else ""
print("%s窗口 %dx%d · 可见控件 %d · 异常 %d" % (head, W, H, len(items), len(issues)))
for why, it, extra in issues:
    txt = (it.get("t") or "").replace("\n", " ")[:26]
    print("  %-8s %-10s r=%-22s %s %s" % (why, it.get("ty"), it.get("r"), extra, txt))

sys.exit(1 if issues else 0)
