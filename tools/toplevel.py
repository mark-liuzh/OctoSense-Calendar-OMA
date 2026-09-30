import io, sys

P = sys.argv[1] if len(sys.argv) > 1 else 'bundle/main.splash'
lines = io.open(P, encoding='utf-8').read().split('\n')
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

print('EOF depth =', depth)
bad = 0
for i, ln in enumerate(lines, 1):
    s = ln.strip()
    if s.startswith('fn ') or s.startswith('start_timeout(') or s.startswith('start_interval('):
        before = prof[i - 2] if i >= 2 else 0
        flag = '' if before == 0 else '   <<< 非顶层！'
        if before != 0:
            bad += 1
        print('line %5d  行前depth=%d %s  %s' % (i, before, flag, s[:50]))
print('异常条数 =', bad)
