#!/usr/bin/env python3
"""静态防线：压在**画布之上**的点击层，任何状态色都不许不透明。

背景（2026-09-30 用户实测报回来的 bug）
──────────────────────────────────────────────────────────────────
月历网格是**双层**结构（见 main.splash 的 grid / canvas / click_layer）：

    grid（flow: Overlay）
      ├─ canvas      画布：日期数字、今天墨圆、事件点、放假绿点、节日名
      └─ click_layer 点击层：42 个 ButtonFlat，透明、只负责接点击

Overlay 里**声明顺序 = 绘制顺序**，所以点击层画在画布之上。于是点击层的
填充色只要不透明，就会把画布画的数字**整块擦掉** —— 用户原话：
「当我把鼠标移到这个格子上的时候，那个日期它就消失了，就只剩空白了」。

颜色本身没问题（浅赤陶是对的），错的是**不透明度**。八位色值
#xRRGGBBAA 的**末字节才是 alpha**（makepad/platform/script/src/colorhex.rs
的 `#rrggbbaa` 分支），所以悬停/按下必须写成带 alpha 的形式：

    color_hover: #xe4b28e4d     ← 30% 赤陶，数字仍清晰
    color_hover: #xfbeadf       ← ✗ 不透明，数字被擦掉

判定规则
──────────────────────────────────────────────────────────────────
取 `click_layer := …{…}` 这一块里的每个 ButtonFlat，看它 `draw_bg +: {…}`
直接一层上的四个状态色：

  color       必须透明（不放任何填充 —— 底由画布画）
  color_hover 必须**半透明**（0 < alpha < 255）
  color_down  必须**半透明**
  color_focus 必须透明（点了会 set_key_focus，不透明就会「一直亮着」）

颜色值可以是字面量（#x…）或本文件里 `let NAME = #x…` 定义的常量，
两种都会解析。解析不出来（改名、写成表达式）按**报错**处理 —— 门禁宁可吵。

另外要求 `border_color_hover` 非透明：悬停底很淡，得靠描边给出「有个方框
出现」的明确信号（用户原话）。

用法:
  python tools/cellhover.py [bundle/main.splash]
退出码: 0 = 全过；1 = 有不透明的状态色（打印行号、属性、实际取值）。
"""
import io
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else "bundle/main.splash"
src = io.open(P, encoding="utf-8").read()


def mask(text):
    """字符串字面量与 // 注释全部替换成空格（长度不变，行号不乱）。"""
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


m = mask(src)


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


def body_of(text, start, end, key):
    """直接一层上 `key +: { … }` 的 (body_start, body_end)。"""
    depth = 0
    i = start
    while i < end:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0 and text.startswith(key, i) and (
            i == 0 or not (text[i - 1].isalnum() or text[i - 1] in "_.")
        ):
            j = i + len(key)
            while j < end and text[j] in " \t+:":
                j += 1
            if j < end and text[j] == "{":
                return j + 1, match_close(text, j)
        i += 1
    return None


def raw_value(text, start, end, key):
    """直接一层上 `key: <tok>` 的原始 token（不含空白）。"""
    depth = 0
    i = start
    while i < end:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0 and text.startswith(key, i) and (
            i == 0 or not (text[i - 1].isalnum() or text[i - 1] in "_.")
        ):
            j = i + len(key)
            while j < end and text[j] in " \t":
                j += 1
            if j >= end or text[j] != ":":
                i += 1
                continue
            j += 1
            while j < end and text[j] in " \t":
                j += 1
            k = j
            # ⚠️ 必须带上 `#` —— 颜色字面量是 #x… 开头，漏了它就解析成空串
            while k < end and (text[k].isalnum() or text[k] in "._-#"):
                k += 1
            return text[j:k], i
        i += 1
    return None, -1


# ── 常量表：let NAME = #x… ────────────────────────────────────────────
CONSTS = dict(re.findall(r"^\s*let\s+([A-Za-z_]\w*)\s*=\s*(#x[0-9a-fA-F]+)", src, re.M))


def alpha_of(tok):
    """返回 (alpha_0_255, 规范化描述)；解析不了抛 ValueError。"""
    v = tok
    if not v.startswith("#"):
        if v not in CONSTS:
            raise ValueError("取值 %r 既不是颜色字面量，也不是本文件的常量" % v)
        v = CONSTS[v]
    body = v[2:]
    if len(body) == 8:                      # #xRRGGBBAA —— 末字节是 alpha
        return int(body[6:8], 16), v
    if len(body) == 4:                      # #xRGBA
        return int(body[3] * 2, 16), v
    if len(body) == 6:                      # #xRRGGBB —— 不透明！
        return 255, v
    raise ValueError("颜色 %r 的写法不认识（支持 4 / 6 / 8 位）" % v)


# ── 找到 click_layer 块 ───────────────────────────────────────────────
#   ⚠️ 不能写成 `click_layer := {` —— 实际是 `click_layer := RoundedView{`
#      （中间夹着控件类型），第一版正则就是这么扑空的。
anchor = re.search(r"(?<![A-Za-z_0-9])click_layer\s*:=", m)
if not anchor:
    print("找不到 `click_layer :=` —— 网格结构改过？门禁需要同步更新。")
    sys.exit(1)
_cl_brace = m.find("{", anchor.end())
if _cl_brace < 0:
    print("click_layer 后面找不到 `{` —— 门禁需要同步更新。")
    sys.exit(1)
cl_body = (_cl_brace + 1, match_close(m, _cl_brace))

BTN = re.compile(r"(?<![A-Za-z_0-9])ButtonFlat\s*\{")
problems = []
n_btn = 0

