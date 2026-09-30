import io, json, sys, time, urllib.parse, urllib.request

BASE = 'http://127.0.0.1:8932'


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return r.read().decode('utf-8', 'replace')


def snap():
    return json.loads(get('/snap'))


def click(x, y):
    return get('/click?x=%d&y=%d' % (x, y))


def type_text(t):
    # /k?t=... 直接传原文，仅做百分号编码
    return get('/k?t=' + urllib.parse.quote(t, safe=''))


def find(s, pred):
    for w in s['s']:
        if pred(w):
            return w
    return None


def center(w):
    r = w['r']
    return r[0] + r[2] // 2, r[1] + r[3] // 2


def btn_text(s, label):
    for w in s['s']:
        if w.get('ty') == 'Button' and w.get('t') == label:
            return w
    return None


def texts(s, maxlen=90):
    out = []
    for w in s['s']:
        t = w.get('t')
        if t and str(t).strip() and len(str(t)) < maxlen:
            out.append((w.get('ty'), str(t)))
    return out


if __name__ == '__main__':
    act = sys.argv[1]
    if act == 'open':
        s = snap()
        # 幂等：只有 entry 不在树里时才点
        ent = find(s, lambda w: w.get('ty') == 'TextInput')
        if ent is None:
            w = btn_text(s, '导入')
            print('导入 btn', w['r'])
            click(*center(w))
            time.sleep(0.8)
            s = snap()
            ent = find(s, lambda w: w.get('ty') == 'TextInput')
        print('entry', ent['r'] if ent else None)
    elif act == 'fill':
        ics = io.open('seed.ics', encoding='utf-8').read()
        s = snap()
        ent = find(s, lambda w: w.get('ty') == 'TextInput')
        click(*center(ent))
        time.sleep(0.4)
        type_text(ics)
        time.sleep(0.6)
        s = snap()
        ent = find(s, lambda w: w.get('ty') == 'TextInput')
        t = str(ent.get('t') or '')
        print('len', len(t))
        print(t[:120])
    elif act == 'parse':
        s = snap()
        w = btn_text(s, '解析')
        if not w:
            print('no 解析 btn'); sys.exit(1)
        click(*center(w))
        time.sleep(1.2)
        s = snap()
        for ty, t in texts(s):
            print(ty, '|', t)
    elif act == 'texts':
        s = snap()
        for ty, t in texts(s):
            print(ty, '|', t)
    elif act == 'click':
        click(int(sys.argv[2]), int(sys.argv[3]))
        time.sleep(0.8)
        s = snap()
        for ty, t in texts(s):
            print(ty, '|', t)
    elif act == 'label':
        s = snap()
        w = btn_text(s, sys.argv[2])
        print(w['r'] if w else 'not found')
