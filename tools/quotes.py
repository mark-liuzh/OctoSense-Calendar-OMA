"""扫描 main.splash 中引号不配对的行（字符串未闭合）。"""
import io
import sys

P = sys.argv[1] if len(sys.argv) > 1 else 'bundle/main.splash'
lines = io.open(P, encoding='utf-8').read().split('\n')
BS = chr(92)
DQ = chr(34)

bad = 0
for i, ln in enumerate(lines, 1):
    # 去掉 // 注释（不含引号时才算注释）
    code = ln
    j = 0
    q = False
    cut = len(code)
    while j < len(code):
        ch = code[j]
        if q:
            if ch == BS:
                j += 2
                continue
            if ch == DQ:
                q = False
            j += 1
            continue
        if ch == DQ:
            q = True
            j += 1
            continue
        if ch == '/' and j + 1 < len(code) and code[j + 1] == '/':
            cut = j
            break
        j += 1
    n = 0
    j = 0
    while j < cut:
        if code[j] == BS:
            j += 2
            continue
        if code[j] == DQ:
            n += 1
        j += 1
    if n % 2 == 1:
        bad += 1
        print('line %5d  引号数 %d  %s' % (i, n, ln.strip()[:100]))
print('不配对行数 =', bad)
