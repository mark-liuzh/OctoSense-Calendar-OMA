#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门禁：`reschedule()` 是唯一写入点，且**必须递增 SEQUENCE + 刷新 DTSTAMP**。

为什么需要这道门禁（2026-10-11 · v0.5.2 W2-1）：
  `reschedule()` 是规则引擎与模型共用的**唯一**写入点（AGENTS.md 硬性要求第 5 条）。
  v0.5.1 及以前它是 `sequence: e.sequence` —— 原样透传，改期多少次序号都不变。
  后果对外是静默的：任何标准日历客户端按 RFC 5545 §3.8.7.4 判断版本新旧，
  会认为「这条从没被改过」⇒ **静默丢弃我们的改期结果**，用户看到的是「改了但没生效」。

  这类缺陷不会让宿主报任何错（`[E]` 数仍是 0）、界面也一切正常，
  只有把导出文件拿给别的日历软件才知道错了 —— 所以必须静态拦。

同时守住两条不变量：
  ① 全文**只有一处** `events[k] = {` 重建事件对象（唯一写入点）。
     多一处就会漂移 —— v0.4.x 就因为两处各写一遍 `events[k] = {...}`，
     修了 `start_utc` 的 `Z` 后缀只改一处，往返无损当场回归。
  ② 那唯一一处必须同时含 `sequence: ... + 1` 与 `dtstamp: now_dtstamp()`
     （RFC 5545 §3.8.7.2 与 §3.8.7.4 要求二者**成对**更新）。

