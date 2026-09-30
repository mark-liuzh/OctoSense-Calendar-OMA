#!/usr/bin/env bash
# OctoSense 端到端实测 · ⑥ 逐页布局扫描
# 用法: bash tools/run_layout.sh
#
# 它回答的问题和其他五条流程不一样：
#   另外五条查「功能对不对」（状态文本、像素颜色、往返幂等）；
#   这条查「界面有没有坏掉」—— 把应用走到 12 个界面状态，每步对
#   /snap 快照做一次几何检查（零尺寸 / 负坐标 / 右侧越界）。
#
# 为什么需要它：像素断言只覆盖「特意去取色的那几个点」。一个被压成
# 0 高的 Label、一个跑到窗口右边的按钮，不会让任何一条断言失败，
# 只会让人在某页里觉得「这里怎么怪怪的」。2026-09-30 发现 13 个
# Label 显式写了 height（与「Label 一律不写 height」的铁律相悖）
# 之后，补上这道几何防线。
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
mkdir -p "$OUT"

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

static_gate

echo "=== [1/3] 启动宿主 ==="
echo "python:    $PY"
echo "card-host: $HOST"
boot_host "$OUT/run-layout.log"
assert_clean
echo "宿主就绪"

e2e()  { "$PY" tools/e2e.py "$@" >/dev/null 2>&1; }
scan() { "$PY" tools/layout_scan.py --label "$1" || scan_bad=1; }
scan_bad=0

echo
echo "=== [2/3] 逐页扫描 ==="

scan "① 空状态"

e2e open
scan "② 导入面板"

e2e fill seed.ics
e2e parse
scan "③ 解析预览（seed）"

e2e write
scan "④ 写入 3 事件"

e2e open
e2e fill conflict.ics
e2e parse
e2e write
scan "⑤ 冲突写入"

e2e more
scan "⑥ 冲突详情展开"

e2e advice
scan "⑦ 应用建议后"

e2e open
e2e export
scan "⑧ 导出面板"

e2e cancel
e2e about
scan "⑨ 关于页"

e2e about
e2e cycle
scan "⑩ 节日来源 · 国际"

e2e cycle
scan "⑪ 节日来源 · 全部"

e2e cycle
e2e scroll 420
scan "⑫ 滚到事件列表"

echo
echo "=== [3/3] 错误检查 ==="
echo "编译/运行错误数: $(host_error_count "$OUT/run-layout.log")"
grep '\[E\]' "$OUT/run-layout.log" | head -5 || true

kill_host

if [ "$scan_bad" != "0" ]; then
  echo "LAYOUT FAIL"
  exit 1
fi
echo "LAYOUT PASS"
