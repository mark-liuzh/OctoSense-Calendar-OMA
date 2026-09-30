#!/usr/bin/env bash
# OctoSense 端到端实测 · ② 冲突流程 + 导出 + 往返幂等 + 回滚
# 用法: bash tools/run_conflict.sh
# 可选: PY=<python>  OCTO_CARD_HOST=<card-host>  PORT=<端口>
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
EV="$OUT/evidence-conflict"
mkdir -p "$EV"
rm -f "$EV"/* 2>/dev/null || true

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

static_gate

echo "=== [1/9] 启动宿主 ==="
echo "python:    $PY"
echo "card-host: $HOST"
boot_host "$OUT/run-conflict.log"
assert_clean
echo "宿主就绪"

# 截图：加随机参数破缓存（代理/中间层会缓存同一 URL 的响应 → 拿到陈旧帧）
shot() { sleep 0.5; $CURL "http://127.0.0.1:$PORT/g?raw=1&t=$RANDOM$RANDOM" -o "$EV/$1" 2>/dev/null; }
snapfile() { $CURL "http://127.0.0.1:$PORT/snap" -o "$OUT/snap.json"; }

echo
echo "=== [2/9] 导入基线 seed.ics（3 个事件，无冲突）==="
"$PY" tools/e2e.py open 2>&1 | tail -2
"$PY" tools/e2e.py fill seed.ics 2>&1 | tail -1
"$PY" tools/e2e.py parse 2>&1 | grep -E "解析|新增|状态" | tail -3
"$PY" tools/e2e.py write 2>&1 | grep -E "已写入|冲突|状态" | tail -3
shot "01-after-seed.png"

echo
echo "=== [3/9] 再导入冲突 ICS（10-04 10:30-11:30 撞 10:00-11:00）==="
"$PY" tools/e2e.py open 2>&1 | tail -2
"$PY" tools/e2e.py fill conflict.ics 2>&1 | tail -1
"$PY" tools/e2e.py parse 2>&1 | grep -E "解析|新增" | tail -2
shot "02-conflict-preview.png"
"$PY" tools/e2e.py write 2>&1 | grep -E "已写入|冲突|发现|状态|剩余" | tail -5
sleep 1
shot "03-conflict-detected.png"

echo
echo "=== [4/9] 展开冲突详情 ==="
"$PY" tools/e2e.py more 2>&1 | grep -E "重叠|可动|建议|发现|保留" | tail -8
shot "04-conflict-detail.png"

echo
echo "=== [5/9] 应用改期建议 ==="
"$PY" tools/e2e.py advice 2>&1 | grep -E "已应用|剩余|没有待处理" | tail -4
sleep 1
shot "05-after-advice.png"

echo
echo "=== [6/9] 导出 ICS（写入输入框）==="
"$PY" tools/e2e.py open 2>&1 | tail -1
"$PY" tools/e2e.py export 2>&1 | grep -E "entry 长度|DTSTART|DTEND|BEGIN:VEVENT|SUMMARY" | head -20
shot "06-export.png"

echo
echo "=== [7/9] 往返幂等：把导出的 ICS 原样再解析一次 ==="
echo "（期望：新增 0 / 改期 0 / 跳过 4 —— 这是「导出不丢信息」的硬证据）"
"$PY" tools/e2e.py parse >/dev/null 2>&1
"$PY" tools/e2e.py texts 2>&1 | grep -E "解析|新增" | tail -2
shot "07-roundtrip.png"

echo
echo "=== [8/9] 回滚上一次导入 ==="
"$PY" tools/e2e.py cancel 2>&1 | tail -1
"$PY" tools/e2e.py dump 2>&1 | grep -E "回滚|详情|应用建议|没有时间冲突" | head -4
"$PY" tools/e2e.py rollback >/dev/null 2>&1
"$PY" tools/e2e.py texts 2>&1 | grep -E "回滚|没有可回滚" | tail -2
shot "08-rollback.png"

echo
echo "=== [9/9] 关于页（吉祥物 + CC BY 4.0 署名）==="
"$PY" tools/e2e.py about >/dev/null 2>&1
"$PY" tools/e2e.py texts 2>&1 | grep -E "CC BY|Noto|OctoSense|队伍|Apache|storage|清空事件库|收起" | tail -8
shot "09-about.png"

echo
echo "=== 错误检查 ==="
echo "编译/运行错误数: $(grep -c '\[E\]' "$OUT/run-conflict.log" 2>/dev/null || echo 0)"
grep '\[E\]' "$OUT/run-conflict.log" | head -5 || true
echo "证据文件:"; ls -la "$EV"

kill_host
echo "DONE"
