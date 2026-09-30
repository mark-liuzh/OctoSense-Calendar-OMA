#!/usr/bin/env python3
"""OctoSense 静态自检 · 函数前向引用

用法:
  python tools/deps.py                 # 默认检查一组关键函数
  python tools/deps.py bundle/main.splash a,b,c

────────────────────────────────────────────────────────────────────────
⚠️ 这个检查的结论在 2026-09-30 被**实测修正过一次**，别再按老结论改代码：

老结论（错）：函数体内引用「后面才定义」的函数一律报错 → 必须按依赖顺序排。

实测结论（对）：Splash 的函数名是**调用时解析**的。
  `refresh_all()` 定义在第 928 行，却调用第 1570 行的 `festival_note()`、
  第 1660 行的 `view_year()` —— 界面按月份正确变化，宿主日志零错误。
  所以「函数体里的前向引用」是**安全的**。deps.py 原来把它报成问题，
  上一次为了消掉这个假警报，把 `festival_mode_label` 硬挪到前面
  （白做一次重排，还让文件顺序变得不自然）。

真正的雷区只有一个：**建树时就会求值的表达式**。
  顶层 widget 声明里的属性值（`text:` / `width:` / `color:` / `body:` …）
  在**解析脚本、搭 UI 树的那一刻**就求值，那时后面的 fn 还没定义 → 报错。
  所以 `Label{text: "" + view_year() + " 年 " + ... }` 必须保证 view_year 在前。
  凡是被 `|| {` 包起来的（on_render / on_click / on_* 回调）都算运行时，
  里面的前向引用是安全的。

本工具因此输出两类：
  · BUILD FATAL —— 建树时求值的表达式里前向引用，**必须修**
  · RUNTIME OK  —— `fn` 体内或 `||` 闭包内的前向引用，可以用
"""
import io
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else "bundle/main.splash"
src = io.open(P, encoding="utf-8").read()
lines = src.split("\n")

# ── 收集 fn 定义：名称 -> 起始行 ────────────────────────────────────
fns = {}
order = []
for i, ln in enumerate(lines, 1):
    m = re.match(r"^fn ([a-z_0-9]+)\(", ln)
    if m:
        fns[m.group(1)] = i
        order.append((i, m.group(1)))

BS = chr(92)
Q1 = chr(34)
Q2 = chr(39)


def stripped(code):
    """去掉字符串字面量与行尾注释，避免把字符串里的括号/函数名当成代码。"""
    out = []
    q = None
    j = 0
    while j < len(code):
        ch = code[j]
        if q:
            if ch == BS:
                j += 2
                continue
            if ch == q:
                q = None
            j += 1
            continue
        if ch == Q1 or ch == Q2:
            q = ch
            j += 1
            continue
        if ch == "/" and j + 1 < len(code) and code[j + 1] == "/":
            break
        out.append(ch)
        j += 1
    return "".join(out)


# ── 逐行跟踪大括号，同时记录「这一行是不是运行时上下文」──────────────
# runtime 上下文 = 由 `fn ...` 行或含 `||` 的行打开的作用域。
# 只要**任意一层祖先**是运行时的，这一行就是运行时求值。
depth = 0
prof = []
runtime_stack = []
runtime_flags = []
for ln in lines:
    code = stripped(ln)
    opens = code.count("{")
    closes = code.count("}")
    line_is_rt = bool(re.match(r"^fn ", code.strip())) or ("||" in code)
    runtime_flags.append(any(runtime_stack) if runtime_stack else False)
    for _ in range(opens):
        runtime_stack.append(line_is_rt)
    for _ in range(closes):
        if runtime_stack:
            runtime_stack.pop()
    depth += opens - closes
    prof.append(depth)

# ── 函数体范围（用于第 2 段报告）────────────────────────────────────
bodies = {}
for idx, (start, name) in enumerate(order):
    end = order[idx + 1][0] - 1 if idx + 1 < len(order) else len(lines)
    bodies[name] = (start, end)

bad = 0

# ══ 检查 1：建树时求值的前向引用（致命）══════════════════════════════
# 判定一个调用点是不是「建树时求值」：
#   祖先作用域里没有任何 fn/|| 运行时块，**且**同一行里这个调用之前没出现 `||`。
# 后半句是必须的 —— 实测
#   `Label{text: "ok" on_click: || later() ...}`
# 是**单表达式闭包**（`||` 后面没有 `{`），只按「祖先是不是运行时块」判断会误报。
print("── 1. 建树时求值的前向引用（必须为 0）──")
for i, ln in enumerate(lines, 1):
    anc_rt = runtime_flags[i - 1]
    code = stripped(ln)
    for m in re.finditer(r"\b([a-z_][a-z_0-9]*)\s*\(", code):
        f = m.group(1)
        if f not in fns or fns[f] <= i:
            continue
        if anc_rt or ("||" in code[:m.start()]):
            continue                  # 运行时（fn 体内 / || 闭包内），安全
        print("  FATAL 第 %d 行调用 `%s()`，但它定义在第 %d 行 —— 建树时会报错"
              % (i, f, fns[f]))
        print("        %s" % ln.strip()[:100])
        bad += 1
if bad == 0:
    print("  0 处（顶层 widget 的属性表达式里只引用已定义过的函数）")

# ══ 检查 2：关键函数的依赖（运行时前向引用：安全，仅作提示）══════════
TARGETS = sys.argv[2].split(",") if len(sys.argv) > 2 else [
    "load", "refresh_all", "start_import", "confirm_import",
    "cancel_import", "toggle_import", "rescan_ui", "clear_all",
]
print("── 2. 关键函数的依赖（运行时解析，前向引用可用，仅列出）──")
for name in TARGETS:
    if name not in bodies:
        print("  MISSING %s" % name)
        continue
    s, e = bodies[name]
    called = []
    for i in range(s, e):
        for m in re.finditer(r"\b([a-z_][a-z_0-9]*)\s*\(", stripped(lines[i])):
            f = m.group(1)
            if f in fns and f != name:
                called.append((f, i + 1))
    seen = []
    for f, ln in called:
        if f in [x[0] for x in seen]:
            continue
        seen.append((f, ln))
    fwd = [f for f, ln in seen if fns[f] > s]
    bwd = [f for f, ln in seen if fns[f] < s]
    tag = ("前向 %s（运行时解析 OK）" % fwd) if fwd else "后向 %d 个" % len(bwd)
    print("  fn %-16s (line %4d)  %s" % (name, s, tag))

print()
print("结果：建树时前向引用 %d 处" % bad)
sys.exit(1 if bad else 0)
