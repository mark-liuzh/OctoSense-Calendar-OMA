#!/usr/bin/env python3
"""OctoSense 远程驱动 · 端到端实测

用法：
  python e2e.py open          点「导入」展开面板
  python e2e.py fill <file>   把文件内容灌进输入框
  python e2e.py parse         点「解析」（轮询等预览条出现）
  python e2e.py write         点「写入」（轮询等按钮出现）
  python e2e.py cancel        点确认条「取消」
  python e2e.py texts         打印界面所有文本
  python e2e.py dump          打印全部节点
  python e2e.py click x y     点任意坐标
  python e2e.py scroll dy     在页面中央滚轮滚动（负值向上）
  python e2e.py about         点「关于」
  python e2e.py clear         点「清空事件库」
  python e2e.py export        点「导出」
  python e2e.py cycle         切换节日来源（中国 → 国际 → 全部）
  python e2e.py months n      月历向后翻 n 个月（n 为负则向前）· 闭环，每步校验落点
  python e2e.py goto YYYY-MM  翻到指定月份（推荐：与「今天几号」解耦）
  python e2e.py fest          打印节日说明行 + 本月放假/调休标记
  python e2e.py dotcolor <png>  回读截图像素，打印每个日期标记的实际颜色
"""
import io, json, os, sys, time, urllib.parse, urllib.request

PORT = os.environ.get("OCTO_PORT", "8932")
BASE = "http://127.0.0.1:" + PORT
SNAP = ".runtime/snap.json"

# ⚠️ 本机环境设了 http_proxy=http://127.0.0.1:2801，会把发往宿主（127.0.0.1:8932）
#    的请求也劫持走代理 → 502 Bad Gateway / 返回上一帧的陈旧截图。
#    必须显式清空 ProxyHandler，否则测试结果全是假的。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _get(path):
    with _OPENER.open(BASE + path, timeout=10) as r:
        return r.read().decode("utf-8", "replace")


def _stable(pred, tries=5, settle=0.35):
    """反复求值 pred，直到它连续 `settle` 秒都为真（或超时）。

    ⚠️ 为什么需要（2026-10-09 实测，连跑 5 轮有 2 轮红）：宿主的翻月/ 切来源
    是**异步落地**的，且偶发「落地后又弹回原值」。原先 `goto` 闭环确认一次
    就返回，脚本再另起一条命令去读 —— 两条命令之间存在窗口，宿主正好在
    窗口里复位状态，于是「翻月断言 OK、随后的 fest 读到上一个月」。
    这里要求**状态稳定一段时间**才算数，且由同一条命令接着输出 fest，
    消除「确认」与「读取」之间的空档。
    """
    last = None
    ok_since = None
    deadline = time.time() + tries * 3.0
    while time.time() < deadline:
        last = pred()
        if last:
            if ok_since is None:
                ok_since = time.time()
            elif time.time() - ok_since >= settle:
                return True, last
        else:
            ok_since = None
        time.sleep(0.15)
    return False, last


def _render_ready(s):
    """判断这份快照是不是**内容与当前月份一致**的月历。

    ⚠️ 三轮返工才对（2026-10-09），前两版的判据都抓错了东西：
     ① 最初数「空文本的方形按钮」= 42 个格子 —— **错**。那42 个点击层
        ButtonFlat 是**静态声明**的，翻月时并不会被清空，所以翻到一半也照样是
        42 个 ⇒ 判据恒为真，等于没判。
     ② 改成数格子上的**日期数字** —— 对。日期数字由cal_cells() 每帧按当前
        view_month 重新生成，重绘中途会是 0 个。
     ③ 但「有数字」还不够：实���抓到过**新旧混杂**的一帧 —— 月份标题已经是
        10 月、格子里的日期数字与标记点却还是 9 月的（DOTS 读出 5 而不是 8）。
         所以判据必须是「**连续多帧内容完全一致**」，见 _stable_consistent()。

    这里只回答「月历格子画出来了没有」；「这一帧内部是否自相矛盾」交给上层。
    """
    n = 0
    for node in s:
        t = str(node.get("t") or "").strip()
        if t.isdigit() and 1 <= int(t) <= 31:
            n += 1
    # 一个月 42 格里最多 31 个数字行；渲染完整时至少 28（2 月平月也有 28）
    return n >= 28


def _fingerprint(s):
    """这份快照里「与月份相关」的内容指纹。

    只取月历区域（y 在月历行范围内）与标题、标记点、节日行 —— 工具条、
    状态条、底部按钮在这些操作下不变，混进来会稀释掉变化。
    用途：判断连续两帧**内容完全一致**（见 _stable_consistent）。
    """
    parts = []
    for node in s:
        t = str(node.get("t") or "").strip()
        r = node.get("r") or [0, 0, 0, 0]
        ty = node.get("ty")
        # 月历区大致 y∈[380, 800]（6 行 × 52px + 行距），加上标题与说明行
        if 40 <= r[1] <= 800 and (t or ty in ("View", "ViewFlat", "RoundedView",
                                            "CircleView")):
            parts.append("%s|%s|%s" % (t, ty, r))
    return "\n".join(parts)


def _stable_consistent(tries=8, settle=0.3):
    """连续 `settle` 秒内，快照内容指纹保持完全一致才算稳定。

    ⚠️ 这是本轮最关键的一处（2026-10-09）：宿主翻月时**不是**原子的
    「清空 → 整帧重绘」，而是分步更新 —— 实测抓到过月份标题已更新、
    格子日期与标记点还是上一个月的「半帧」。此时任何按月份写的断言都会
    报出「MONTH 对、DOTS 错」这种自相矛盾的红。

    判据用**整帧内容指纹相同**（而不是「某几个字段看起来对」），
    所以无论是标题先更新还是格子先更新，都会被挡下。
    """
    fp = None
    ok_since = None
    deadline = time.time() + tries * 4.0
    while time.time() < deadline:
        s = snap(wait_render=False)
        cur = _fingerprint(s)
        if _render_ready(s) and cur == fp:
            if ok_since is None:
                ok_since = time.time()
            elif time.time() - ok_since >= settle:
                return True, s
        else:
            fp = cur
            ok_since = None
        time.sleep(0.15)
    return False, snap(wait_render=True)


