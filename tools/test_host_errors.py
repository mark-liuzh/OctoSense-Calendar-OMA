#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""`host_error_count` / `HOST_ERROR_WHITELIST` 的行为夹具（2026-10-12 · v0.5.2 W1-6）。

为什么它属于 static_gate：这条硬指标「编译/运行错误数: 0」是对外的验收线，
而它的实现藏在 shell 里 —— 白名单正则一旦写宽，**真的应用错误会被静默扣掉**，
数字仍然显示 0，回归全绿。这是「指标本身失真」这类缺陷，本项目已经中过一次招
（2026-10-08 的 PulseAudio 白名单就是宽松匹配）。

为什么用 Python 构造日志而不用 shell here-doc：`HOST_ERROR_WHITELIST` 里有
`\[`、`[0-9]`、反斜杠，在 shell 里转义会引入新的歧义；夹具要验的正是**正则本身**，
多一层转义就没有意义了。这里让 bash 去 source _env.sh 并调用真的 host_error_count，
只把日志行作为数据传进去 —— 验的是生产代码路径，不是复制的一份逻辑。

纯 Python、秒级、不起宿主。
"""
import io
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))


def count(log_lines, env_extra=None):
    """把日志写进临时文件，**真的** bash 一遍 _env.sh 再调 host_error_count。

    返回 (返回值, 合并后的 stderr) —— `[W] 白名单命中` 提示走 stderr
    （打 stdout 会污染 `$(host_error_count …)` 的取值，见 _env.sh 里的说明）。
    """
    fd, path = tempfile.mkstemp(suffix=".log")
    try:
        with io.open(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(log_lines) + "\n")
        env = dict(os.environ)
        # 不继承调用方的白名单覆盖：本夹具要验的就是默认值。
        env.pop("HOST_ERROR_WHITELIST", None)
        env.update(env_extra or {})
        p = subprocess.run(
            ["bash", "-c",
             '. "$1/tools/_env.sh" 2>/dev/null; host_error_count "$2"',
             "_", ROOT, path],
            capture_output=True, text=True, env=env)
        return p.stdout.strip(), p.stderr
    finally:
        os.unlink(path)


print("=== host_error_count 口径 ===")

# 1. 干净日志 → 0
n, _ = count(["[I] splash compiled", "[I] ready"])
check("干净日志报 0", n == "0", "实得 %r" % n)

# 2. 一条真错误 → 1
n, _ = count(["[I] ready", "[E] splash:2316: runtime error: boom"])
check("一条真错误报 1", n == "1", "实得 %r" % n)

# 3. ★ W1-6 核心用例：含 "connection refused" 字样的**非音频**错误不得被扣除。
#    旧正则 `pulseaudio.*connection refused` 前的 `pulseaudio` + 后面任意内容，
#    会把这一行整行吃掉 ⇒ 报 0 ⇒ 指标失真。
n, _ = count([
    "[E] app:0: fetch failed: pulseaudio stream connection refused at host"]
)
check("非音频错误即使含 connection refused 也不被扣除", n == "1", "实得 %r" % n)

# 3b. 变体：pulseaudio 与 connection refused 顺序颠倒，跨任意内容
n, _ = count([
    "[E] splash:12: network connection refused while opening pulseaudio device",
])
check("顺序颠倒的同款伪命中也不被扣除", n == "1", "实得 %r" % n)

# 4. 真·良性降级仍然要扣除（否则 Linux 上硬指标永远为 1）
n, _ = count(["[E] pulse_audio.rs:740: pa_context_connect failed"])
check("PulseAudio 良性降级被扣除", n == "0", "实得 %r" % n)

n, _ = count(["[E] ALSA fallback to dummy device"])
check("ALSA fallback 被扣除", n == "0", "实得 %r" % n)

# 5. 白名单命中时必须打一行 [W]，否则「0」不可追溯
_, raw = count(["[E] pulse_audio.rs:740: pa_context_connect failed"])
check("白名单命中时打印 [W] 白名单命中", "[W] 白名单命中" in raw,
      "实得 %r" % raw.strip()[:90])

# 6. 没有命中时不打印 [W]
_, raw = count(["[E] splash:1: boom"])
check("无白名单命中时不打印 [W]", "[W] 白名单命中" not in raw)

# 7. run_festival 曾用的宽松口径会误判的两种日志，现在都不算错误
n, _ = count([
    "libEGL warning: DRI3 error: Could not get DRI3 device",
    "[I] Script data fetch request error: reserved request header",
])
check("良性 [I]/warning 行不计入错误数", n == "0", "实得 %r" % n)

print()
if FAILS:
    print("test_host_errors 失败 %d 项：%s" % (len(FAILS), FAILS))
    sys.exit(1)
print("test_host_errors 全部通过")
sys.exit(0)