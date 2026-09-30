import io, sys

P = sys.argv[1] if len(sys.argv) > 1 else 'bundle/main.splash'
lines = io.open(P, encoding='utf-8').read().split('\n')

BS = chr(92)
DQ = chr(34)
SQ = chr(39)


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
        if ch == DQ or ch == SQ:
            q = ch
            j += 1
            continue
        if ch == '/' and j + 1 < len(code) and code[j + 1] == '/':
            break
        out.append(ch)
        j += 1
    return ''.join(out)


depth = 0
profile = []
for ln in lines:
    depth += stripped(ln).count('{') - stripped(ln).count('}')
    profile.append(depth)

print('最终 depth =', depth)
zero = [i + 1 for i, d in enumerate(profile) if d == 0]
if not zero:
    print('没有 depth==0 的行')
else:
    last0 = max(zero)
    print('最后一个 depth==0 的行:', last0)
    print('之后各行：')
    for i in range(last0, len(lines)):
        print('  %4d depth=%d  %s' % (i + 1, profile[i], lines[i].strip()[:70]))
