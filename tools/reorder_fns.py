"""按依赖顺序重排 main.splash 里的函数定义。

背景（实测）：
  Splash 在编译函数体时解析函数名。若引用的是**后面才定义**的函数，
  该引用解析失败（运行时 `variable X not found in scope`），
  并且**被引用的那个 fn 也不会注册**，导致它的调用点全部失效。

做法：把 fn 块按拓扑序重排（被调用者在前），保持原有相对顺序（稳定排序）。
"""
import io
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else 'bundle/main.splash'
DRY = '--apply' not in sys.argv

src = io.open(P, encoding='utf-8').read()
lines = src.split('\n')

BS = chr(92)
Q1 = chr(34)
Q2 = chr(39)


def stripped(code):
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
        if ch == '/' and j + 1 < len(code) and code[j + 1] == '/':
            break
        out.append(ch)
        j += 1
    return ''.join(out)


# ---- 1. 找所有 fn 起始行，并用括号深度求其结束行
fn_starts = []          # (line, name)
for i, ln in enumerate(lines, 1):
    m = re.match(r'^fn ([a-z_0-9]+)\(', ln)
    if m:
        fn_starts.append((i, m.group(1)))

names = {n: s for s, n in fn_starts}

depth = 0
prof = []
for ln in lines:
    depth += stripped(ln).count('{') - stripped(ln).count('}')
    prof.append(depth)

# 结束行：从 fn 起始行往后找第一个 depth 回到 fn 起始行之前的 depth 的地方
blocks = []             # (name, start_line, end_line)
for idx, (s, name) in enumerate(fn_starts):
    base = prof[s - 2] if s >= 2 else 0
    end = s
    for i in range(s, len(lines)):
        if prof[i] <= base:
            end = i
            break
    else:
        end = len(lines)
    blocks.append((name, s, end + 1))

first_fn_line = blocks[0][1]
last_fn_end = blocks[-1][2]

# ---- 2. 每块前面紧邻的注释/空行一起打包（注释跟着它描述的函数走）
def head_start(s):
    i = s - 1          # 1-based 行号
    while i - 1 >= first_fn_line:
        t = lines[i - 2].strip()
        if t == '' or t.startswith('//'):
            i -= 1
        else:
            break
    return i


chunks = []
for name, s, e in blocks:
    h = head_start(s)
    chunks.append({'name': name, 'start': h, 'end': e,
                   'text': lines[h - 1:e]})
    # 上一个块的结束要跟着前移
    if len(chunks) >= 2:
        chunks[-2]['end'] = h - 1
        chunks[-2]['text'] = lines[chunks[-2]['start'] - 1:h - 1]

prefix = lines[:chunks[0]['start'] - 1]
suffix = lines[chunks[-1]['end']:]

# 校验：chunk 起点递进、覆盖到最后一个 fn 结束
for k in range(len(chunks) - 1):
    assert chunks[k]['start'] < chunks[k + 1]['start'], chunks[k]
    assert chunks[k]['end'] < chunks[k + 1]['start'], (chunks[k], chunks[k + 1])
print('函数区覆盖: line %d .. %d  (suffix %d 行)'
      % (chunks[0]['start'], chunks[-1]['end'], len(suffix)))

# ---- 3. 建依赖图（fn 体内的调用）
text_of = {}
for c in chunks:
    text_of[c['name']] = '\n'.join(c['text'])

deps = {}
for c in chunks:
    name = c['name']
    d = set()
    for m in re.finditer(r'\b([a-z_][a-z_0-9]*)\s*\(', text_of[name]):
        f = m.group(1)
        if f in names and f != name:
            d.add(f)
    deps[name] = d

orig_order = [c['name'] for c in chunks]

# ---- 4. 拓扑排序（稳定：反复按原顺序扫描，取所有依赖已就绪的）
done = []
placed = set()
remaining = list(orig_order)
progress = True
while remaining and progress:
    progress = False
    for nm in list(remaining):
        if deps[nm] <= placed:
            done.append(nm)
            placed.add(nm)
            remaining.remove(nm)
            progress = True
if remaining:
    print('!! 存在循环依赖，剩余:', remaining)
    sys.exit(1)

moved = [n for i, n in enumerate(done) if n != orig_order[i]]
print('函数总数:', len(chunks))
print('需要移动的:', len(moved))
# 展示「改动前后位置差 > 0」的
by_name = {c['name']: c for c in chunks}
out_lines = list(prefix)
for i, nm in enumerate(done):
    if out_lines and out_lines[-1].strip() != '':
        out_lines.append('')
    out_lines.extend(by_name[nm]['text'])
out_lines.extend(suffix)

new_src = '\n'.join(out_lines)
if new_src.endswith('\n'):
    new_src = new_src[:-1]
if not new_src.endswith('\n'):
    new_src += '\n'

old_diff = src.count('{') - src.count('}')
new_diff = new_src.count('{') - new_src.count('}')
print('大括号差: 原 %d 新 %d' % (old_diff, new_diff))
assert old_diff == new_diff, '重排后括号不平衡，中止'

if DRY:
    print('（dry-run，未写入。加 --apply 生效）')
else:
    io.open(P, 'w', encoding='utf-8').write(new_src)
    print('已写入', P)