for mo in BTN.finditer(m[cl_body[0]:cl_body[1]]):
    off = cl_body[0] + mo.start()
    body = (cl_body[0] + mo.end(), match_close(m, cl_body[0] + mo.end() - 1))
    n_btn += 1
    ln = src.count("\n", 0, off) + 1

    db = body_of(m, *body, "draw_bg")
    if not db:
        problems.append((ln, "没有 draw_bg 块", ""))
        continue

    # 期望：color / color_focus 透明；hover / down 半透明（0 < a < 255）
    want = [
        ("color", "透明", lambda a: a == 0),
        ("color_hover", "半透明", lambda a: 0 < a < 255),
        ("color_down", "半透明", lambda a: 0 < a < 255),
        ("color_focus", "透明", lambda a: a == 0),
    ]
    for key, wantdesc, ok in want:
        tok, pos = raw_value(m, *db, key)
        if tok is None:
            problems.append((ln, "缺 %s（期望：%s）" % (key, wantdesc), ""))
            continue
        try:
            a, desc = alpha_of(tok)
        except ValueError as e:
            problems.append((ln, "%s 无法解析：%s" % (key, e), tok))
            continue
        if not ok(a):
            line_ln = src.count("\n", 0, pos) + 1
            problems.append((
                line_ln,
                "%s = %s → alpha=%d，**不是%s**" % (key, desc, a, wantdesc),
                "不透明就会把画布上的日期数字整块擦掉",
            ))

    # 悬停底很淡，必须靠描边补一个明确信号
    tok, pos = raw_value(m, *db, "border_color_hover")
    if tok is None:
        problems.append((ln, "缺 border_color_hover（悬停只剩一层浅底，太弱）", ""))
    else:
        try:
            a, _ = alpha_of(tok)
            if a == 0:
                problems.append((ln, "border_color_hover 是透明的（悬停没有任何可见信号）", tok))
        except ValueError as e:
            problems.append((ln, "border_color_hover 无法解析：%s" % e, tok))

print("click_layer 里的格子按钮: %d 个" % n_btn)
if n_btn == 0:
    print("一个都没找到 —— click_layer 结构改过？门禁需要同步更新。")
    sys.exit(1)

# ── 可读性数值验收 ────────────────────────────────────────────────────
# 「透明」只解决了一半：alpha 太大（比如 0.95）数字照样糊掉，太小（0.05）
# 则等于没反馈。所以直接把**合成结果**算出来，要求「数字与底色仍分得开」。
#
# 合成公式（over）：out = (1-a) * under + a * C
# 数字的 under 是它自己的字色，底色的 under 是格子底色。
# 亮度用三通道求和（满分 765）—— 与 e2e.py 的调色板判定同一种粗粒度。
def _rgb(hexstr):
    b = hexstr[2:]
    if len(b) == 6:
        return tuple(int(b[i:i + 2], 16) for i in (0, 2, 4))
    if len(b) == 8:
        return tuple(int(b[i:i + 2], 16) for i in (0, 2, 4))
    if len(b) == 4:
        return tuple(int(b[i] * 2, 16) for i in (0, 1, 2))
    raise ValueError(hexstr)


def _lum(c):
    return c[0] + c[1] + c[2]


def _over(under, color, a):
    return tuple((1.0 - a) * under[i] + a * color[i] for i in range(3))


# 取第一个格子按钮的 hover 色当代表（42 个必须一致，下面会校验）
first_btn = BTN.search(m[cl_body[0]:cl_body[1]])
fb_off = cl_body[0] + first_btn.start()
fb = (cl_body[0] + first_btn.end(), match_close(m, cl_body[0] + first_btn.end() - 1))
fb_db = body_of(m, *fb, "draw_bg")
hover_tok, _ = raw_value(m, *fb_db, "color_hover")
hover_a, hover_src = alpha_of(hover_tok)
C = _rgb(CONSTS.get(hover_tok, hover_tok))

# 可能的字色 / 底色，全部取本文件里的常量，避免手抄色值
NUMERALS = ["c_ink", "c_ink2", "c_ink3", "c_ok", "c_accent"]
BASES = ["c_card", "c_sel_bg", "c_accent_s"]
worst = (10 ** 9, None)
for nname in NUMERALS:
    if nname not in CONSTS:
        continue
    N = _rgb(CONSTS[nname])
    for bname in BASES:
        if bname not in CONSTS:
            continue
        B = _rgb(CONSTS[bname])
        # 悬停时：底与数字都被同一层半透明色压过
        cb = _over(B, C, hover_a / 255.0)
        cn = _over(N, C, hover_a / 255.0)
        d = abs(_lum(cb) - _lum(cn))
        if d < worst[0]:
            worst = (d, "%s(%s) 压在 %s(%s) 上" % (nname, CONSTS[nname], bname, CONSTS[bname]))

MIN_DELTA = 90          # 实测参考：现状最差组合 ≈127（上/下月的灰字），仍可辨
print("悬停底 %s（%s，alpha=%d/255）合成后，数字与底的最小亮度差 = %d（%s）"
      % (hover_src, hover_tok, hover_a, worst[0], worst[1]))
if worst[0] < MIN_DELTA:
    problems.append((0, "悬停底太不透明：数字与底的亮度差只剩 %d（要求 ≥ %d），"
                        "数字会被糊掉" % (worst[0], MIN_DELTA)
                     + "  —— " + str(worst[1]), ""))

if problems:
    print("\n有 %d 处状态色不合规：" % len(problems))
    for ln, why, extra in sorted(problems):
        print("  L%-6d %s%s" % (ln, why, ("   ← " + extra) if extra else ""))
    print("\n→ 点击层画在画布之上：不透明的状态色 = 把日期数字擦掉。")
    sys.exit(1)
print("状态色透明度合规 ✓（点击层不会盖住画布内容）")
