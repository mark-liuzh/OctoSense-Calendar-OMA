#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""octo CLI 与宿主抓帧的公共通道（2026-10-12 · v0.5.2 W1-1）。

为什么抽出来：`newflow.py` / `rrule_guard.py` / `featflow.py` 三个驱动脚本
各自写了一遍 `OCTO = os.environ.get("OCTO", "D:/Projects/OctoScript-App-Design-Flow/tools/octo")`。
那是个**开发者本机的 Windows 绝对路径** —— Linux / Windows 干净克隆上必然找不到，
subprocess 抛FileNotFoundError，而这三个脚本里 shot() 各被调用好多次，
于是一条根因被放大成七八条「打不开图片」的假 FAIL（Linux 测试报告的 run_new 10 条红）。

三处各修一遍，下一个脚本还会再犯。统一收口在这里。

解析顺序：环境变量 OCTO → 仓库内 tools/octo → PATH。
**找不到不是致命错误**：抓帧本质上只需要宿主远程控制桥的 `/g?raw=1`，
e2e 已经在用同一个 opener 直连了。octo 只是官方 CLI 包装，有它就用它
（保留它 --settle 的语义），没有就直接抓帧 —— 这样干净克隆上流程**真的能跑**。
"""
import io
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ⚠️ 直连抓帧必须清空 ProxyHandler：本机 http_proxy 会把发往127.0.0.1 的
#    请求也劫持走，返回 502 或上一帧陈旧截图 —— 症状极具误导性
#    （与 e2e._OPENER 同一套理由）。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

SETTLE = 0.9   # 等价于 `octo shot --settle 0.9`


def resolve_octo():
    """→ octo CLI 路径，找不到返回 None（调用方须走 shot_via_host）。"""
    env = os.environ.get("OCTO")
    if env:
        return env
    local = os.path.join(ROOT, "tools", "octo")
    if os.path.exists(local):
        return local
    return shutil.which("octo")


OCTO = resolve_octo()


def describe():
    """给人看的一句话：这个脚本用的是哪条抓帧通道。"""
    return OCTO or "（未找到 octo CLI → 直连宿主 /g?raw=1 抓帧）"


def shot_via_host(base, out, tag="", settle=SETTLE, retries=2):
    """直连宿主远程控制桥抓一帧存到 out。返回 out。

    ⚠️ 失败**抛异常**，不静默返回路径 —— 静默会让调用方拿着一个不存在的文件
    去 open，报出的错是「打不开 PNG」，与真因（宿主没在跑 / 端口不对）隔了三层。

    ⚠️ `grab request limit reached (64)` 这类**瞬时**拒绝要重试：宿主对**未完成**
       的抓帧请求设了全局上限 64（remote.rs `MAX_PENDING_GRABS` / `PENDING_GRABS`）。
       一次跑 8 条流程、共几十次抓帧时，前面几次若还没回收就会撞上限。
       它是背压信号，不是错误 —— 重试（并等一会儿让在途的收尾）才是正解。
    """
    last = None
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(1.2 * attempt)
        try:
            return _grab_once(base, out, tag, settle)
        except RuntimeError as e:
            last = e
            if "HTTP 404" not in str(e):
                raise
    raise last


def _grab_once(base, out, tag, settle):
    if settle:
        time.sleep(settle)
    url = "%s/g?raw=1&t=%d-%s" % (base, int(time.time() * 1000), tag)
    try:
        with _OPENER.open(url, timeout=25) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        # ⚠️⚠️ 必须把 body 读出来：宿主把**所有**抓帧失败都表达成
        #   `Out::Json(404, {"err": "..."})`（remote.rs:1792的 err()），
        #   而 404 这个状态码本身**不携带任何原因** —— "no windows" /
        #   "grab request limit reached (64); retry after pending grabs finish" /
        #   "no matching window" 全是 404。
        #   只报「HTTP Error 404」等于把真因丢掉（本轮就这么丢过一次，
        #   害我以为宿主挂了）。这里解析 err 字段带进异常。
        try:
            payload = e.read().decode("utf-8", "replace")
        except Exception:                      # noqa: BLE001 - 读 body 失败不该盖掉原异常
            payload = ""
        reason = ""
        m = re.search(r'"err"\s*:\s*"([^"]*)"', payload)
        if m:
            reason = "：%s" % m.group(1)
        raise RuntimeError("抓帧被宿主拒绝（HTTP %s%s，tag=%s）"
                           % (e.code, reason, tag))
    if len(body) < 1000 or body[:4] != b"\x89PNG":
        raise RuntimeError("直连抓帧失败（收到 %d 字节，头 %r，不是 PNG）"
                           "—— 宿主可能没在跑，或 OCTO_PORT 不对"
                           % (len(body), body[:16]))
    d = os.path.dirname(out)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(out, "wb") as f:
        f.write(body)
    return out


def shot(octo, base, out, tag="", settle=SETTLE, py=None):
    """抓一帧到 out（优先用 octo CLI，失败即抛）。返回 out。

    ⚠️ 检查 returncode、并把 stderr 尾部带进异常信息：
       原实现一律 `subprocess.run(..., capture_output=True)` 且从不看退出码，
       octo 不存在 / 抓帧失败时**照样返回一个路径**，后面的 px_at() 才去
       open 一个不存在的文件抛 FileNotFoundError —— 一条根因放大成 N 条假 FAIL。
    """
    if octo:
        p = subprocess.run([py or sys.executable, octo, "shot", base.rsplit(":", 1)[-1],
                            out, "--settle", str(settle)],
                           capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError("octo shot 失败（tag=%s，exit=%d）：%s"
                               % (tag, p.returncode,
                                  (p.stderr or p.stdout or "").strip()[-300:]))
        if not os.path.exists(out):
            raise RuntimeError("octo shot 退出码 0 但没产出文件：%s" % out)
        return out
    return shot_via_host(base, out, tag, settle)