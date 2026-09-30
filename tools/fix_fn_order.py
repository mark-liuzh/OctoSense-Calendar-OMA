"""把 main.splash 里「前向引用」的函数挪到依赖之后（最小移动）。

背景（实测）：
  Splash 编译 fn 体时解析函数名；若引用的是**后面才定义**的函数，
  该 fn 不会被注册，其所有调用点都报 `variable X not found in scope`。

策略：只移动「有前向引用」的函数 —— 挪到它最后一个依赖的后面，反复直到收敛。
      其余函数保持原位，改动量最小、可审查。
用法：python tools/fix_fn_order.py bundle/main.splash [--apply]
"""
import io
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else 'bundle/main.splash'
APPLY = '--apply' in sys.argv

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


# ---- 找 fn 起始行 + 结束行
fn_starts = [(i, m.group(1))
             for i, ln in enumerate(lines, 1)
             for m in [re.match(r'^fn ([a-z_0-9]+)\(', ln)] if m]
names = {n: s for s, n in fn_starts}

depth = 0
prof = []
for ln in lines:
    depth += stripped(ln).count('{') - stripped(ln).count('}')
    prof.append(depth)

blocks = []
for s, name in fn_starts:
    base = prof[s - 2] if s >= 2 else 0
    end = len(lines)
    for i in range(s, len(lines)):
        if prof[i] <= base:
            end = i + 1
            break
    blocks.append((name, s, end))

first_fn_line = blocks[0][1]


def head_start(s):
    """把紧邻上方的注释/空行并入本块（注释跟着它描述的函数走）"""
    i = s
    while i - 1 >= first_fn_line:
        t = lines[i - 2].strip()
        if t == '' or t.startswith('//'):
            i -= 1
        else:
            break
    return i


# chunk 文本按「本块头 .. 下一块头」切分，保证无缝覆盖
heads = [head_start(s) for _, s, _ in blocks]
chunks = []
for k, (name, s, e) in enumerate(blocks):
    start = heads[k]
    end = heads[k + 1] - 1 if k + 1 < len(blocks) else blocks[-1][2]
    chunks.append({'name': name, 'lines': lines[start - 1:end]})

prefix = lines[:heads[0] - 1]
suffix = lines[blocks[-1][2]:]

text_of = {c['name']: '\n'.join(c['lines']) for c in chunks}
pos = {c['name']: i for i, c in enumerate(chunks)}

deps = {}
for c in chunks:
    d = set()
    for m in re.finditer(r'\b([a-z_][a-z_0-9]*)\s*\(', text_of[c['name']]):
        f = m.group(1)
        if f in names and f != c['name']:
            d.add(f)
    deps[c['name']] = d

moves = []
for _ in range(400):
    changed = False
    for i, c in enumerate(list(chunks)):
        late = [d for d in deps[c['name']] if pos[d] > i]
        if not late:
            continue
        # 挪到最后一个依赖之后
        tgt = max(pos[d] for d in late) + 1
        nm = c['name']
        chunks.pop(i)
        for k, cc in enumerate(chunks):
            pos[cc['name']] = k
        chunks.insert(tgt, c)
        for k, cc in enumerate(chunks):
            pos[cc['name']] = k
        moves.append((nm, sorted(late)))
        changed = True
        break
    if not changed:
        break
else:
    print('!! 未收敛（可能有循环依赖）')
    sys.exit(1)

print('函数总数 %d，移动 %d 次:' % (len(chunks), len(moves)))
for nm, late in moves:
    print('  %-18s 挪到 %s 之后' % (nm, ', '.join(late)))

out = list(prefix)
for c in chunks:
    if out and out[-1].strip() != '':
        out.append('')
    out.extend(c['lines'])
out.extend(suffix)
new_src = '\n'.join(out)
if not new_src.endswith('\n'):
    new_src += '\n'

print('括号差: 原 %d 新 %d' % (src.count('{') - src.count('}'),
                              new_src.count('{') - new_src.count('}')))
assert (src.count('{') - src.count('}')) == (new_src.count('{') - new_src.count('}'))

# 复检：不应再有前向引用
chk_lines = new_src.split('\n')
chk = {}
for i, ln in enumerate(chk_lines, 1):
    m = re.match(r'^fn ([a-z_0-9]+)\(', ln)
    if m:
        chk[m.group(1)] = i
d2 = 0
p2 = []
for ln in chk_lines:
    d2 += stripped(ln).count('{') - stripped(ln).count('}')
    p2.append(d2)
left = []
for name, s in sorted(chk.items(), key=lambda kv: kv[1]):
    base = p2[s - 2] if s >= 2 else 0
    end = len(chk_lines)
    for i in range(s, len(chk_lines)):
        if p2[i] <= base:
            end = i + 1
            break
    for i in range(s - 1, end):
        for m in re.finditer(r'\b([a-z_][a-z_0-9]*)\s*\(', chk_lines[i]):
            f = m.group(1)
            if f in chk and f != name and chk[f] > s:
                left.append((name, f))
print('剩余前向引用:', left if left else '无')

if APPLY and not left:
    io.open(P, 'w', encoding='utf-8').write(new_src)
    print('已写入', P)
else:
    print('（未写入）')
