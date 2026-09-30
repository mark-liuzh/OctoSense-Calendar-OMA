#!/usr/bin/env bash
# OctoSense 端到端实测 · ④ 异常与空状态
#
# 前三条流程跑的都是「顺利路径」，容易给人「只做了 happy path」的印象。
# 初赛材料明确要求「至少一次可核对的操作结果 + 一个失败或空状态」，
# 这里把四类坏输入固定成回归用例：每种都必须给出**明确原因**，
# 而不是静默地什么都不发生。
#
# 用法: bash tools/run_negative.sh
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
EV="$OUT/evidence-negative"
FX="$ROOT/tools/fixtures"
mkdir -p "$EV"
rm -f "$EV"/* 2>/dev/null || true

source tools/_env.sh

static_gate

shot() { $CURL --max-time 20 "http://127.0.0.1:$PORT/g?raw=1&t=$RANDOM" -o "$EV/$1" 2>/dev/null; }

PASS=0; FAIL=0
expect() {  # $1 = 期望状态条里出现的子串, $2 = 用例说明
  local got
  got=$("$PY" tools/e2e.py texts 2>&1)
  if printf '%s' "$got" | grep -qF "$1"; then
    echo "  OK   $2"; PASS=$((PASS+1))
  else
    echo "  FAIL $2 —— 期望出现「$1」，实际状态条："
    printf '%s' "$got" | grep -E "已加载|解析|空的|不是 ICS|没有解析" | head -3
    FAIL=$((FAIL+1))
  fi
}

echo "=== [1/6] 启动宿主 ==="
boot_host "$OUT/run-negative.log"
assert_clean
echo "宿主就绪"

echo
echo "=== [2/6] 空输入 ==="
"$PY" tools/e2e.py open >/dev/null 2>&1
"$PY" tools/e2e.py parse >/dev/null 2>&1
expect "输入框是空的" "空输入应被明确拒绝"
shot "01-empty-input.png"

echo
echo "=== [3/6] 非 ICS 文本 ==="
"$PY" tools/e2e.py fill "$FX/not-ics.txt" >/dev/null 2>&1
"$PY" tools/e2e.py parse >/dev/null 2>&1
expect "不是 ICS 文件" "普通文本应被识别为非 ICS，而不是解析出 0 个事件"
shot "02-not-ics.png"

echo
echo "=== [4/6] 只有外壳、没有事件 ==="
"$PY" tools/e2e.py fill "$FX/shell-only.ics" >/dev/null 2>&1
"$PY" tools/e2e.py parse >/dev/null 2>&1
expect "没有解析出任何事件" "空日历应给出空状态提示"
shot "03-shell-only.png"

echo
echo "=== [5/6] 残缺事件（缺 UID / 缺 DTSTART / 未闭合）==="
"$PY" tools/e2e.py fill "$FX/broken-events.ics" >/dev/null 2>&1
"$PY" tools/e2e.py parse >/dev/null 2>&1
# 关键：不能只说「N 条警告」，要指出**哪一行**、缺什么
expect "缺 UID" "应指出第一处问题的具体位置与原因"
shot "04-broken.png"

echo
echo "=== [6/6] 错误检查 ==="
NERR=$(grep -c '\[E\]' "$OUT/run-negative.log" 2>/dev/null); NERR=${NERR:-0}
echo "编译/运行错误数: $NERR   断言通过 $PASS / 失败 $FAIL"
ls "$EV"

kill_host
echo "DONE"