纯 Python、秒级、不起宿主。
"""
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def fn_body(src, name):
    """取 `fn <name>(...) { ... }` 的函数体（按大括号配平，不靠正则猜）。"""
    m = re.search(r"^fn %s\s*\(" % re.escape(name), src, re.M)
    if not m:
        return None
    start = src.index("{", m.end() - 1)
    depth, i = 0, start
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    return None


def main(path):
    src = io.open(path, encoding="utf-8").read()
    fails = []

    # ── ① 唯一写入点 ────────────────────────────────────────────────
    writes = [m.start() for m in re.finditer(r"events\[[^\]]+\]\s*=\s*\{", src)]
    # 排除注释里提到的情况（注释不会匹配这个模式，但保险起见按行过滤）
    real = [w for w in writes
            if not src[src.rfind("\n", 0, w) + 1:w].lstrip().startswith("//")]
    if len(real) != 1:
        line = src[:real[0]].count("\n") + 1 if real else 0
        fails.append("① 唯一写入点：找到 %d 处 `events[k] = {`，应为 1（首处在第 %d 行）"
                     % (len(real), line))
        print("  [FAIL] ① 唯一写入点：%d 处" % len(real))
        for w in real:
            print("         第 %d 行" % (src[:w].count("\n") + 1))
    else:
        print("  [PASS] ① 唯一写入点：全文只有 1 处 `events[k] = {`（第 %d 行）"
              % (src[:real[0]].count("\n") + 1))

    # ── ② reschedule 里必须同时递增 SEQUENCE + 刷新 DTSTAMP ─────────
    body = fn_body(src, "reschedule")
    if body is None:
        fails.append("② 找不到 fn reschedule()")
        print("  [FAIL] ② 找不到 fn reschedule()")
    else:
        code = "\n".join(l for l in body.split("\n")
                         if not l.strip().startswith("//"))
        # SEQUENCE：必须出现 `sequence:` 且右值含 `+ 1`
        seq = re.search(r"sequence:\s*([^,\n]+)", code)
        if not seq:
            fails.append("② reschedule() 没有写 sequence 字段")
            print("  [FAIL] ② reschedule() 没有写 sequence")
        elif not re.search(r"\+\s*1\b", seq.group(1)):
            fails.append("② reschedule() 的 sequence 没有 +1（实得 `%s`）"
                         % seq.group(1).strip())
            print("  [FAIL] ② sequence 没有 +1（实得 `%s`）" % seq.group(1).strip())
        elif re.search(r"e\.sequence\s*[,}]", seq.group(1)):
            fails.append("② reschedule() 的 sequence 仍是原样透传 e.sequence")
            print("  [FAIL] ② sequence 仍是原样透传")
        else:
            print("  [PASS] ② reschedule() 递增 SEQUENCE：`%s`" % seq.group(1).strip())

        ds = re.search(r"dtstamp:\s*([^,\n]+)", code)
        if not ds:
            fails.append("② reschedule() 没有写 dtstamp 字段")
            print("  [FAIL] ② reschedule() 没有刷新 dtstamp")
        elif "e.dtstamp" in ds.group(1):
            fails.append("② reschedule() 的 dtstamp 仍是原样透传 e.dtstamp")
            print("  [FAIL] ② dtstamp 仍是原样透传")
        else:
            print("  [PASS] ② reschedule() 刷新 DTSTAMP：`%s`" % ds.group(1).strip())

    # ── ③ now_dtstamp 必须存在且格式正确 ────────────────────────────
    nd = fn_body(src, "now_dtstamp")
    if nd is None:
        fails.append("③ 找不到 fn now_dtstamp()")
        print("  [FAIL] ③ 找不到 fn now_dtstamp()")
    else:
        ok = ('pad8' in nd and 'pad2' in nd and '"T"' in nd and '"Z"' in nd)
        if not ok:
            fails.append("③ now_dtstamp() 没有拼出 YYYYMMDDTHHMMSSZ")
            print("  [FAIL] ③ now_dtstamp() 格式不全（要 pad8 + pad2 + T + Z）")
        else:
            print("  [PASS] ③ now_dtstamp() 产出 YYYYMMDDTHHMMSSZ")

    # ── ④ 事件对象的字段表必须处处列全（2026-10-11 实测真回归）──────
    #   Splash 的「整体替换」写法 `events[k] = { … }` 要求**列全所有字段**：
    #   漏一个键，之后任何地方读它都会抛 `property X not found in prototype
    #   chain`，而抛错之后**该实例的后续写操作全部静默失效**。
    #   本轮真的踩了：W3-1 给事件加了 extra / extra_kinds，
    #   reschedule 重建对象时没带上 ⇒ 改期一次，那条事件的提醒/分类/参会人
    #   就永久没了，而界面不报错、导出看着也正常。
    base = fn_body(src, "new_event")
    if base is None:
        fails.append("④ 找不到 fn new_event()（字段表的基准）")
        print("  [FAIL] ④ 找不到 fn new_event()")
        else_fields = None
    else:
        else_fields = set(re.findall(r"(\w+)\s*:", base))
        print("  [PASS] ④ 基准 new_event() 有 %d 个字段" % len(else_fields))

    if else_fields:
        for fname in ("reschedule", "with_extra"):
            b = fn_body(src, fname)
            if b is None:
                fails.append("④ 找不到 fn %s()" % fname)
                print("  [FAIL] ④ 找不到 fn %s()" % fname)
                continue
            code = "\n".join(l for l in b.split("\n")
                             if not l.strip().startswith("//"))
            got = set(re.findall(r"(\w+)\s*:", code))
            missing = sorted(else_fields - got)
            if missing:
                fails.append("④ %s() 重建对象时漏了字段：%s"
                             % (fname, "、".join(missing)))
                print("  [FAIL] ④ %s() 漏字段：%s" % (fname, "、".join(missing)))
            else:
                print("  [PASS] ④ %s() 列全 %d 个字段"
                      % (fname, len(else_fields - {"extra", "extra_kinds"})))

    print()
    if fails:
        print("writepoint 未通过 —— %d 项：" % len(fails))
        for f in fails:
            print("  · %s" % f)
        return 1
    print("writepoint: 唯一写入点 + SEQUENCE/DTSTAMP 递增 全对")
    return 0


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "bundle", "main.splash")
    sys.exit(main(p))