def snap(wait_render=False, timeout=3.0):
    """取一份 /snap 快照。

    ⚠️⚠️ `wait_render` 默认为**关**（2026-10-09 改）。理由是一个自己踩的坑：
       我曾把「等月历渲染就绪」放进这里当默认，于是**导入面板**这类
       根本没有日历格子的页面也一起等 —— 而 _render_ready 数的是日期数字，
       面板页恒为 0 ⇒ 每次 snap() 都白等满timeout。
       run_e2e 的 [4/7]「灌入 seed.ics」一步有几十次 snap() 调用，
       于是那一轮回归从 40 秒变成**十几分钟**，看起来像死锁。
       教训：**渲染就绪这类判据只在该用它的地方用**（goto / cycle /
       dumpsnap 这三个真正关心月历的命令），不要塞进通用入口。
    """
    raw = _get("/snap")
    io.open(SNAP, "w", encoding="utf-8").write(raw)
    s = json.loads(raw)["s"]
    if wait_render and not _render_ready(s):
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.15)
            raw = _get("/snap")
            s = json.loads(raw)["s"]
            if _render_ready(s):
                io.open(SNAP, "w", encoding="utf-8").write(raw)
                break
    return s


def click(x, y):
    _get(f"/click?x={int(x)}&y={int(y)}")
    time.sleep(0.35)


def scroll(dy, x=206, y=500):
    """滚轮滚动：dy 负=向上（看上面的内容），正=向下"""
    _get(f"/m?k=scroll&x={x}&y={y}&dy={dy}")
    time.sleep(0.35)


def type_text(t):
    _get("/k?t=" + urllib.parse.quote(t, safe=""))
    time.sleep(0.5)


def entry_text(s=None):
    """读输入框的**真实内容**；找不到输入框返回 None（用来区分「没有输入框」）。

    ⚠️⚠️ 2026-10-01 修正字段优先级（原实现按 `t` 优先，是错的）：
       实测快照里 **`t` 是渲染后的显示文本，`val` 才是真实值**：
         · 空输入框 → {"t": "BEGIN:VCALENDAR …", "val": ""}
                      （`t` 是占位提示，17 字符 → 空态被误读成「有 17 个字符」）
         · 有内容   → {"t": "<内容>", "val": "<内容>"}
       所以「有没有内容」必须看 `val`。优先取 `val`，再退回其它字段。
    """
    s = s if s is not None else snap()
    for n in s:
        if n.get("ty") in ("TextInput", "TextInputFlat"):
            for k in ("val", "v", "value", "text", "t"):
                if k in n and n[k] is not None:
                    return str(n[k])
            return ""
    return None


def wipe_entry(already_focused=False):
    """清空输入框：**按当前长度连发退格**，直到文本长度不再变短。

    背景（宿主的文本输入语义）：输入走 remote.rs 的 route_key/route_text，
    只发 `Input::Text`，语义是**在光标处插入**，不是替换。所以「先 export 填充、
    再 fill 同一份 ICS」会把内容灌成两份 —— 实测 1235 字节变 2470 字节、
    12 个 UID 各出现 2 次，merge_events 认不出这是同一批事件，
    往返断言（期望新增 0 / 跳过 6）直接失效。

    ⚠️⚠️ 为什么不能再用 Ctrl+A（2026-10-01 macOS 实测**推翻**了原实现）：
       原实现是「Ctrl+A 全选 → 一次 Backspace」。实测本机宿主上
       **Ctrl+A 完全没有效果** —— `c=keya&ctrl=1` 和官方文档写的
       `k=down&c=KeyA&ctrl=1` 两种写法都试过，灌入 8 个字符后按「全选+退格」，
       只剩 7 个（**只删掉了 1 个字符**）。
       后果极隐蔽：连续 fill 会把内容**累加**（实测 127 → 123 → 409 → 874 字符
       逐次追加），run_negative 的四个坏输入夹具全叠进同一个输入框，
       状态条报出的是**上一个夹具**的错，看起来像应用解析错了，其实输入就不是
       它以为的那份。
       退格则稳定可靠：`c=backspace` 每次**恰好删 1 个字符**（实测 ×12 → 恰好少 12）。
       Windows 上原来 Ctrl+A 是有效的，改成连发退格后**行为不变**（只是多几个请求）
       —— 因此这个改法是严格更可移植的。

    ⚠️ 判据用 `val`（真实内容），不要用 `t`（显示文本，空态是占位提示里的
       「BEGIN:VCALENDAR …」，会把空态误判成「有 17 个字符」）。

    ⚠️ 退格与**前向删除交替**发（`c=backspace` + `c=delete`）：
       退格只删光标**左边**。实测光标停在文字中间时，右边那一截**永远删不掉**，
       残留会从中间开始（例如 'e//CN\nEND:VCALENDAR…'）；
       而宿主上「把光标挪到末尾」并不可靠（点击输入框右侧实测无效）。
       交替发两种删除键，就不依赖光标位置了。

    ⚠️ 结束条件**只能是 `val` 为空**，不能用「长度不再变短」这类启发式：
       删除请求是异步落地的，`/snap` 可能读到上一帧，宽度一时没变就误判成「到底了」，
       于是留下残尾（实测：75 字符的夹具清成 76、287 的清成 303、466 的清成 120）。
    """
    s = snap()
    e = find_id(s, "entry")
    if not e:
        return False
    if not already_focused:
        click_node(e)

    for _ in range(30):
        cur = entry_text() or ""
        if cur == "":
            # ⚠️ 必须先让队列里**剩余的删除键落地**再返回。实测：清空成功后
            #    紧接着灌入下一份夹具，残余的退格会把刚打进去的字**吃掉**
            #    （broken-events.ics 实测被清成 0 字符）。
            time.sleep(2.5)
            return True                      # 唯一成功判据：真实内容为空
        n = min(len(cur) + 4, 256)
        for _ in range(n):
            _get("/k?c=backspace")
            _get("/k?c=delete")
        _get("/k?c=backspace&wait=1")        # 屏障：确证前面那批已被处理
        time.sleep(0.35)
    return (entry_text() or "") == ""


