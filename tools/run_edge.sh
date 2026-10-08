#!/usr/bin/env bash
# OctoSense 端到端实测 · ③ 字段级往返无损（边界用例）
#
# 为什么单独一条流程：run_e2e.sh / run_conflict.sh 的往返断言只数
# 「新增 / 改期 / 跳过」，靠 UID 匹配 —— **字段级缩水它测不出来**。
# 实测就是这么漏掉了 DESCRIPTION / ORGANIZER / RRULE 三条静默丢失。
# 这里改成直接对导出的 ICS 做子串硬断言。
#
# 用法: bash tools/run_edge.sh
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
EV="$OUT/evidence-edge"
mkdir -p "$EV"
rm -f "$EV"/* 2>/dev/null || true

source tools/_env.sh

static_gate

shot() { $CURL --max-time 20 "http://127.0.0.1:$PORT/g?raw=1&t=$RANDOM" -o "$EV/$1" 2>/dev/null; }
show() { "$PY" tools/e2e.py texts 2>&1 | grep -E "$1"; }
# ★ 2026-10-08（P0-1）：新增。`show` 只是把匹配行打出来，**从不参与判定**——
#   历史上 run_edge.sh 全文没有 exit，于是所有判定都是摆设。现在凡是
#   「本该出现却没出现」的东西都必须走 expect_* 记进 BAD，最后统一 exit 1。
BAD=0
bad() { BAD=$((BAD+1)); }
# 在视口内文本里找子串（用于「重复 / 全天」这类**标签必须可见**的断言）
expect_viewport() {  # $1 = 期望子串, $2 = 说明
  local got
  got=$("$PY" tools/e2e.py texts 2>&1)
  if printf '%s' "$got" | grep -qF "$1"; then
    echo "  OK   $2"
  else
    echo "  FAIL $2 —— 视口内未出现「$1」"
    bad
  fi
}
# 滚回页顶 / 滚到底。⚠️ 列表是 ScrollYView，滚下去之后顶部的
# 「导入」按钮会离开视口、从渲染树里消失，need() 就找不到了。
to_top() { for _ in 1 2 3 4 5 6; do "$PY" tools/e2e.py scroll -400 >/dev/null 2>&1; done; }
to_bottom() { for _ in 1 2 3 4 5 6; do "$PY" tools/e2e.py scroll 400 >/dev/null 2>&1; done; }

echo "=== [1/8] 启动宿主 ==="
boot_host "$OUT/run-edge.log"
assert_clean
echo "宿主就绪  python=$PY  host=$HOST"

echo
echo "=== [2/8] 导入 seed.ics（常规 3 事件）==="
"$PY" tools/e2e.py open  >/dev/null 2>&1
"$PY" tools/e2e.py fill seed.ics >/dev/null 2>&1
"$PY" tools/e2e.py parse >/dev/null 2>&1
"$PY" tools/e2e.py write 2>&1 | grep -E "已写入|FAIL" | head -2

echo
echo "=== [3/8] 导入 edge.ics（RRULE / DESCRIPTION / ORGANIZER / UTC）==="
"$PY" tools/e2e.py open  >/dev/null 2>&1
"$PY" tools/e2e.py fill edge.ics >/dev/null 2>&1
"$PY" tools/e2e.py parse 2>&1 | grep -E "解析|重复日程" | head -3
"$PY" tools/e2e.py write 2>&1 | grep -E "已写入|FAIL" | head -2

echo
echo "=== [4/8] 列表里应出现重复标签（不能静默）==="
shot "01-edge-list.png"
# ⚠️ 必须滚动：列表是 ScrollYView，只有视口内的行才会进渲染树。
#    第一次跑这里没滚，10-06/12-25 的行都还没渲染，被误判成「标签没出来」。
to_bottom
show "重复|全天|VALUE=DATE|月 [0-9]+ 日"
# ★ P0-1：原来只有上面那行 show（纯打印，不判定）。重复日程必须打标签、
#   不能静默合并 —— 这是 edge.ics 存在的唯一理由，所以要真断言。
expect_viewport "重复" "重复日程应打「重复」标签（不能静默合并）"
expect_viewport "全天" "全天事件应打「全天」标签（VALUE=DATE 不参与自动改期）"
shot "02-edge-list-scrolled.png"

echo
echo "=== [5/8] 导出到输入框并落盘 ==="
to_top
# ⚠️ 此时导入面板是「关」的（confirm_import 会收起它），open 一次正好打开。
#    见 [7/8] 的说明。
"$PY" tools/e2e.py open >/dev/null 2>&1
"$PY" tools/e2e.py export >/dev/null 2>&1
"$PY" tools/e2e.py entry "$EV/exported.ics" 2>&1 | tail -12

echo
echo "=== [6/8] 字段级硬断言（往返无损证据）==="
MISS=0
for key in "BEGIN:VCALENDAR" "RRULE:FREQ=WEEKLY;BYDAY=TU;COUNT=8" "RRULE:FREQ=YEARLY" \
           "EXDATE;TZID=Asia/Shanghai:20261020T093000" \
           "RDATE;TZID=Asia/Shanghai:20261022T093000" \
           "DTSTAMP:20260930T120000Z" \
           "DESCRIPTION:" "ORGANIZER:" "TZID=Asia/Shanghai" "VALUE=DATE" \
           "T140000Z" "SEQUENCE:1" "STATUS:CONFIRMED" "UID:edge-recurring@oma"; do
  if grep -qF "$key" "$EV/exported.ics"; then
    printf "  OK    %s\n" "$key"
  else
    printf "  MISS  %s   <-- 数据丢失！\n" "$key"
    MISS=$((MISS+1))
  fi
done
echo "  字段丢失数: $MISS"
# ★ P0-1：字段丢失必须让脚本失败。这 14 条硬断言是本流程存在的唯一理由，
#   历史上只打印不判定 —— 导出真丢字段时全量回归照样全绿。
[ "$MISS" = "0" ] || bad

echo
echo "=== [7/8] 往返：把导出的 ICS 原样再解析一次 ==="
echo "（期望 新增 0 / 改期 0 / 跳过 6）"
# ⚠️ 这里**不能**再 open：toggle_import() 是切换，而且打开时会清空输入框 ——
#    面板此刻已经是开的，再点一次会把面板关掉（「找不到按钮『解析』」），
#    顺便把刚导出的内容也清掉。
"$PY" tools/e2e.py fill "$EV/exported.ics" 2>&1 | tail -1
"$PY" tools/e2e.py parse >/dev/null 2>&1
# ⚠️ 必须 write 一次才能看到往返结论：状态条在导入面板打开时会主动让位隐藏
#    （设计稿要求面板互斥），只有面板收起后的文案才是最终状态。
RT=$("$PY" tools/e2e.py write 2>&1 | grep -oE "新增 [0-9]+ / 改期 [0-9]+ / 跳过 [0-9]+" | head -1)
echo "  往返结果: $RT"
case "$RT" in
  *"新增 0 / 改期 0 / 跳过 6"*) echo "  OK   往返幂等：导出无损、重入不产生副本" ;;
  *) echo "  FAIL 往返不幂等（期望 新增 0 / 改期 0 / 跳过 6）"; bad ;;
esac
shot "03-roundtrip.png"
expect_viewport "已写入" "往返后状态条应确认写入完成"

echo
echo "=== [8/8] 错误检查 ==="
NERR=$(host_error_count "$OUT/run-edge.log")
echo "编译/运行错误数: $NERR"
grep '\[E\]' "$OUT/run-edge.log" 2>/dev/null | head -5 || true
# ★ P0-1：宿主错误数也必须参与判定（与 run_conflict.sh / run_e2e.sh 一致）。
[ "$NERR" = "0" ] || bad
# 资源加载失败硬断言（同 run_conflict.sh）：不要匹配裸 `404`，
# 宿主日志里的 `splash.rs:404:9` 是源码行号，会命中假阳性。
if grep -qiE "load failed|failed to load|failed to fetch|no such file" "$OUT/run-edge.log"; then
  echo "FAIL: 宿主日志里出现资源加载失败："
  grep -inE "load failed|failed to load|failed to fetch|no such file" "$OUT/run-edge.log" | head -5
  bad
fi
echo "证据文件:"; ls "$EV"

echo
echo "=== 断言汇总 ==="
echo "失败项数: $BAD"

kill_host
if [ "$BAD" != "0" ]; then
  echo "EDGE FAIL"
  exit 1
fi
echo "EDGE PASS"
exit 0
