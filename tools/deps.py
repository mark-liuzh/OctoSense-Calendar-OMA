import io, re, sys

P = sys.argv[1] if len(sys.argv) > 1 else 'bundle/main.splash'
src = io.open(P, encoding='utf-8').read()
lines = src.split('\n')

# 收集 fn 定义：名称 -> 起始行
fns = {}
order = []
for i, ln in enumerate(lines, 1):
    m = re.match(r'^fn ([a-z_0-9]+)\(', ln)
    if m:
        fns[m.group(1)] = i
        order.append((i, m.group(1)))

# 找每个函数体的范围（用大括号深度）
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


depth = 0
prof = []
for ln in lines:
    depth += stripped(ln).count('{') - stripped(ln).count('}')
    prof.append(depth)

bodies = {}
for idx, (start, name) in enumerate(order):
    end = order[idx + 1][0] - 1 if idx + 1 < len(order) else len(lines)
    bodies[name] = (start, end)

TARGETS = sys.argv[2].split(',') if len(sys.argv) > 2 else [
    'load', 'refresh_all', 'start_import', 'confirm_import',
    'cancel_import', 'toggle_import', 'rescan_ui', 'clear_all']

for name in TARGETS:
    if name not in bodies:
        print('MISSING', name)
        continue
    s, e = bodies[name]
    called = []
    for i in range(s, e):
        for m in re.finditer(r'\b([a-z_][a-z_0-9]*)\s*\(', lines[i]):
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
    print('fn %-16s (line %4d)  前向引用: %s' % (name, s, fwd if fwd else '无'))