def btn(s, label):
    """匹配按钮文本：先精确、再包含（设计稿给按钮加了 ↑/↓ 图标前缀）"""
    for n in s:
        if n.get("ty") in ("Button", "ButtonFlat") and str(n.get("t", "")).strip() == label:
            return n
    for n in s:
        if n.get("ty") in ("Button", "ButtonFlat") and label in str(n.get("t", "")):
            return n
    return None


def any_text(s, sub):
    for n in s:
        t = n.get("t")
        if t and sub in str(t):
            return n
    return None


def find_id(s, wid):
    for n in s:
        if n.get("i") == wid:
            return n
    return None


def center(n):
    r = n["r"]
    return (r[0] + r[2] / 2.0, r[1] + r[3] / 2.0)


def click_node(n):
    x, y = center(n)
    click(x, y)
    return x, y


def show_texts(s):
    for n in s:
        t = n.get("t")
        if not t:
            continue
        t = str(t)
        if t.startswith("//") or len(t) > 200:
            continue
        if not t.strip():
            continue
        print(f"{n.get('i')} [{n.get('ty')}] r={n.get('r')}  {t!r}")


def need(s, label):
    n = btn(s, label)
    if not n:
        print(f"FAIL: 找不到按钮「{label}」")
        print("  现有按钮:", [n2.get("t") for n2 in s if n2.get("ty") in ("Button", "ButtonFlat")])
    return n


def buttons_of(s):
    return [n.get("t") for n in s if n.get("ty") in ("Button", "ButtonFlat")]


def month_heading(s):
    """月历标题，例如「2026 年 9 月」——界面上唯一同时含「年」「月」的短 Label。

    ⚠️ 必须加长度上限：快照里的 `card`（ty=Splash）节点把**整份 main.splash
       源码**当成 `t` 带出来（实测 94 KB，源码注释里当然也有「年」「月」），
       不加长度守卫会把 94 KB 源码当标题返回，断言全乱。
    """
    for n in s:
        if n.get("ty") != "Label":
            continue
        t = str(n.get("t") or "")
        if len(t) <= 20 and "年" in t and "月" in t:
            return t
    return None


# ── 月份定位：绝对 + 闭环 ──────────────────────────────────────────────
# ★ 2026-10-01 新增。背景是一次真实的翻车：
#   `run_festival.sh` / `newflow.py` 原来**假设「应用打开在 9 月」**，再用相对翻月
#   （`months 1` / `months -12` / 点一次 `>`）推到期盼的月份。
#   但应用打开的是**当月**：2026-10-01 打开就是 10 月，于是每个相对位移整体错一格，
#   run_festival / run_new 大面积断言失败 —— 表象像「翻月丢了一次点击」，
#   真因是**测试写死了日期**。
#   （交接文档 §11 记过同类问题，并称 newflow.py 开头有 `months -1` 兜底；
#     实测**该行并不存在**，那条文档已过时。）
#
#   修法不是加 sleep，而是**改用绝对定位**：要测哪个月就 `goto` 哪个月，
#   与「今天几号」彻底解耦 —— 任何设备、任何日期跑都对。
def _digits_runs(t):
    """收集字符串里所有数字段。

    ⚠️ 年月之间隔着一个「年」字，不能只累加**连续**数字，否则读到 2026 就断了
       （rrule_guard.py 的第一版就栽在这里，返回 None 让翻月循环一次都没跑）。
    """
    runs, cur = [], ""
    for ch in str(t or ""):
        if ch.isdigit():
            cur += ch
        elif cur:
            runs.append(cur)
            cur = ""
    if cur:
        runs.append(cur)
    return runs


def month_of(s=None):
    """月历标题 → (年, 月)；读不到返回 None。

    优先按 id `month_title` 取（main.splash 里 `month_title := Label{...}`，快照带 id）；
    取不到才退回 month_heading() 的启发式（「第一个 ≤20 字且含『年』『月』的 Label」）
    —— 启发式容易被新加的短文案抢先命中，只作兜底。
    """
    s = s if s is not None else snap()
    n = find_id(s, "month_title")
    t = str(n.get("t") or "") if n else (month_heading(s) or "")
    runs = _digits_runs(t)
    if len(runs) < 2:
        return None
    return int(runs[0]), int(runs[1])


def _midx(ym):
    """(年, 月) → 单调递增整数，便于比较与求差。"""
    return ym[0] * 12 + (ym[1] - 1)


