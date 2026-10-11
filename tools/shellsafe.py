#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bash 变量展开的 multibyte 陷阱门禁（2026-10-12 · v0.5.2 W1-1）。

`$VAR` 后面紧跟**非 ASCII 字节**时，bash 解析变量名会把那个多字节序列的
**首字节当成变量名的一部分**。在本项目它已经造成过两次真事故：

  1. `echo "… ${ym}，…"` 省略花括号时 → `ym?: unbound variable`（2026-10-08 记在案）
  2. `echo "编译/运行错误数: $((NERR + NERR2))（第一个宿主 $NERR + 第二个宿主 $NERR2）"`
     → `NERR2?: unbound variable`，run_features 在最后一步崩掉。

**语法检查抓不到**：`bash -n` 认为 `$NERR2` 是完整变量名、全角括号是普通文本；
只有真正执行到那一行才炸。而崩掉的位置常常是**错误检查那一步** ——
正好是本该给出结论的地方，于是整条流程「跑完了但没结论」。

判据：`$名字` 后面紧跟字节 >= 0x80。修法一律写 `${名字}`。
纯 Python、秒级、不起宿主。
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# $VAR 后紧跟非 ASCII 字节。排除 ${...} 形式（那是安全的）。
PAT = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7f]")


def shell_files():
    out = []
    for d in ("tools", "."):
        p = os.path.join(ROOT, d)
        if not os.path.isdir(p):
            continue
        for f in sorted(os.listdir(p)):
            if not f.endswith(".sh"):
                continue
            if f == os.path.basename(__file__):
                continue
            out.append(os.path.join(p, f))
    return out


def main():
    bad = []
    files = shell_files()
    for path in files:
        rel = os.path.relpath(path, ROOT)
        try:
            lines = io.open(path, encoding="utf-8").read().splitlines()
        except (IOError, UnicodeDecodeError):
            continue
        for i, line in enumerate(lines, 1):
            st = line.strip()
            if st.startswith("#"):
                continue
            code = line.split(" #", 1)[0]
            m = PAT.search(code)
            if m:
                bad.append("%s:%d  $变量 紧跟全角/非 ASCII → bash 会吞掉首字节\n%s"
                           % (rel, i, "      " + st[:100]))
    if bad:
        print("shellsafe 未通过 —— 发现 %d 处 bash multibyte 陷阱：" % len(bad))
        for b in bad:
            print("  · %s" % b)
        print("\n  修法：凡 $变量 后面紧跟中文/全角标点，一律写成 ${变量}。")
        return 1
    print("shellsafe: 无 $变量 紧跟非 ASCII 的写法（扫描 %d 个 shell 脚本）" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())