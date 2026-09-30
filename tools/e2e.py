#!/usr/bin/env python3
"""OctoSense 远程驱动 · 端到端实测

用法：
  python e2e.py open          点「导入」展开面板
  python e2e.py fill <file>   把文件内容灌进输入框
  python e2e.py parse         点「解析」
  python e2e.py write         点「写入」
  python e2e.py cancel        点确认条「取消」
  python e2e.py texts         打印界面所有文本
  python e2e.py dump          打印全部节点
  python e2e.py click x y     点任意坐标
  python e2e.py scroll dy     在页面中央滚轮滚动（负值向上）
  python e2e.py about         点「关于」
  python e2e.py clear         点「清空事件库」
  python e2e.py export        点「导出」
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


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "texts"

    if cmd == "texts":
        show_texts(snap())

    elif cmd == "dump":
        for n in snap():
            print(f"{n.get('i')} [{n.get('ty')}] r={n.get('r')}  {str(n.get('t'))[:50]!r}")

    elif cmd == "open":
        n = need(snap(), "导入")
        if n:
            print("click 导入", click_node(n))
            print("entry 存在:", find_id(snap(), "entry") is not None)

    elif cmd == "fill":
        data = io.open(sys.argv[2], encoding="utf-8").read()
        e = find_id(snap(), "entry")
        if not e:
            print("FAIL: entry 不在树里，先 open")
            return
        click_node(e)
        type_text(data)
        print(f"已灌入 {len(data)} 字节")

    elif cmd == "parse":
        n = need(snap(), "解析")
        if n:
            print("click 解析", click_node(n))
            time.sleep(0.6)
            show_texts(snap())

    elif cmd == "write":
        n = need(snap(), "写入")
        if n:
            print("click 写入", click_node(n))
            time.sleep(0.6)
            show_texts(snap())

    elif cmd == "cancel":
        n = need(snap(), "取消")
        if n:
            print("click 取消", click_node(n))
            time.sleep(0.4)

    elif cmd == "about":
        n = need(snap(), "关于")
        if n:
            print("click 关于", click_node(n))
            time.sleep(0.4)

    elif cmd == "clear":
        n = need(snap(), "清空事件库")
        if n:
            print("click 清空事件库", click_node(n))
            time.sleep(0.4)

    elif cmd == "export":
        n = need(snap(), "导出")
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

    elif cmd == "more":
        n = need(snap(), "详情")
        if n:
            print("click 详情", click_node(n))
            time.sleep(0.5)
            show_texts(snap())

    elif cmd == "advice":
        n = need(snap(), "应用建议")
        if n:
            print("click 应用建议", click_node(n))
            time.sleep(0.6)
            show_texts(snap())

    elif cmd == "rollback":
        n = need(snap(), "回滚")
        if n:
            print("click 回滚", click_node(n))
            time.sleep(0.6)
            show_texts(snap())

    elif cmd == "field":
        s = snap()
        for n in s:
            if n.get("ty") in ("TextInput", "TextInputFlat"):
                print(f"{n.get('i')} [{n.get('ty')}] r={n.get('r')} keys={sorted(n.keys())}")
                for k in ("t", "v", "text", "value"):
                    if k in n:
                        print(f"   {k} = {str(n[k])!r}")

    elif cmd == "click":
        click(float(sys.argv[2]), float(sys.argv[3]))
        print(f"clicked {sys.argv[2]},{sys.argv[3]}")

    elif cmd == "scroll":
        scroll(float(sys.argv[2]))
        print(f"scrolled dy={sys.argv[2]}")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
