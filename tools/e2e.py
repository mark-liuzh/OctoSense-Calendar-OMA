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
  python e2e.py months n      月历向后翻 n 个月（n 为负则向前）
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


def snap():
    raw = _get("/snap")
    io.open(SNAP, "w", encoding="utf-8").write(raw)
    return json.loads(raw)["s"]


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
    """读输入框当前文本。找不到返回 None 区分「没有输入框」。"""
    s = s if s is not None else snap()
    for n in s:
        if n.get("ty") in ("TextInput", "TextInputFlat"):
            for k in ("t", "v", "text", "value"):
                if k in n and n[k] is not None:
                    return str(n[k])
            return ""
    return None


def wipe_entry(already_focused=False):
    """清空输入框：Ctrl+A 全选 → Backspace。

    ⚠️ 为什么必须这么做：宿主的文本输入走 remote.rs 的 route_key/route_text，
       只发 `Input::Text`，语义是**在光标处插入**，不是替换。所以「先 export 填充、
       再 fill 同一份 ICS」会把内容灌成两份 —— 实测 1235 字节变 2470 字节、
       12 个 UID 各出现 2 次，merge_events 认不出这是同一批事件，
       往返断言（期望新增 0 / 跳过 6）直接失效。
    """
    s = snap()
    e = find_id(s, "entry")
    if not e:
        return False
    if not already_focused:
        click_node(e)
    _get("/k?c=keya&ctrl=1&wait=1")
    time.sleep(0.25)
    _get("/k?c=backspace&wait=1")
    time.sleep(0.35)
    return True


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
        # ⚠️ 宿主的文本输入是**追加**语义（remote.rs route_key 只发
        #    Input::Text，不做替换）。不先清空就把同一份 ICS 灌两次 →
        #    实测 1235 字节变 2470、UID 各出现 2 次，往返断言直接失效。
        wipe_entry(already_focused=True)
        type_text(data)
        print(f"已灌入 {len(data)} 字节")

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
        for k in ("t", "v", "text", "value"):
            if k in node and node[k] is not None:
                txt = str(node[k])
                break
        io.open(out, "w", encoding="utf-8", newline="").write(txt)
        print(f"entry -> {out}  len={len(txt)}")
        for key in ("BEGIN:VCALENDAR", "RRULE:", "DESCRIPTION:", "ORGANIZER:",
                    "TZID=", "VALUE=DATE", "T140000Z", "SEQUENCE:", "UID:"):
            print(f"  {'OK ' if key in txt else 'MISS'} {key}")

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
        n, s = wait_btn("节日")
        if not n:
            print("FAIL: 找不到节日来源按钮")
            print("  现有按钮:", buttons_of(s))
            return
        before = str(n.get("t"))
        click_node(n)
        n2, s2 = wait_btn("节日")
        print(f"SRC={str(n2.get('t'))}")
        print(f"SRC_BEFORE={before}")

    elif cmd == "months":
        k = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        label = ">" if k >= 0 else "<"
        for _ in range(abs(k)):
            n, s = wait_btn(label)
            if not n:
                print(f"FAIL: 找不到翻月按钮 {label!r}")
                return
            click_node(n)
        _emit(snap())

    elif cmd == "fest":
        _emit(snap())

    elif cmd == "dotcolor":
        # 回读截图像素，给出日历格子里每个小标记的**实际颜色语义**。
        # 为什么必须做这一步：/snap 快照只有 i/ty/r/w，**不带颜色**，
        # 所以「放假是绿点、照常上班是黑点、调休写班字」只能靠回读像素验证。
        # 用法：python e2e.py dotcolor <png>
        # 输出：DOTKIND  = 每个点的语义（OK / WORK / EVENT / INK / NONE）
        #       DOTCOLORS= 每个点的代表色 hex，便于人眼对照
        #       DOTXY / BANXY / BANKIND
        import zoom
        png = sys.argv[2] if len(sys.argv) > 2 else ".runtime/shot.png"
        w, h, ch, buf = zoom.read_png(png)
        sc = w / 412.0
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
        if m["班"]:
            bk = dot_kinds(w, ch, buf, m["班"][0], sc)
            print("BANKIND=" + bk)
        else:
            print("BANKIND=")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
