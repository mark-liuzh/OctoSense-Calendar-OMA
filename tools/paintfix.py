#!/usr/bin/env python3
"""把「用 View 画背景」的地方换成真正能绘制的控件。

背景（2026-09-30 实测 + 源码核实）
──────────────────────────────────────────────────────────────────
makepad 的 `View` 是 `ViewBase {}` —— **既没有 `show_bg: true`，也没有带
`pixel` 的 `draw_bg`**（widgets/src/view_ui.rs:5）。所以

    View{... draw_bg +: {color: c_ok border_radius: 2.0}}

里那句 `draw_bg` 只是往一个**永远不会被绘制的** shader 上写了个颜色，
一个字都画不出来。项目里所有「用 View 画背景」的地方都是白干的：

  · 今天格的实心墨底高亮        · 日历格子的事件点 / 放假绿点 / 小黑点
  · 说明行前面的图例点          · 状态条前面的项目符号
  · 空状态那个 36px 空心圆环    · 事件卡片左侧的彩色色条
  · 冲突条 / 预览条 / 状态面板的有色底与描边

为什么一直没被发现：这个设计几乎是单色的 —— 大量 `c_card` / `c_paper`
白底画在白纸上，画不出来也看不出来；只有上面列的那些**有色**元素是真丢了。
（`Hr` / `SolidView` / `RoundedView` / `ButtonFlat` 这些**自己**声明了
`show_bg: true` + `pixel` 的控件才能画。）

映射规则
──────────────────────────────────────────────────────────────────
  · 宽高都 ≤ 8 的小方块  → `CircleView`（把 border_radius 归 0 → 自动取
                            半径 = min(w,h)/2，是圆而不是圆角方块）
  · 其余需要背景的 View  → `RoundedView`（color / border_radius / border_size /
                            border_color 全支持，且**无阴影**，不像 RoundedShadowView
                            会默认带 20px 阴影、还会撑大自己的 rect）
  · `ScrollYView` 不动（它需要滚动能力；页面底色本来就由窗口给，视觉上没问题）

用法:
  python tools/paintfix.py            # dry-run，只打印将要做的修改
  python tools/paintfix.py --write    # 落盘
"""
import io
import re
import sys

P = "bundle/main.splash"
WRITE = "--write" in sys.argv


def mask(text):
    """把字符串字面量与 // 注释替换成空格（长度不变）。

    避免被字符串里的花括号（ICS 模板、正则、提示文案）带偏括号配对。
    """
    out = list(text)
    n = len(text)
    i = 0
    while i < n:
        c = text[i]
        if c in "\"'":
            q = c
            out[i] = " "
            i += 1
            while i < n:
                if text[i] == "\\":
                    out[i] = " "
                    i += 1
                    if i < n:
                        out[i] = " "
                        i += 1
                    continue
                if text[i] == q:
                    out[i] = " "
                    i += 1
                    break
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
            continue
        i += 1
    return "".join(out)


src = io.open(P, encoding="utf-8").read()
m = mask(src)
PAT = re.compile(r"(?<![A-Za-z_0-9])View(\s*:=)?\s*\{")


def match_close(text, open_pos):
    depth = 0
    j = open_pos
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise ValueError("大括号不配对")


def _tok_at(text, i, tok):
    """text 在 i 处是不是一个独立的标识符 tok（两侧不是标识符字符）。"""
    if not text.startswith(tok, i):
        return False
    if i > 0 and (text[i - 1].isalnum() or text[i - 1] in "_."):
        return False
    j = i + len(tok)
    if j < len(text) and (text[j].isalnum() or text[j] == "_"):
        return False
    return True


def scan_depth0(text, start, end, tok):
    """返回 [位置…]：tok 出现在**直接一层**（相对 start..end，depth==0）的位置。

    子控件里的同名属性处在 depth>=1，会被跳过 —— 这是关键，
    否则外层 View 会误认子控件的 draw_bg 是自己的。
    """
    hits = []
    depth = 0
    i = start
    while i < end:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0 and _tok_at(text, i, tok):
            hits.append(i)
        i += 1
    return hits


def depth0_value(text, start, end, key):
    """取直接一层上 `key: <标量>` 的值（不含嵌套块）。"""
    for i in scan_depth0(text, start, end, key):
        j = i + len(key)
        while j < end and text[j] in " \t":
            j += 1
        if j >= end or text[j] != ":":
            continue
        j += 1
        while j < end and text[j] in " \t":
            j += 1
        k = j
        while k < end and (text[k].isalnum() or text[k] in "._-"):
            k += 1
        return text[j:k]
    return None


def patch_body(text, start, end, key):
    """取直接一层上 `key +: { ... }` 那个花括号体的 (body_start, body_end)。"""
    for i in scan_depth0(text, start, end, key):
        j = i + len(key)
        while j < end and text[j] in " \t+:":
            j += 1
        if j < end and text[j] == "{":
            return j + 1, match_close(text, j)
    return None


edits = []          # (start, end, new_text, 说明)
for mo in PAT.finditer(m):
    brace = mo.end() - 1
    close = match_close(m, brace)
    body = (mo.end(), close)
    if not scan_depth0(m, *body, "draw_bg"):
        continue
    w = depth0_value(m, *body, "width") or ""
    h = depth0_value(m, *body, "height") or ""

    def small(v):
        try:
            return float(v) <= 8.0
        except ValueError:
            return False

    ln = src.count("\n", 0, mo.start()) + 1
    if small(w) and small(h):
        new = "CircleView"
        # CircleView 的半径 0 = 自动取 min(w,h)/2；原来写的 2.0 / 2.5 会
        # 让半径 ≥ 半边长，圆角矩形直接退化消失（这正是它一直没画出来的
        # 第二层原因，即使换成能画的控件也还是看不见）。
        pb = patch_body(m, *body, "draw_bg")
        if pb:
            for p in scan_depth0(m, *pb, "border_radius"):
                j = p + len("border_radius")
                while j < pb[1] and m[j] in " \t":
                    j += 1
                if j < pb[1] and m[j] == ":":
                    j += 1
                    while j < pb[1] and m[j] in " \t":
                        j += 1
                    k = j
                    while k < pb[1] and (m[k].isalnum() or m[k] in "._-"):
                        k += 1
                    edits.append((j, k, "0.0", "半径归零→自动圆"))
        edits.append((mo.start(), mo.start() + 4, new,
                      "小方块 %.1sx%.1s → 圆形" % (w or "?", h or "?")))
    else:
        edits.append((mo.start(), mo.start() + 4, "RoundedView",
                      "背景 %s" % (depth0_value(m, *body, "draw_bg") and "draw_bg" or "")))

print("共 %d 处替换：\n" % len([e for e in edits if e[3].startswith(("小方块", "背景"))]))
for start, end, txt, why in edits:
    if txt in ("0.0",):
        continue
    ln = src.count("\n", 0, start) + 1
    print("  L%-5d View → %-13s  %s" % (ln, txt, why))

out = src
for start, end, txt, why in sorted(edits, key=lambda e: -e[0]):
    out = out[:start] + txt + out[end:]

n_view = len(edits) - len([e for e in edits if e[2] == "0.0"])

if WRITE:
    io.open(P, "w", encoding="utf-8", newline="").write(out)
    print("\n已写入 %s" % P)
else:
    print("\n（dry-run，未写盘；加 --write 落盘）")

# ⚠️ 当门禁用：还有裸 View 带 draw_bg 就退出码 1，
#    这样 e2e / CI 能在「背景画不出来」重新溜进来时立刻报警。
sys.exit(1 if n_view else 0)
