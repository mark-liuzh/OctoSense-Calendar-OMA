#!/usr/bin/env bash
# OctoSense 端到端实测 · ⑦ 新建日程 / 点格子 / 重复规则 / ICS 往返
#
# 为什么单独一条流程：前六条流程测的都是「导入 → 冲突 → 往返 → 边界 → 节假日 →
# 布局」，全部以**导入外部 ICS** 为入口。而 2026-09-30 新增的能力是
# 「**不用 ICS，直接在界面上点日期写日程**」—— 它走的是一整条全新的代码路径：
#   点格子(pick_cell) → 新建面板(save_new) → 事件落库 → 画布重绘
# 这条路没有 ICS 解析器兜底，也没有别的流程覆盖，所以必须单独立项。
#
# 断言分三段：
#   A/B/C/D  交互与选中高亮（newflow.py，坐标全部现取）
#   E        每年重复要真展开到明年（像素级事件点）
#   F        手工建的事件也要能无损往返（导出含 RRULE → 重入 0 新增）
#
# 用法: bash tools/run_new.sh
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
EV="$OUT/evidence"
mkdir -p "$EV"

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

static_gate

echo "=== [1/7] 启动宿主（空事件库）==="
boot_host "$OUT/run-new.log"
assert_clean
echo "宿主就绪  存储目录 $APP_DATA"

echo
echo "=== [2/7] 交互与选中高亮（A–E）==="
"$PY" "$ROOT/tools/newflow.py"
NF=$?
if [ "$NF" != "0" ]; then
  echo "  FAIL newflow.py 退出码 $NF"
else
  echo "  OK   newflow.py 全部通过"
fi

echo
echo "=== [3/7] 导出到输入框并落盘（手工建的事件也要能被导出）==="
# ⚠️ 导入面板此刻是关的，open 一次正好打开（toggle_import 是**切换**，
#    已经开着时再点会把它关掉 —— run_edge.sh 里记过这个坑）。
"$PY" tools/e2e.py open >/dev/null 2>&1
"$PY" tools/e2e.py export >/dev/null 2>&1
"$PY" tools/e2e.py entry "$EV/manual.ics" 2>&1 | tail -4

echo
echo "=== [4/7] 字段级断言：手工事件的 RRULE / 全天语义必须写出来 ==="
MISS=0
for key in "BEGIN:VCALENDAR" "SUMMARY:妈妈生日" "RRULE:FREQ=YEARLY" \
           "DTSTART;VALUE=DATE:20260915" "UID:manual-20260915-" "VERSION:2.0"; do
  if grep -qF "$key" "$EV/manual.ics"; then
    printf "  OK    %s\n" "$key"
  else
    printf "  MISS  %s   <-- 数据丢失！\n" "$key"
    MISS=$((MISS+1))
  fi
done
echo "  字段丢失数: $MISS"

echo
echo "=== [5/7] 往返：把导出的 ICS 原样再解析一次 ==="
echo "（期望 新增 0 / 改期 0 / 跳过 1 —— 手工建的事件与导入的事件走同一套合并逻辑）"
"$PY" tools/e2e.py fill "$EV/manual.ics" 2>&1 | tail -1
"$PY" tools/e2e.py parse 2>&1 | tee "$OUT/rt-parse.txt" | tail -4
# ⚠️⚠️ 这三个数是在**点「解析」时**写进状态条的（main.splash 的解析分支：
#    先 `let r = merge_events(...)` 跑一遍预演，再 `set_status("解析 N 个：新增…")`），
#    **不是**点「写入」之后才写。所以去 write 的输出里 grep 永远是空的 ——
#    2026-09-30 就是在这儿误报了两轮 FAIL，白查了半天应用。
#    正确姿势：从 parse 的输出里取（它同样来自 merge_events，与写入结果同源）；
#    write 那一步只用来验「事务真的提交了、事件数没变多」。
RT=$(grep -oE "新增 [0-9]+ / 改期 [0-9]+ / 跳过 [0-9]+" "$OUT/rt-parse.txt" | head -1)
echo "  往返结果: ${RT:-<没抓到>}"
RT_OK=0
case "$RT" in
  "新增 0 / 改期 0 / 跳过 1") echo "  OK   往返幂等"; RT_OK=1 ;;
  *) echo "  FAIL 往返不幂等（期望 新增 0 / 改期 0 / 跳过 1）" ;;
esac
"$PY" tools/e2e.py write 2>&1 | tail -2
# 事件总数必须还是 1（不能因为重入变成 2）。
# ⚠️ 不要用「列表里数文本」来验：列表在 ScrollYView 里，**只有视口内的行才进渲染树**，
#    数出 0 是测量方式的问题，不是应用的问题（第一次就是这么误报的）。
#    改用指标行的「事件」计数 —— 它永远可见，且就是事件库的真实长度。
# ⚠️ dump 的行格式是 `<id> [<ty>] r=[x, y, w, h]  '<text>'`（**两个空格** + repr 引号），
#    不是 `id [..]  'n'` 直接相连；上一版正则写成 `\[[^]]*\]  '[0-9]+'` 少了 [Type]，
#    于是永远抓空 → CNT='?'（2026-09-30 的第二个误报源）。
# ⚠️ metric_events 只在指标行**可见**时才进快照；新建面板开着时 metrics 会被收起。
#    所以 newflow.py 结束时必须不留面板（见它的 D 段），否则这里必然抓空。
sleep 0.5
CNT=$("$PY" tools/e2e.py dump 2>/dev/null | grep -E "^metric_events " | grep -oE "'[0-9]+'\$" | tr -d "'" | head -1)
echo "  指标「事件」= ${CNT:-?}（期望 1，>1 说明重入产生了副本）"
if [ "${CNT:-0}" = "1" ]; then echo "  OK   没有产生副本"; COUNT_OK=1; else echo "  FAIL 事件数不为 1"; COUNT_OK=0; fi

echo
echo "=== [6/7] 带修饰的 RRULE 不得被乱标（负向回归）==="
# 为什么必须单列：repeat_hits 一开始用 `r.split("FREQ=MONTHLY").len() > 1` 判断，
# 它**连修饰一起匹配** —— 导入的 FREQ=WEEKLY;INTERVAL=2 被当成每周标、
# FREQ=YEARLY;UNTIL=… 忽略 UNTIL 继续往后标。注释与 README 都写着「宁可少标不可乱标」，
# 代码却没做到。修法 = rrule_plain() 白名单。这一步就是那条防线的哨兵。
"$PY" "$ROOT/tools/rrule_guard.py"
RG=$?
if [ "$RG" != "0" ]; then
  echo "  FAIL rrule_guard.py 退出码 $RG"
else
  echo "  OK   rrule_guard.py 全部通过"
fi

echo
echo "=== [7/7] 错误检查 ==="
NERR=$(host_error_count "$OUT/run-new.log")
echo "编译/运行错误数: $NERR"
grep '\[E\]' "$OUT/run-new.log" 2>/dev/null | head -5 || true
echo "证据文件:"; ls "$EV"

kill_host

if [ "$NF" != "0" ] || [ "$MISS" != "0" ] || [ "$RT_OK" != "1" ] || [ "${COUNT_OK:-0}" != "1" ] || [ "$RG" != "0" ] || [ "$NERR" != "0" ]; then
  echo "结论：FAIL"
  exit 1
fi
echo "结论：PASS"
exit 0
