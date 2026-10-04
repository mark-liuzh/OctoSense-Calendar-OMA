"""花括号配平门禁（tools/run_all.sh 阶段 1 的第 2 道）。

用法： python tools/brace.py [bundle/main.splash]
退出码 0 = 配平；非 0 = 不配平（run_all.sh 会立即中止）。

⚠️⚠️ 2026-10-04 「心情/目标/时光 白屏事故」后重写（血泪）：
   旧版只 print 深度、**从不 sys.exit(1)**，所以它永远是 PASS ——
   一道形同虚设的门禁。缺一个 `}` 时旧版会打印「最终 depth = 1」，
   但 run_all.sh 判的是**退出码**，于是照常绿着过。
   代价：倒计时卡 `countdown_card` 少一个 `}` → 它把 sec_mood /
   sec_goal / sec_egg 三个分区**吞成自己的子节点** → 切「心情/目标/时光」
   整片白屏（父节点 sec_todo 被 set_visible(false)，子树不进布局，snap 里
   连节点都没有），而静态门禁全绿。这条 bug 是靠人肉 dump 布局树才抓到的。

   现在改为：
     ① 必须 sys.exit(1) —— 让它真的能拦住 CI；
     ② 用**栈**记录每个 `{` 的行号，EOF 时仍在栈里的就是**没闭合的块**，
        直接打出「第 N 行 ... 未闭合」，定位成本从「翻 7000 行」降到 0；
     ③ 深度为负（多写了 `}`）也报。
"""
import io
import sys

P = sys.argv[1] if len(sys.argv) > 1 else 'bundle/main.splash'
lines = io.open(P, encoding='utf-8').read().split('\n')

BS = chr(92)
DQ = chr(34)
SQ = chr(39)


def stripped(code):
    """去掉 `//` 注释与字符串字面量，只留下结构性字符。"""
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
        if ch == DQ or ch == SQ:
            q = ch
            j += 1
            continue
        if ch == '/' and j + 1 < len(code) and code[j + 1] == '/':
            break
        out.append(ch)
        j += 1
    return ''.join(out)


def brief(ln):
    return ln.strip()[:96]


depth = 0
profile = []
stack = []       # 每个未闭合 `{` 的 (行号, 该行内容, 该行缩进)
extra_close = []  # 多余的 `}` 的 (行号, 该行内容)
indent_suspect = []  # 缩进没有比父块更深、却开了新块的行 → 缺 `}` 的高发位置


def indent_of(ln):
    n = 0
    for ch in ln:
        if ch == ' ':
            n += 1
        elif ch == '\t':
            n += 4
        else:
            break
    return n


for idx, ln in enumerate(lines):
    code = stripped(ln)
    opens = code.count('{')
    closes = code.count('}')
    # ⚠️ 只看**净增量 > 0** 的行：`out.push({ ... })` / `draw_bg +: {color: c}` 这类
    #    单行自闭合（净增量 0）不是「开了一个块」，拿它做缩进比较全是假阳性。
    if opens > closes and stack and stack[-1][2] > 0 and indent_of(ln) <= stack[-1][2]:
        # 父块还没闭合，这一行却「退到父块同级或更浅」还开了新块 ——
        # 正确嵌套里子块一定缩进更深，所以这里八成是上一块漏了 `}`。
        indent_suspect.append((idx + 1, ln, stack[-1][0]))
    for ch in code:
        if ch == '{':
            stack.append((idx + 1, ln, indent_of(ln)))
            depth += 1
        elif ch == '}':
            if stack:
                stack.pop()
            else:
                extra_close.append((idx + 1, ln))
            depth -= 1
    profile.append(depth)

problems = []

if extra_close:
    problems.append('有 %d 个多余的 `}`（没有对应的 `{`）：' % len(extra_close))
    for no, ln in extra_close[:10]:
        problems.append('  第 %d 行  %s' % (no, brief(ln)))

if stack:
    problems.append('有 %d 个 `{` 没有闭合：' % len(stack))
    for no, ln, _ind in stack[:10]:
        problems.append('  第 %d 行  %s' % (no, brief(ln)))
    # 最外层未闭合的那个就是「吞掉后续兄弟节点」的元凶
    if len(stack) > 1:
        problems.append('  ⚠️ 最外层未闭合的是第 %d 行 —— 它会把**之后的所有节点**吞成自己的子节点'
                        % stack[0][0])
    if indent_suspect:
        problems.append('  疑似缺 `}` 的位置（缩进比父块还浅却开了新块）：')
        for no, ln, pno in indent_suspect[:6]:
            problems.append('    第 %d 行（父块开于第 %d 行）  %s' % (no, pno, brief(ln)))

if problems:
    print('brace FAIL: 最终 depth = %d（应为 0）' % depth)
    print('\n'.join(problems))
    print('提示：这类缺陷会让整棵子树从布局树里消失（白屏），而运行时**不一定报错**。')
    sys.exit(1)

print('brace OK: 最终 depth = 0，共 %d 行，最大嵌套 %d 层'
      % (len(lines), max(profile) if profile else 0))
