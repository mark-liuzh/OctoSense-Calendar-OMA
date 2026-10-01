#!/usr/bin/env python3
"""静态门禁：**调用了但从未定义**的函数名（含方法名写错的情况）。

为什么需要它（血泪，2026-10-01）
──────────────────────────────────────────────────────────────────
新功能那一版里，我在逻辑层写了 `cell_bg` 调用 `heat_of(c.d8)`、
`week_sum` 调用 `todo_count(d8)` —— **两个函数从头到尾就没写过**。
- `deps.py` 抓不到：它只查「建树时求值的前向引用」，而这两处都在
  **运行时上下文**（on_render 闭包 / fn 体内），那里前向引用是合法的。
- 静态语法检查也抓不到：`heat_of(...)` 语法完全合法。
- 只有真跑起来才爆，而且爆得很偏：
  `on_render` 里的 `heat_of` 报错 → **整个 canvas 的渲染产出被丢弃**
  → 月历空白 → `load()` 里 `refresh_all()` 被静默中断
  → 状态条没写上「已加载 0 个事件」→ `assert_clean` 判「存储不干净」。
  报错信息（「存储不干净」）离真因（未定义的函数名）隔了整整三层。
所以补这一道门禁：把「调用点」与「定义点」做差集，差集必须为空。

判定范围
──────────────────────────────────────────────────────────────────
· 定义点：`fn NAME(`（含 `.splash` 里所有顶层 fn）+ 宿主内建（见 BUILTINS）
· 调用点：`NAME(`，且 NAME 前面**不是** `.`（排除方法调用）也不是标识符字符
· 关键字（if / for / while / return / fn / let）不算调用

局限（写清楚，免得被当成万能）
──────────────────────────────────────────────────────────────────
· 只查「函数名」，查不出「字段名写错」（如 `c.hlv` 写成 `c.hlvv`）；
  那类要靠 `/snap` 与像素断言。
· 内建名表是**手维护**的：宿主新增内建、且本文件没列，会误报。
  误报时把名字加进 BUILTINS 即可（误报不会漏报，方向是对的）。
"""
import re
import sys

BUILTINS = {
    # 类型转换 / 数值
    "parse_json", "ipart", "min", "max", "abs", "floor", "ceil", "round",
    # 时钟（实测：`time_now()` 拿当前时间，`local_time(t)` 转本地时间）
    "time_now", "local_time",
    # 图形 / 资源 / 主题
    "http_resource", "theme",
    # 定时器 / 生命周期
    "start_timeout", "start_interval",
    # 其他宿主内建（实测出现在本项目的调用点）
    "size_of", "color", "vec2", "vec3", "vec4", "mat4", "ok", "err",
    "json", "fn", "regex", "html", "shader",
}

KEYWORDS = {"if", "for", "while", "return", "fn", "let", "else", "match", "in"}

STR_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
FN_DEF_RE = re.compile(r'\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(')
CALL_RE = re.compile(r'(?<![.\w])([a-z_][A-Za-z0-9_]*)\s*\(')


def strip_strings_and_comments(src):
    """把字符串字面量与行注释换掉，避免在注释/字符串里匹配到假调用点。

    ⚠️ 必须逐行处理并保留换行：行号要跟原文对上，报错才有用。
    """
    out = []
    for line in src.split("\n"):
        # 先处理字符串：把 "..." 整体替换成同长度的占位，保证列号不漂
        def _blank(m):
            return '"' + " " * (len(m.group(0)) - 2) + '"'
        line = STR_RE.sub(_blank, line)
        # 再去行注释（此时字符串已中性化，不会误伤 "//" 出现在字符串里的情况）
        i = line.find("//")
        if i >= 0:
            line = line[:i]
        out.append(line)
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        print("用法: python tools/fncalls.py bundle/main.splash")
        return 2
    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    code = strip_strings_and_comments(src)

    defined = set(FN_DEF_RE.findall(code))

    unknown = {}
    for lineno, line in enumerate(code.split("\n"), start=1):
        for m in CALL_RE.finditer(line):
            name = m.group(1)
            if name in KEYWORDS or name in BUILTINS or name in defined:
                continue
            unknown.setdefault(name, []).append(lineno)

    if not unknown:
        print("fncalls: 所有调用点都有定义（%d 个自定义 fn + %d 个内建）"
              % (len(defined), len(BUILTINS)))
        return 0

    print("FATAL: 以下名字被调用但既不是自定义 fn 也不在内建表里：")
    for name in sorted(unknown):
        lines = unknown[name]
        shown = ", ".join(str(x) for x in lines[:6])
        more = "" if len(lines) <= 6 else " …(+%d)" % (len(lines) - 6)
        print("  %-24s %d 处：%s%s" % (name, len(lines), shown, more))
    print()
    print("若确认它是宿主内建（不是笔误），把名字加进 tools/fncalls.py 的 BUILTINS。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
