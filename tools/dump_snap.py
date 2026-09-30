import io, re, sys

path = sys.argv[1] if len(sys.argv) > 1 else '.runtime/snap.txt'
s = io.open(path, encoding='utf-8', errors='replace').read()
print('size', len(s))

# 文本内容
txt = re.findall(r'text:\s*"([^"]*)"', s)
txt = [t for t in txt if t.strip()]
print('--- texts (%d) ---' % len(txt))
for t in txt[:80]:
    print('  ', t)

# 错误
errs = re.findall(r'\[E\].*', s)
if errs:
    print('--- errors ---')
    for e in errs[:10]:
        print('  ', e)
