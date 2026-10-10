#!/usr/bin/env bash
# 天气城市选择功能的定点验收（v0.5.0）。
# 验证五件事：
#   1. 月历右上角有可点的城市按钮，且那一行没被挤爆（最右边界 < 412）
#   2. 点它能展开城市面板，且面板整体在 892px 视口内
#   3. 输入城市名点「应用」后，wx_city.json 真的写下了新坐标
#   4. 顶栏按钮文案变成新城市名
#   5. 换城市后旧城市的天气缓存被清空（不是两个城市的数据混着显示）
ROOT="$PWD"
OUT="$ROOT/.runtime"
source "$ROOT/tools/_env.sh"
LOG="$OUT/verify-city.log"
boot_host "$LOG" || exit 1
sleep 2

OCTO_PORT="$PORT" /Users/odycai/.workbuddy/binaries/python/envs/default/bin/python - <<'PY'
import os, sys, time, json, glob
sys.path.insert(0, 'tools')
import e2e

def ui(s):
    # 根 Splash 节点的 text 是整份脚本源码，必须排除，否则什么都「命中」
    return [n for n in s if n.get('ty') != 'Splash' and n.get('r')]

def find(s, sub, ty=None):
    for n in ui(s):
        if sub in (n.get('t') or '') and (ty is None or n.get('ty') == ty):
            return n
    return None

fails = []
def ck(name, ok, extra=''):
    print(('  OK   ' if ok else '  FAIL ') + name + (('  ' + extra) if extra else ''))
    if not ok:
        fails.append(name)

# ── 1. 顶栏城市按钮 ──
s = e2e.snap(wait_render=True, timeout=12.0)
btn = find(s, '北京', 'Button')
ck('月历右上角有城市按钮（默认「北京」）', btn is not None,
   '' if not btn else 'r=%s' % (btn['r'],))
if btn:
    y = btn['r'][1]
    row = sorted([n for n in ui(s) if n['r'][1] == y], key=lambda n: n['r'][0])
    right = max(n['r'][0] + n['r'][2] for n in row)
    ck('顶栏那一行没被挤爆（最右 < 412）', right < 412, '最右 x=%d / 视口 412' % right)
    # ⚠️⚠️ 三个翻月按钮都要在，**且宽度都必须是 26px**。
    #   只判「存在」会漏掉一种真实故障：宽度被压缩。实测 116px 的城市按钮
    #   把 `·` 压到 20px 并让 `>` 直接消失 —— 而「最右边界 392 < 412」看着完全正常。
    #   教训：横向预算要逐个元素看，「没超出视口」≠「没挤掉东西」。
    nav = {}
    for k in ('<', '·', '>'):
        n = find(s, k, 'Button')
        nav[k] = n['r'][2] if n else None
    ck('翻月按钮三个都在且宽度都是 26px（未被城市按钮挤掉）',
       all(v == 26 for v in nav.values()), str(nav))

# ── 2. 打开面板（每一步都重新取快照，绝不复用旧坐标）──
e2e.click_node(btn)
time.sleep(0.8)
s = e2e.snap()
ck('点城市按钮能展开城市面板', find(s, '天气按城市取', 'Label') is not None)

entry = None
for n in ui(s):
    if n.get('ty') == 'TextInput':
        entry = n
        break
ck('面板里有城市名输入框', entry is not None)
ys = [n['r'][1] + n['r'][3] for n in ui(s)]
ck('面板打开后仍在视口内（最大底边 < 892）', max(ys) < 892, '最大底边=%d' % max(ys))

applied = find(s, '应用', 'Button')
ck('面板里有「应用」按钮', applied is not None)

