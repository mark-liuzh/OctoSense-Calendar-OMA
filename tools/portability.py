#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可移植性门禁：脚本里不许出现开发者本机路径（2026-10-12 · v0.5.2 W1-1）。

为什么必须静态拦：v0.5.1 的 `newflow.py` / `rrule_guard.py` / `featflow.py`
各自写死了一行 `OCTO = os.environ.get("OCTO", "D:/Projects/OctoScript-App-Design-Flow/tools/octo")`。
后果在干净克隆上极其误导：shot() 把 stderr 丢掉、不检查退出码，**照样返回一个路径**，
后面取像素时才抛FileNotFoundError —— 一条根因放大成 8~10 条假 FAIL，
报告读起来像应用像素渲染坏了。Linux / Windows 两份测试报告都栽在这。

同一类还包括本机 `_toolchain/` 绝对路径、`/Users/<某人>/…` 这类。
它们在别人机器上必然不存在，且失败方式几乎都是静默的。

本门禁只看 tools/ 与仓库根的脚本，不看 bundle/（bundle 不含工具代码）。
纯 Python、秒级、不起宿主。
"""
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TOOLS = os.path.join(ROOT, "tools")

# (正则, 为什么它是问题)
PATTERNS = [
    (r"['\"]D:/Projects/", "开发者本机 Windows 绝对路径（v0.5.1 的 OCTO 默认值）"),
    (r"['\"]D:\\\\", "开发者本机 Windows 盘符路径"),
    (r"['\"]C:/Users/", "开发者本机 Windows 用户目录"),
    (r"/Users/[a-z][a-z0-9_.-]*/", "macOS 某人的家目录路径（换机器即失效）"),
    (r"/home/[a-z][a-z0-9_.-]*/", "Linux 某人的家目录路径"),
    (r"_toolchain/OctoSense-App-Hub/target", "本机工具链构建路径（应由 OCTO_CARD_HOST 提供）"),
]

# 这几行是**说明性记录**（写在注释里是为了讲清「被删掉的旧写法是什么」），
# 刻意保留旧路径字面量，不该被自己抓到。
ALLOW_SUBSTR = ("已移除", "原来", "写死", "曾", "v0.5.1", "作废", "各写了一遍")


def docstring_lines(path):
    """→ 该 Python 文件里属于字符串/文档字符串的行号集合。

    ⚠️ 必须真解析而不是靠 `#` 判断：`octo_shot.py` 的模块 docstring 里**要**
    引用旧写法 `D:/Projects/...` 来解释「为什么抽这个模块」。靠去注释看不到这一点，
    只会把它当违规 —— 而把说明文字删掉才是不对的。
    """
    try:
        import ast
        tree = ast.parse(io.open(path, encoding="utf-8").read())
    except (SyntaxError, IOError, UnicodeDecodeError):
        return set()
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            d = body[0]
            if isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant) \
               and isinstance(d.value.value, str):
                for ln in range(d.lineno, (d.end_lineno or d.lineno) + 1):
                    lines.add(ln)
    return lines


def strip_comment(line):
    """粗略去注释：# 之后、且不在引号里的部分。够用即可，不追求完备。"""
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
            out.append(ch)
            continue
        if ch == "#":
            break
        out.append(ch)
    return "".join(out)


def main():
    files = []
    for d in (TOOLS, ROOT):
        if d == TOOLS:
            files += [os.path.join(d, f) for f in sorted(os.listdir(d))
                      if f.endswith((".py", ".sh")) and f != os.path.basename(__file__)]
        else:
            files += [os.path.join(d, f) for f in sorted(os.listdir(d))
                      if f.endswith(".sh")]

    bad = []
    for path in files:
        rel = os.path.relpath(path, ROOT)
        try:
            lines = io.open(path, encoding="utf-8").read().splitlines()
        except (IOError, UnicodeDecodeError):
            continue
        doc = docstring_lines(path) if path.endswith(".py") else set()
        for i, raw in enumerate(lines, 1):
            if i in doc or any(k in raw for k in ALLOW_SUBSTR):
                continue
            code = strip_comment(raw)
            if not code.strip():
                continue
            for pat, why in PATTERNS:
                if re.search(pat, code, re.I):
                    bad.append("%s:%d  %s\n      %s" % (rel, i, why, raw.strip()[:100]))

    if bad:
        print("portability 未通过 —— 发现 %d 处写死的本机路径：" % len(bad))
        for b in bad:
            print("  · %s" % b)
        print("\n  修法：路径一律走环境变量或仓库内相对路径；")
        print("        抓帧通道用 tools/octo_shot.resolve_octo()（找不到就走直连 /g?raw=1）。")
        return 1
    print("portability: 无写死的本机路径（扫描 %d 个脚本）" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())