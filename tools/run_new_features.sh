#!/usr/bin/env bash
# OctoSense 端到端实测 · ⑨ v0.5.6 新功能固化（历史回滚 / 取消后自动释放）
#
# 为什么单独立项：v0.5.6 新增的两条功能此前只有手动探针，无 CI 固化 —
#   · T1 版本历史与回滚：改期 → 详情页「历史」→ 一键回滚 → 状态条确认
#   · T2 取消后自动释放：待办排期(auto) → 取消阻塞事件 → auto 事件前移
# Windows / macOS 两份测试报告都指出「需要设计用例 + 调试」，这就是那条用例。
#
# 用法: bash tools/run_new_features.sh
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
EV="${EV:-$OUT/evidence}"
mkdir -p "$EV"

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

static_gate

echo "=== [1/5] 启动宿主（空事件库）==="
boot_host "$OUT/run-newfeat.log"
assert_clean
echo "宿主就绪  存储目录 $APP_DATA"

echo
echo "=== [2/5] T1/T2 合并场景：阻塞 → 排期 → 取消 → 回滚 ==="
"$PY" "$ROOT/tools/newfeatflow.py"
NF=$?
if [ "$NF" != "0" ]; then
  echo "  FAIL newfeatflow.py 退出码 $NF"
else
  echo "  OK   newfeatflow.py 全部通过"
fi

echo
echo "=== [3/5] 本地优先存储：关键旁路文件必须落盘 ==="
APPDIR="$APP_DATA/com.oma.octosense.calendar"
STOREOK=1
for f in event-history.json auto-events.json; do
  if [ -f "$APPDIR/$f" ]; then
    printf "  OK    %-22s %s 字节\n" "$f" "$(wc -c < "$APPDIR/$f" | tr -d ' ')"
  else
    printf "  MISS  %-22s 没落盘！\n" "$f"
    STOREOK=0
  fi
done

echo
echo "=== [4/5] 重启宿主，数据读回一致 ==="
kill_host
boot_host "$OUT/run-newfeat2.log" "$APP_DATA"
# 轮询等应用加载完（splash 首次 eval 要数秒，单次 texts 可能扑空）
LOADED=0
for _ in $(seq 1 15); do
  "$PY" "$ROOT/tools/e2e.py" texts > "$OUT/newfeat-restore.txt" 2>&1
  if grep -q "已加载" "$OUT/newfeat-restore.txt"; then
    LOADED=1
    break
  fi
  sleep 0.7
done
RESTORE_OK=0
if [ "$LOADED" = "1" ]; then
  # 事件数应该还是 2（阻塞已取消但仍在库里 + auto 事件）
  CNT=$("$PY" "$ROOT/tools/e2e.py" dump 2>/dev/null | grep -E "^metric_events " | grep -oE "'[0-9]+'\$" | tr -d "'" | head -1)
  echo "  重启后事件数: ${CNT:-?}"
  if [ "${CNT:-0}" = "2" ]; then
    echo "  OK   重启后数据读回一致"
    RESTORE_OK=1
  else
    echo "  FAIL 重启后事件数不为 2"
  fi
else
  echo "  FAIL 重启后应用未正常加载"
fi

echo
echo "=== [5/5] 错误检查 ==="
NERR=$(host_error_count "$OUT/run-newfeat.log")
NERR2=$(host_error_count "$OUT/run-newfeat2.log")
echo "编译/运行错误数: $((NERR + NERR2))（第一个宿主 ${NERR} + 第二个宿主 ${NERR2}）"
grep '\[E\]' "$OUT/run-newfeat.log" 2>/dev/null | head -5 || true
grep '\[E\]' "$OUT/run-newfeat2.log" 2>/dev/null | head -5 || true

kill_host

if [ "$NF" != "0" ] || [ "$STOREOK" != "1" ] || [ "$RESTORE_OK" != "1" ] \
   || [ "$NERR" != "0" ] || [ "$NERR2" != "0" ]; then
  echo "结论：FAIL"
  exit 1
fi
echo "结论：PASS"
exit 0
