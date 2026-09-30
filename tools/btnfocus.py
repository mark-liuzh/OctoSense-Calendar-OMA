#!/usr/bin/env python3
"""静态防线：每个 ButtonFlat 都必须补齐 focus 态属性。

背景（2026-09-30 用户报的 bug）
──────────────────────────────────────────────────────────────────
点一下按钮就获得键盘焦点（宿主 `widgets/src/button.rs` 的
`Hit::FingerDown` 里有 `cx.set_key_focus(...)`，受 Rust 私有字段
`grab_key_focus` 控制，脚本关不掉），而按钮的填充色是**四态混色**：

    fill = color.mix(color_focus, focus)
                .mix(color_hover, hover)
                .mix(color_down,  down)
                .mix(color_disabled, disabled)

只写 `color` / `color_hover` / `color_down` 而漏掉 `color_focus` 时，
按钮一被点就落到主题默认的 `theme.color_outset_focus`（浅色）：
浅底按钮「整块消失」、深底按钮「变白」。描边与文字同理
（`border_color_focus` / `draw_text.color_focus`）。

运行时已被 shots.sh 的像素断言覆盖，但那是**截图链路**上的，
手工开窗口点两下不会触发。所以需要这一层静态防线。

判定规则
──────────────────────────────────────────────────────────────────
对每个 ButtonFlat 的 `draw_bg +: {...}` / `draw_text +: {...}` 直接一层：
  · 写了 `color`            → 必须写 `color_focus`
  · 写了 `border_size` 且非 0 → 必须写 `border_color_focus`
另外：按钮块内**一个 color_focus 都没有** → 直接报错（漏改整块）。

用法:
  python tools/btnfocus.py [bundle/main.splash]
退出码: 0 = 全过；1 = 有漏写的按钮（会打印行号与缺的属性名）。
"""
import io
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else "bundle/main.splash"


def mask(text):
    """把字符串字面量与 // 注释替换成空格（长度不变）。

    避免被字符串里的花括号（ICS 模板、提示文案）带偏括号配对。
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
    if not text.startswith(tok, i):
        return False
    if i > 0 and (text[i - 1].isalnum() or text[i - 1] in "_."):
        return False
    j = i + len(tok)
    if j < len(text) and (text[j].isalnum() or text[j] == "_"):
        return False
    return True


def scan_depth0(text, start, end, tok):
    """tok 出现在直接一层（depth==0）的位置 —— 子控件的同名属性不算。"""
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


src = io.open(P, encoding="utf-8").read()
m = mask(src)
PAT = re.compile(r"(?<![A-Za-z_0-9])ButtonFlat(\s*:=)?\s*\{")

problems = []
n_btn = 0
for mo in PAT.finditer(m):
    brace = mo.end() - 1
    body = (mo.end(), match_close(m, brace))
    n_btn += 1
    ln = src.count("\n", 0, mo.start()) + 1

    # 按钮体内**任意深度**都没有 color_focus → 整块漏改。
    #   ⚠️ 这里不能用 scan_depth0：color_focus 写在 draw_bg 体内（第二层），
    #      而 scan_depth0 只看直接一层 —— 用它会把 16 个按钮全判成漏改（踩过）。
    if "color_focus" not in m[body[0]:body[1]]:
        problems.append((ln, "整个按钮没有任何 color_focus"))
        continue

    db = patch_body(m, *body, "draw_bg")
    if db:
        if scan_depth0(m, *db, "color") and not scan_depth0(m, *db, "color_focus"):
            problems.append((ln, "draw_bg 有 color 但缺 color_focus"))
        bs = depth0_value(m, *db, "border_size")
        try:
            has_border = bs is not None and float(bs) != 0.0
        except ValueError:
            has_border = False
        if has_border and not scan_depth0(m, *db, "border_color_focus"):
            problems.append((ln, "draw_bg 有 border_size 但缺 border_color_focus"))

    dt = patch_body(m, *body, "draw_text")
    if dt and scan_depth0(m, *dt, "color") and not scan_depth0(m, *dt, "color_focus"):
        problems.append((ln, "draw_text 有 color 但缺 color_focus"))

print("ButtonFlat: %d 个" % n_btn)
if problems:
    print("\n有 %d 处漏写 focus 属性：" % len(problems))
    for ln, why in sorted(problems):
        print("  L%-6d %s" % (ln, why))
    print("\n→ 点一下按钮它就会掉到主题默认的浅色（看着像「消失」）。")
    sys.exit(1)
print("focus 属性齐全 ✓")
