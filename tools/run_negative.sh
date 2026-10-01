#!/usr/bin/env bash
# OctoSense 端到端实测 · ④ 异常与空状态
#
# 前几条流程跑的都是「顺利路径」，容易给人「只做了 happy path」的印象。
# 初赛材料明确要求「至少一次可核对的操作结果 + 一个失败或空状态」，
# 这里把五类坏输入固定成回归用例：每种都必须给出**明确原因**，
# 而不是静默地什么都不发生。
#
# ★ 2026-10-01 新增第 5 类「不存在的日期」。它是自查时抓到的真 bug：
#   导入侧原来对 DTSTART 只查「非空」，于是 `20260230`（2 月 30 日）会被
#   当成正常事件收下 —— 状态条报「新增 1」，而月历格子永远不会有这一天，
#   事件**导入成功却从不出现在日历上**。同类的还有平年的 2 月 29 日。
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

# 反向断言：某个子串**不该**出现在界面上。
# 「坏输入被明确拒绝」只查报错文案还不够 —— 还要查它**没有偷偷混进去**。
# 这两条必须成对存在，否则「报了个错、同时把事情也做了」会被判为通过。
refuse() {  # $1 = 不应出现的子串, $2 = 用例说明
  local got
  got=$("$PY" tools/e2e.py texts 2>&1)
  if printf '%s' "$got" | grep -qF "$1"; then
    echo "  FAIL $2 —— 界面上不该出现「$1」："
    printf '%s' "$got" | grep -F "$1" | head -3
    FAIL=$((FAIL+1))
  else
    echo "  OK   $2"; PASS=$((PASS+1))
  fi
}

# 读「事件库」指标（= events.len()）。用来证明**只留下了该留的**。
# 取 /snap 里 id 为 metric_events 的 Label 文本；dump 一行形如
#   metric_events [Label] r=[...]  '2'
metric_is() {  # $1 = 期望值, $2 = 用例说明
  local got
  got=$("$PY" tools/e2e.py dump 2>&1 | grep -F "metric_events [Label]" | head -1 \
        | grep -oE "'[^']*'" | tail -1 | tr -d "'")
  if [ "$got" = "$1" ]; then
    echo "  OK   $2"; PASS=$((PASS+1))
  else
    echo "  FAIL $2 —— 事件库 期望 '$1'，实得 '$got'"
    FAIL=$((FAIL+1))
  fi
}

echo "=== [1/7] 启动宿主 ==="
boot_host "$OUT/run-negative.log"
assert_clean
echo "宿主就绪"

echo
echo "=== [2/7] 空输入 ==="
"$PY" tools/e2e.py open >/dev/null 2>&1
"$PY" tools/e2e.py parse >/dev/null 2>&1
expect "输入框是空的" "空输入应被明确拒绝"
shot "01-empty-input.png"

echo
echo "=== [3/7] 非 ICS 文本 ==="
"$PY" tools/e2e.py fill "$FX/not-ics.txt" >/dev/null 2>&1
"$PY" tools/e2e.py parse >/dev/null 2>&1
expect "不是 ICS 文件" "普通文本应被识别为非 ICS，而不是解析出 0 个事件"
shot "02-not-ics.png"

echo
echo "=== [4/7] 只有外壳、没有事件 ==="
"$PY" tools/e2e.py fill "$FX/shell-only.ics" >/dev/null 2>&1
"$PY" tools/e2e.py parse >/dev/null 2>&1
expect "没有解析出任何事件" "空日历应给出空状态提示"
shot "03-shell-only.png"

echo
echo "=== [5/7] 残缺事件（缺 UID / 缺 DTSTART / 未闭合）==="
"$PY" tools/e2e.py fill "$FX/broken-events.ics" >/dev/null 2>&1
"$PY" tools/e2e.py parse >/dev/null 2>&1
# 关键：不能只说「N 条警告」，要指出**哪一行**、缺什么
expect "缺 UID" "应指出第一处问题的具体位置与原因"
shot "04-broken.png"

echo
echo "=== [6/7] 不存在的日期（2 月 30 日 / 平年 2 月 29 日）==="
# fixture 里 4 个事件：前两个日期不存在（2026-02-30、2026-02-29），
# 后两个是真的（2024-02-29 闰日、2026-10-04）。
"$PY" tools/e2e.py fill "$FX/bad-date.ics" >/dev/null 2>&1
"$PY" tools/e2e.py parse >/dev/null 2>&1
expect "不存在，已跳过" "不存在的日期要指出来（行号 + 具体日期），不能默默收下"
expect "等 2 条" "两个不存在的日期都要被拦下（不是只拦第一个）"
shot "05-bad-date.png"
"$PY" tools/e2e.py write >/dev/null 2>&1
metric_is "2" "只留下 2 个真实存在的事件（4 个里恰好剔掉 2 个）"
# ★ 反向断言：坏日期不得偷偷混进事件库。列表里日期渲染成「2 月 30 日」，
#   所以这一条能直接抓住「报错归报错、事件还是写进去了」这种半吊子修法。
refuse "2 月 30 日" "不存在的日期不得出现在事件库里"

echo
echo "=== [7/7] 错误检查 ==="
NERR=$(host_error_count "$OUT/run-negative.log")
echo "编译/运行错误数: $NERR   断言通过 $PASS / 失败 $FAIL"
ls "$EV"

kill_host

if [ "$FAIL" != "0" ] || [ "$NERR" != "0" ]; then
  echo "NEGATIVE FAIL"
  exit 1
fi
echo "NEGATIVE PASS"
exit 0