# ── 3. 输入 + 应用 ──
# ⚠️ 用英文城市名：宿主键盘桥 /k?t= 对非 ASCII 不通
#   （实测输入「深圳」发出去的 URL 是 name=2814522323，即字符码）。
#   这是宿主既有限制，与本应用无关；地理编码本身支持中文，真机手动输入即可。
CITY = '深圳'
if entry and applied:
    e2e.click_node(entry)
    time.sleep(0.8)
    # ⚠️⚠️ 不要调 e2e.wipe_entry()：它内部 `find_id(s, "entry")` 找的是**导入面板**
    #   那个输入框的 id，不是 city_entry。城市面板打开时导入面板是隐藏的，
    #   它找不到就静默 return False，然后后面的 type_text 就打空了地方。
    #   城市输入框本来就是空的（toggle_city_panel 每次打开都 set_text("")），无需清。
    time.sleep(0.3)
    e2e.type_text(CITY)
    time.sleep(0.6)
    # 确证字真的进去了 —— 否则后面必然白点。
    # ⚠️ 不能用 e2e.entry_text()：它同样只认 id="entry"（导入面板那个）。
    # 这里直接从当前快照里找 TextInput 读它的 val（真实内容，非占位提示）。
    _s = e2e.snap()
    _ents = [n for n in ui(_s) if n.get('ty') == 'TextInput']
    cur = (_ents[0].get('val') if _ents else '') or ''
    ck('城市名真的输入进了输入框', CITY in cur, 'val=%r' % cur[:40])

    # ⚠️ 只点**一次**「应用」——这是对用户的真实要求。
    #   apply_city 内部会用 start_timeout(0.6s) 自动排重试（retry_city），
    #   用户不该被要求点第二次。实测该链路需 ~1.5s 才落定。
    s = e2e.snap()
    b = find(s, '应用', 'Button')
    if b:
        e2e.click_node(b)

    # 等它自己走完「首次 -9999 → 重试 → 拿到坐标」这条链
    got = False
    for _ in range(14):
        time.sleep(1.0)
        s = e2e.snap()
        if find(s, '已切到', 'Label'):
            got = True
            break
        if find(s, '没查到该城市', 'Label'):
            break
    s = e2e.snap()
    trace = []
    for m in ('已切到', '没查到该城市', '查询中'):
        hit = find(s, m, 'Label')
        if hit:
            trace.append(hit.get('t'))
    print('  ·  最终提示: %s' % (trace[0] if trace else '(面板已关，提示不可见)'))

s = e2e.snap()
# ⚠️ 成功路径会**关闭**面板（`wx_city_open = false`），而提示 Label 在面板内部，
#   所以成功后「已切到」是看不见的 —— 判据必须落在**面板外**的顶栏按钮上。
ck('顶栏城市按钮已更新为新城市（面板已关 = 成功路径走完）',
   find(s, CITY, 'Button') is not None)
ck('面板已收起（成功后才关）', find(s, '应用', 'Button') is None)

# ── 4. 落盘检查 ──
files = glob.glob('.runtime/app-data-*/com.oma.octosense.calendar/wx_city.json')
if files:
    got = json.load(open(files[-1]))
    la, lo = got.get('lat'), got.get('lon')
    # 深圳 lat≈22.5 lon≈114.1；北京是 39.9042 / 116.4074
    ck('wx_city.json 写下了新坐标（不是北京）',
       la is not None and 22.0 < la < 23.5,
       'lat=%s lon=%s city=%s' % (la, lo, got.get('name')))
    ck('坐标是中国深圳而非北京',
       lo is not None and 113.5 < lo < 114.5,
       'lon=%s（北京是 116.4074）' % lo)
else:
    ck('wx_city.json 已生成', False, '(没找到文件)')

# ── 5. 旧城市缓存已清、新城市数据已回填 ──
# ⚠️ 判据不是「缓存变空」——换完城市 wx_past_fetch 会**立刻拉新城市的数据回填**，
#   等断言时它已经是 37 行新数据了（实测深圳 9/10 最高 30°，北京同期约 25°）。
#   真正要证的是：① 缓存非空（新城市数据到了）② 时间戳晚于坐标写入（顺序对）
#   ③ 行数接近 37（30 天历史 + 7 天预报，是全量而不是残留碎片）。
live = sorted(glob.glob('.runtime/app-data-*/com.oma.octosense.calendar/wx_live3.json'),
              key=os.path.getmtime)
city_f = sorted(glob.glob('.runtime/app-data-*/com.oma.octosense.calendar/wx_city.json'),
                key=os.path.getmtime)
if live and city_f:
    raw = open(live[-1]).read()
    rows = json.loads(raw).get('rows', [])
    ck('新城市天气已回填（缓存非空）', len(rows) > 0, '%d 行' % len(rows))
    ck('缓存是全量而非残留碎片（>=30 行）', len(rows) >= 30, '%d 行' % len(rows))
    ck('天气数据的时间戳晚于坐标写入（清空→回填顺序对）',
       os.path.getmtime(live[-1]) >= os.path.getmtime(city_f[-1]) - 1,
       'wx_live3=%.1f wx_city=%.1f' % (os.path.getmtime(live[-1]),
                                      os.path.getmtime(city_f[-1])))
else:
    ck('天气缓存与坐标文件都在', False)

print()
print('小结：%d 项失败' % len(fails))
if fails:
    print('失败项：', fails)
PY

echo
echo "=== 宿主 [E] 数 ==="
grep -c "\[E\]" "$LOG" 2>/dev/null || echo 0
grep "\[E\]" "$LOG" 2>/dev/null | head -5
echo "=== geocoding 请求次数 ==="
grep -c "geocoding-api.open-meteo.com/v1/search" "$LOG" 2>/dev/null || echo 0