def shift_month(ym, k):
    """(年, 月) 偏移 k 个月。"""
    t = _midx(ym) + k
    return (t // 12, t % 12 + 1)


def click_month_once(label, before, timeout=10.0, interval=0.25):
    """点一次翻月按钮，并**等到标题真的变了**。

    返回 (新月份, True)  —— 标题已变化；
        (before, False) —— 超时未变（这次点击没被宿主处理），调用方应重试。

    `wait_btn` 只保证按钮**存在**，不保证点击被**处理**；上一步点击还在渲染时
    紧随的点击会被吞掉。本函数只断言「标题变了没有」，不引入任何与平台或渲染
    速度绑定的时间常量 —— 所以 Windows / macOS / 更慢的机器上行为一致。

    ⚠️ timeout 从 4s 加到 10s（2026-10-09）：宿主的点击是**排队异步落地**的，
    实测偶发延迟超过 4 秒 —— 于是这里判超时、调用方重试，**多点的那个 `<`
    稍后才落地**，把月份多翻一格 ⇒ 表现为「状态滞后一步」。
    这里宁可多等（最坏情况是本来就点空了），也不要因为等不及而重复点击。
    """
    n, s = wait_btn(label)
    if not n:
        return before, False
    click_node(n)
    deadline = time.time() + timeout
    while time.time() < deadline:
        ym = month_of()
        if ym is not None and ym != before:
            return ym, True
        time.sleep(interval)
    return before, False


def goto_month(y, m, budget=48):
    """闭环翻到指定 (年, 月)。已在目标月则一步不动。

    每一轮都按**当前位置**重算方向，所以「漏点」能补、「多走一格」能自己退回来。
    返回 (实际月份, 是否到达)。
    """
    target = (int(y), int(m))
    cur = month_of()
    if cur is None:
        return None, False
    while cur != target and budget > 0:
        budget -= 1
        label = ">" if _midx(target) > _midx(cur) else "<"
        cur, moved = click_month_once(label, cur)
        if not moved:
            time.sleep(0.4)      # 漏点：让宿主喘口气，下一轮再试
    return cur, cur == target


def toolbar_y(s):
    n = btn(s, "导入")
    return n["r"][1] if n else 10 ** 9


def festival_lines(s):
    """取节假日说明区的两行文本 → (节日行, 放假安排行)。

    ★ 2026-10-01 改为**按 id 定位**（原来是按坐标猜）。

    为什么必须换：旧规则是「ty=Label、宽>80、y 在 320 与工具条之间，取 y 最小的两个」，
    靠一句「页头大标题(≈84) 和副标题(≈130) 都远在上面，被 y > 320 挡掉」成立。
    新的首页在月历**上方**加了一条吉祥物文案（mascot_say，宽 312、y≈321），
    它成了「y 最小的宽 Label」，于是被当成节日行 —— run_festival 报出来的是
    「节日行写出中秋 — 实际：今天 9 月 30 日 · 0 个日程…」，看着像产品没渲染，
    其实产品侧 fest_line 一直都在（快照里也在），只是定位器挑错了控件。

    ⚠️ 旧注释说「这两行的 id 快照里不带，只给 '-'」——**这条已经过时**。
    用 `:=` 声明过的 Label（fest_line / fest_line2 / mascot_say / egg_today_tag …）
    快照里都带 id，实测可用。按 id 定位与布局完全解耦，以后再挪位置也不会误判。
    """
    a = find_id(s, "fest_line")
    b = find_id(s, "fest_line2")
    return (a.get("t") if a else None, b.get("t") if b else "")


# 向后兼容：原来只取一行的调用点
def festival_line(s):
    return festival_lines(s)[0]


def festival_source(s):
    for n in s:
        t = str(n.get("t") or "")
        if n.get("ty") in ("Button", "ButtonFlat") and t.startswith("节日"):
            return t
    return None


def holiday_marks(s):
    """日历格子里的小标记。

    ⚠️ 放假绿点是**纯 View、无文本**，快照 JSON 不带颜色（只有 i/ty/r/w），
       所以只能按尺寸 + 数量统计，颜色必须靠截图肉眼确认
       （见 tools/run_festival.sh 产出的 PNG 证据）。

    ⚠️⚠️ 尺寸过滤是必须的（2026-09-30 踩过）：界面上还有两种同色系小方块，
       不是日期标记，混进来会直接算错数 ——
         · `fest_bar` 说明行前面的项目符号 5x5（main.splash:2138）
         · 状态条前面的项目符号 6x6（main.splash:2232）
       日历格子里的事件点 / 放假点 / 照常上班点**都是 3.5**（渲染成 4x4），
       所以这里只收 3~4.5px。文档里写死尺寸的只有这三处，改版时要同步。
    """
    ban = [n["r"] for n in s if str(n.get("t") or "") == "班"]
    dots = []
    for n in s:
        r = n.get("r") or [0, 0, 0, 0]
        if n.get("ty") not in ("View", "ViewFlat", "RoundedView", "CircleView"):
            continue
        if 3.0 <= r[2] <= 4.5 and 3.0 <= r[3] <= 4.5:
            dots.append(r)
    return {"班": ban, "日历格子点": dots}


# ── 标记点颜色语义（main.splash 的调色板，改色时必须同步这里）────────────
#    放假          → c_ok      #15803d  绿
#    节日但照常上班 → c_ink2    #6b6560  深灰（用户要的「小黑点」）
#    事件          → c_accent  #b4531f  赤陶
#    今天格实心底   → c_ink     #191714  暖黑（若采样窗口蹭到会单列出来）
DOT_PALETTE = [
    ("OK",      (0x15, 0x80, 0x3d)),
    ("WORK",    (0x6b, 0x65, 0x60)),
    ("EVENT",   (0xb4, 0x53, 0x1f)),
    ("INK",     (0x19, 0x17, 0x14)),
]
DOT_TOL = 70          # 单通道距离上限；抗锯齿边缘色距离更大，会被自然滤掉


def _classify(rgb):
    """把一个像素归到最近的语义色。超出容差返回 None（背景/抗锯齿边缘）。"""
    best, bd = None, 10 ** 9
    for name, (r, g, b) in DOT_PALETTE:
        d = abs(rgb[0] - r) + abs(rgb[1] - g) + abs(rgb[2] - b)
        if d < bd:
            best, bd = name, d
    return best if bd <= DOT_TOL else None


def dot_kinds(w, ch, buf, rect, sc, radius=2):
    """在标记点中心取 (2r+1)² 邻域，**按像素投票**定语义色。

    ⚠️ 为什么不能取中位/最深像素（2026-09-30 实测踩过）：
       · 3.5px 的点在当前 DPI 下只有约 6px，边缘一圈全是抗锯齿过渡色
         → 3×3 中位经常取到 #88be9c / #52a170 这种「浅绿」，无法断言；
       · 而绿 #15803d 与深灰 #6b6560 的**亮度几乎相同**（≈100 vs ≈102），
         「取最深像素」同样区分不出来。
       投票法最稳：点芯至少 4~5 个像素是纯色，边缘杂色因超容差被丢弃。
    """
    cx = int(round((rect[0] + rect[2] / 2.0) * sc))
    cy = int(round((rect[1] + rect[3] / 2.0) * sc))
    votes = {}
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            k = _classify(zoom_px(w, ch, buf, cx + dx, cy + dy))
            if k:
                votes[k] = votes.get(k, 0) + 1
    if not votes:
        return "NONE"
    return max(votes.items(), key=lambda kv: (kv[1], -len(kv[0])))[0]


def zoom_px(w, ch, buf, x, y):
    """惰性导入 zoom，避免无截图需求时也去解析 PNG。"""
    import zoom
    return zoom.px(w, ch, buf, x, y)[:3]


def _emit(s):
    """输出 KEY=value 行，方便 shell 侧做 grep 断言。"""
    m = holiday_marks(s)
    fest, hol = festival_lines(s)
    print("MONTH=" + str(month_heading(s)))
    print("FEST=" + str(fest))
    print("HOL=" + str(hol))
    print("SRC=" + str(festival_source(s)))
    print("BAN=" + str(len(m["班"])))
    print("DOTS=" + str(len(m["日历格子点"])))
    print("TEXTS=" + " | ".join(
        str(n.get("t")) for n in s
        if n.get("t") and len(str(n.get("t"))) <= 40 and str(n.get("t")).strip()
    ))


def wait_btn(label, timeout=12.0, interval=0.4):
    """轮询等待按钮出现 → (node, snapshot)；超时返回 (None, 最后一次快照)。

    ⚠️⚠️ 为什么必须轮询（2026-09-30 修）：解析是**分块续跑**的
       （单 handler 200000 指令 / 64ms 双限，见 main.splash 顶部说明），
       点「解析」后预览条要跨若干帧才建出来。原来固定 sleep 0.6s 就抓快照，
       实测此刻「写入」按钮**还没进布局树** → `write` 报
       「FAIL: 找不到按钮『写入』」，而 1 秒后它明明就在 r=[329,798,51,28]。
       这是**测试脚本的竞态**，不是应用的 bug —— 用固定 sleep 测分块任务
       早晚会翻车，改成轮询。
    """
    deadline = time.time() + timeout
    s = snap()
    while True:
        n = btn(s, label)
        if n:
            return n, s
        if time.time() >= deadline:
            return None, s
        time.sleep(interval)
        s = snap()


def wait_text(sub, timeout=12.0, interval=0.4):
    """轮询等待某段文本出现（用于「预览 · N 个事件尚未写入」这类状态断言）。"""
    deadline = time.time() + timeout
    s = snap()
    while True:
        n = any_text(s, sub)
        if n:
            return n, s
        if time.time() >= deadline:
            return None, s
        time.sleep(interval)
        s = snap()


def wait_id(wid, timeout=10.0, interval=0.3):
    """轮询等待某个 id 的控件进布局树 → (node, snapshot)。

    ⚠️⚠️ 为什么需要它（2026-09-30 又踩一次）：`octo run --detach` 在
       **第一帧画出**后就返回，但按钮/面板进布局树可能还差一两帧。
       `open` 原来用一次性的 `need(snap(), "导入")`，宿主刚起来时可能扑空 →
       open 静默失败 → 后面的 fill/parse/write 全部找不到目标 →
       **整条截图链跑出一张「已加载 0 个事件」的空状态图**，
       而脚本把每步输出都 `>/dev/null` 了，一点提示都没有。
       凡是「点完要等界面变化」的地方，一律轮询，不要一次性取值。
    """
    deadline = time.time() + timeout
    s = snap()
    while True:
        n = find_id(s, wid)
        if n:
            return n, s
        if time.time() >= deadline:
            return None, s
        time.sleep(interval)
        s = snap()


def need_wait(s, label):
    return need(s, label)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "texts"

    if cmd == "texts":
        show_texts(snap())

    elif cmd == "dump":
        for n in snap():
            print(f"{n.get('i')} [{n.get('ty')}] r={n.get('r')}  {str(n.get('t'))[:50]!r}")

    elif cmd == "open":
        # 轮询而不是一次性找：宿主刚 detach 返回时按钮可能还没进布局树（见 wait_id 注释）
        n, _ = wait_btn("导入")
        if not n:
            print("FAIL: 找不到按钮「导入」")
            return
        print("click 导入", click_node(n))
        e, _ = wait_id("entry")
        print("entry 存在:", e is not None)

    elif cmd == "wipe":
        if wipe_entry():
            print("输入框已清空")
        else:
            print("FAIL: entry 不在树里，先 open")

    elif cmd == "fill":
        # ⚠️ newline="" 必须加：默认的 universal newlines 会把 ICS 的 CRLF
        #    吃成 LF，灌进去的字节数和文件对不上（实测 1235 → 1177），
        #    做「原样往返」断言时就成了两个不可比的量。
        data = io.open(sys.argv[2], encoding="utf-8", newline="").read()
        e, _ = wait_id("entry")
        if not e:
            print("FAIL: entry 不在树里，先 open")
            return
        click_node(e)
        # ★ 2026-10-01：灌完**校验真实内容**，不符就重来。
        #   为什么必须校验：清空后队列里可能残留尚未落地的删除键，会把紧接着打进去的
        #   字**吃掉** —— 实测 broken-events.ics 紧跟在 shell-only.ics 之后就变成 0 字符
        #   （同一个文件在全新宿主里第一次灌入则完全正常），而状态条报的是上一个夹具的
        #   错，极具误导性。靠 sleep 猜队列排空时长不可靠（试过 0.4s / 1.2s 都会漏），
        #   直接比对结果最稳，也与平台无关。
        got = ""
        for attempt in range(5):
            wipe_entry(already_focused=True)
            type_text(data)
            # ⚠️ 必须**连续多次**读到完整才算稳：删除键异步落地，刚 type 完立刻读
            #    往往还是完整的，随后才被队列里残余的删除键吃掉。
            #    （试过读一次 + sleep 1.5s，会「打地鼠」：这一份对了、下一份又变 0。）
            #    重试时若输入框已空，wipe_entry 不会再发任何删除键，于是队列自然排空，
            #    所以这个循环是**收敛**的。
            stable = 0
            for _ in range(4):
                time.sleep(0.9)
                got = entry_text() or ""
                if len(got) < len(data):
                    break
                stable += 1
            if stable >= 3:
                break
            print("  重试 %d/5：期望 %d 字符，实得 %d"
                  % (attempt + 1, len(data), len(got)))
        print("已灌入 %d 字符（实得 %d）" % (len(data), len(got)))
        if len(got) < len(data):
            print("FAIL: 灌入内容不完整（输入框里只有 %d / %d 字符）"
                  % (len(got), len(data)))

    elif cmd == "parse":
        n, _ = wait_btn("解析")
        if n:
            print("click 解析", click_node(n))
            # 解析分块续跑 → 预览条要等，不能固定 sleep（见 wait_btn 注释）
            nl, s = wait_text("预览 ·", timeout=15.0)
            if nl:
                print("预览条已出现:", str(nl.get("t"))[:40])
            else:
                print("FAIL: 15s 内没有出现预览条")
                print("  现有按钮:", buttons_of(s))
            show_texts(s)

    elif cmd == "write":
        n, s = wait_btn("写入")
        if n:
            print("click 写入", click_node(n))
            time.sleep(0.6)
            show_texts(snap())
        else:
            print("FAIL: 找不到按钮「写入」")
            print("  现有按钮:", buttons_of(s))

    elif cmd == "cancel":
        n = need(snap(), "取消")
        if n:
            print("click 取消", click_node(n))
            time.sleep(0.4)

    elif cmd == "about":
        n, s = wait_btn("关于")
        if n:
            print("click 关于", click_node(n))
            time.sleep(0.4)
        else:
            print("FAIL: 找不到按钮「关于」")

    elif cmd == "clear":
        n, s = wait_btn("清空事件库")
        if n:
            print("click 清空事件库", click_node(n))
            time.sleep(0.4)
        else:
            print("FAIL: 找不到按钮「清空事件库」")

    elif cmd == "export":
        n, s = wait_btn("导出")
        if n:
            print("click 导出", click_node(n))
            time.sleep(0.6)
            s = snap()
            e = find_id(s, "entry")
            if e:
                v = e.get("t") or e.get("v") or ""
                print(f"entry 长度={len(str(v))}")
                print("---- entry 内容 ----")
                print(str(v))
        else:
            print("FAIL: 找不到按钮「导出」")

    elif cmd == "more":
        n, s = wait_btn("详情")
        if n:
            print("click 详情", click_node(n))
            time.sleep(0.5)
            show_texts(snap())
        else:
            print("FAIL: 找不到按钮「详情」")
            print("  现有按钮:", buttons_of(s))

    elif cmd == "advice":
        n, s = wait_btn("应用建议")
        if n:
            print("click 应用建议", click_node(n))
            time.sleep(0.6)
            show_texts(snap())
        else:
            print("FAIL: 找不到按钮「应用建议」")
            print("  现有按钮:", buttons_of(s))

    elif cmd == "rollback":
        n, s = wait_btn("回滚")
        if n:
            print("click 回滚", click_node(n))
            time.sleep(0.6)
            show_texts(snap())
        else:
            print("FAIL: 找不到按钮「回滚」")
            print("  现有按钮:", buttons_of(s))

    elif cmd == "field":
        s = snap()
        for n in s:
            if n.get("ty") in ("TextInput", "TextInputFlat"):
                print(f"{n.get('i')} [{n.get('ty')}] r={n.get('r')} keys={sorted(n.keys())}")
                for k in ("t", "v", "text", "value"):
                    if k in n:
                        print(f"   {k} = {str(n[k])!r}")

    elif cmd == "entry":
        # 把输入框内容原样存到文件，供字段级比对（往返无损的硬证据）。
        # ⚠️ 快照里的文本可能被截断，所以同时打印长度，长度不符即视为不可信。
        out = sys.argv[2] if len(sys.argv) > 2 else ".runtime/entry.txt"
        s = snap()
        node = None
        for n in s:
            if n.get("ty") in ("TextInput", "TextInputFlat"):
                node = n
                break
        if node is None:
            print("FAIL: 找不到输入框")
            sys.exit(1)
        txt = ""
        # ⚠️ 2026-10-08（P0-3）：字段优先级必须是 **`val` 优先**，与
        #   `entry_text()`（:62-79）保持一致。原实现按 `t` 优先，而 `t` 是
        #   **渲染后的显示文本** —— 空输入框时 `t` 是占位提示
        #   （实测 'BEGIN:VCALENDAR …'），会把空态读成「有一串占位文字」，
        #   于是 run_conflict.sh 的导出断言打在占位提示上，而不是真实导出值。
        for k in ("val", "v", "value", "t", "text"):
            if k in node and node[k] is not None:
                txt = str(node[k])
                break
        io.open(out, "w", encoding="utf-8", newline="").write(txt)
        print(f"entry -> {out}  len={len(txt)}")
        for key in ("BEGIN:VCALENDAR", "RRULE:", "DESCRIPTION:", "ORGANIZER:",
                    "TZID=", "VALUE=DATE", "T140000Z", "SEQUENCE:", "UID:"):
            print(f"  {'OK ' if key in txt else 'MISS'} {key}")

    elif cmd == "dumpsnap":
        # 把**等渲染完成之后**的 /snap 原样写到文件。
        # 为什么需要（2026-10-09）：截图与「取点矩形」必须来自**同一时刻**，
        # 否则 dotcolor 会拿新布局的矩形去读旧截图的像素 ⇒ 整月错配。
        # 裸 curl /snap 不会等渲染，可能落在翻月后的重绘空窗里，
        # 导出一份**没有日历格子**的树（实测症状：DOTS/BAN 全为 0）。
        # 用法：python e2e.py dumpsnap <out.json>
        out_path = sys.argv[2] if len(sys.argv) > 2 else SNAP
        t0 = time.time()
        ok, s = _stable_consistent()
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"s": s}, f)
        print("SNAPSHOT=%s nodes=%d ready=%s stable=%s" % (
            out_path, len(s), _render_ready(s), "yes" if ok else "no"))
        if not ok:
            # 不静默放过：0 字节/半帧快照会让后续像素判定变成「（无）」，
            # 报出与真实原因无关的红。
            print("FAIL: 未能等到内容一致的稳定帧（等了 %.1fs）" % (time.time() - t0))

    elif cmd == "btn":
        # 按**按钮文案**点（不是坐标）。用于分区导航（待办/心情/目标/小知识）
        # 与视图切换（月/周/日）—— 这些按钮的位置会随面板开合而变，
        # 写死坐标必然扑空，所以只认文案。
        n, s = wait_btn(sys.argv[2])
        if n:
            print(f"click {sys.argv[2]}", click_node(n))
            time.sleep(0.5)
        else:
            print(f"FAIL: 找不到按钮「{sys.argv[2]}」")
            print("  现有按钮:", buttons_of(s))
            sys.exit(1)

    elif cmd == "click":
        click(float(sys.argv[2]), float(sys.argv[3]))
        print(f"clicked {sys.argv[2]},{sys.argv[3]}")

    elif cmd == "scroll":
        scroll(float(sys.argv[2]))
        print(f"scrolled dy={sys.argv[2]}")

    elif cmd == "cycle":
        # 切换节日来源（节日 中国 → 国际 → 全部 → 中国）。
        # ⚠️ 闭环（2026-10-08/09 加）：原来点一下就直接读，既不等也不校验，
        #   宿主偶发吞掉点击时 SRC 仍是旧值，而 run_festival.sh 那几处
        #   `cycle >/dev/null 2>&1` 又把输出丢了 ⇒ 整步静默地在旧来源上断言。
        #   现在：点 → 等文案真的变了 → **再稳定 0.35s** → 同一次调用里直接
        #   输出 fest（供 shell 断言），不给「确认」与「读取」之间留窗口。
        n, s = wait_btn("节日")
        if not n:
            print("FAIL: 找不到节日来源按钮")
            print("  现有按钮:", buttons_of(s))
            return
        before = str(n.get("t"))

        def _src():
            nn = btn(snap(), "节日")
            return str(nn.get("t")) if nn else None

        def _changed():
            v = _src()
            return v if (v is not None and v != before) else None

        click_node(n)
        ok, seen = _stable(_changed)
        if not ok:
            # 点击被宿主吞掉了：重发一次再等
            nn = btn(snap(), "节日")
            if nn:
                click_node(nn)
            ok, seen = _stable(_changed, tries=3)
        # ⚠️ `_stable` 返回 (bool, 谓词最后一次的值)，谓词返回的是**新文案本身**
        #   （不是 True）—— 取错会打印出 `SRC=True`（2026-10-09 踩过）。
        #⚠️ 再等「整帧内容一致」：切来源同样会分步更新，
        #   实测出现过按钮文案已是「节日 国际」、格子里国庆绿点还在的半帧。
        _, s_after = _stable_consistent(tries=4)
        after = str(festival_source(s_after) or seen or _src() or before)
        print(f"SRC={after}")
        print(f"SRC_BEFORE={before}")
        if not ok:
            print("WARN: 节日来源未发生变化（点击可能被宿主吞掉）")
        else:
            _emit(s_after)

    elif cmd == "goto":
        # 绝对定位（推荐）：python e2e.py goto 2026-09
        # 与「今天几号」无关，任何日期跑都对 —— 测哪个月就 goto 哪个月。
        if len(sys.argv) < 3 or "-" not in sys.argv[2]:
            print("FAIL: 用法 e2e.py goto YYYY-MM")
            return
        y, m = sys.argv[2].split("-", 1)
        ty, tm = int(y), int(m)
        # ⚠️ 必须「整轮重试直到稳定」，而不是 goto_month 走一遍就收工
        #（2026-10-09 实测，连跑 5 轮有 2 轮红）：
        #   宿主的点击是**排队异步落地**的，延迟可以超过 click_month_once 的
        #   4 秒等待窗。表现是**状态滞后一步**：本步goto 2026-09 读到的还是
        #   10 月（报「翻月失败」），而下一步 goto 2026-10 反而读到了 9 月 ——
        #   看着像脚本自己把月份翻反了。
        #   所以：外层循环反复「goto_month + 稳定确认」，直到某一次真正停稳。
        cur, ok, stable = None, False, False
        s = None
        for attempt in range(6):
            cur, ok = goto_month(ty, tm)
            # ⚠️ 用「整帧内容一致」而不是「月份标题等于目标」：
            #   宿主分步更新，实测抓到过标题已是 10 月、格子与标记点还是 9 月的
            #   半帧 —— 只看标题会放它过去，然后 fest 输出上个月的点数。
            stable, s = _stable_consistent()
            if ok and stable and month_of(s) == (ty, tm):
                break
        if s is None:
            s = snap()
        cur2 = month_of(s) or cur
        _emit(s)
        print("MONTHS_TARGET=%s MONTHS_ACTUAL=%s STABLE=%s ATTEMPTS=%d" % (
            sys.argv[2], ("%d-%02d" % cur2) if cur2 else "None",
            "yes" if stable else "no", attempt + 1))
        if not (ok and stable):
            print("FAIL: 未能稳定停留在 %s（实际 %s）" % (sys.argv[2], cur2))

    elif cmd == "months":
        # 相对翻月。★ 2026-10-01 改为**闭环**：算出目标月后走 goto_month，
        # 每一步都校验标题是否真的变了（漏点补点、多走一格倒回来）。
        # 原来「连点 abs(k) 次、点完就取快照」，把正确性押在「每一次点击都会被
        # 宿主及时处理」上 —— 那是时序假设，不是契约。
        k = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        cur = month_of()
        if cur is None:
            print("FAIL: 读不到月历标题（形如「2026 年 10 月」）")
            return
        target = shift_month(cur, k)
        cur, ok = goto_month(target[0], target[1])
        _emit(snap())
        print("MONTHS_TARGET=%d-%02d MONTHS_ACTUAL=%s" % (
            target[0], target[1], ("%d-%02d" % cur) if cur else "None"))
        if not ok:
            print("FAIL: 翻月未到达目标（目标 %d-%02d，实际 %s）"
                  % (target[0], target[1], cur))

    elif cmd == "fest":
        _emit(snap())

    elif cmd == "dotcolor":
        # 回读截图像素，给出日历格子里每个小标记的**实际颜色语义**。
        # 为什么必须做这一步：/snap 快照只有 i/ty/r/w，**不带颜色**，
        # 所以「放假是绿点、照常上班是黑点、调休写班字」只能靠回读像素验证。
        #
        # ⚠️⚠️ 用法：`python e2e.py dotcolor <png> [snapshot.json]`
        #   第二个参数是**与该png 同一次快照**导出的 /snap JSON。
        #   必须传！否则这里会重新 `snap()` 拿**当前实时**布局，
        #   而png 是几十毫秒~几百毫秒前拍的 ——
        #   翻月/ 切节日来源时两者会**错配一个月**（2026-10-08 实测踩到：
        #   文本断言读的是新月份、像素断言读的是旧截图，于是
        #   「期望 8 个点、实际 5 个」这种完全看不出所以然的红）。
        #   错配的表现很像「应用画错了」，但根因是测试自己拿了两个时刻的证据。
        # ⚠️ 这里**不要**再`import json`：json 已在模块顶层导入过。
        #   在 main() 里重复 import 会让 Python 把 `json` 判定为**函数局部变量**，
        #   于是同一函数中更早的 dumpsnap 分支（2026-10-09）一用 json 就炸
        #   UnboundLocalError —— 表现为所有同源快照都是 0 字节、像素判定全空。
        import zoom
        png = sys.argv[2] if len(sys.argv) > 2 else ".runtime/shot.png"
        snapfile = sys.argv[3] if len(sys.argv) > 3 else ""
        w, h, ch, buf = zoom.read_png(png)
        sc = w / 412.0
        if snapfile:
            with open(snapfile, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # 与 snap() 同款解包：/snap 的顶层是 {"s": [...]}（不是 nodes/tree）。
            # 之前误按 nodes/tree 找→ 永远拿到空列表 ⇒ 所有像素判定变成「（无）」。
            s = raw["s"] if isinstance(raw, dict) and "s" in raw else raw
        else:
            s = snap()
        m = holiday_marks(s)
        kinds, cols = [], []
        for r in m["日历格子点"]:
            k = dot_kinds(w, ch, buf, r, sc)
            kinds.append(k)
            cols.append({
                "OK": "#15803d", "WORK": "#6b6560",
                "EVENT": "#b4531f", "INK": "#191714",
            }.get(k, "??????"))
        print("DOTKIND=" + ",".join(kinds))
        print("DOTCOLORS=" + ",".join(cols))
        print("DOTXY=" + " ".join("%d,%d" % (r[0], r[1]) for r in m["日历格子点"]))
        print("BANXY=" + " ".join("%d,%d" % (r[0], r[1]) for r in m["班"]))
        # ⚠️⚠️ 2026-10-09（v0.5.0 P2-5）：原来只判**第一个**「班」
        #   （bk = dot_kinds(..., m["班"][0], sc)）。而holiday_marks 会收集
        #   **全部** text=="班" 的节点 ⇒ BAN 的**个数**是全的、**颜色**只判第1 个。
        #   后果：某月有多个调休日时（比如 10 月前后各有一个），第 2 个以后
        #   画错颜色不会被告警测出来 —— 数量对得上，颜色错了却全绿。
        #   现在对**每一个**都取色，输出逗号分隔序列；
        #   同时给出 BAN_KIND_DETAIL（含坐标），红了能直接定位是哪一个。
        if m["班"]:
            bks = [dot_kinds(w, ch, buf, r, sc) for r in m["班"]]
            print("BANKIND=" + ",".join(bks))
            print("BAN_KIND_DETAIL=" + " ".join(
                "%d,%d=%s" % (r[0], r[1], k) for r, k in zip(m["班"], bks)))
        else:
            print("BANKIND=")
            print("BAN_KIND_DETAIL=")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
