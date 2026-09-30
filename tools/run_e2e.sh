#!/usr/bin/env bash
# OctoSense 端到端实测 · ① 基本流程（空状态 → 导入 → 写入 → 列表）
# 用法: bash tools/run_e2e.sh
# 可选: PY=<python>  OCTO_CARD_HOST=<card-host>  PORT=<端口>
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
mkdir -p "$OUT/evidence"
rm -f "$OUT"/evidence/* 2>/dev/null || true

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

echo "=== [1/7] 启动宿主 ==="
echo "python:    $PY"
echo "card-host: $HOST"
# 每次清空应用私有数据 → 每次都是「干净首次导入」，结果可复现
boot_host "$OUT/run.log"
echo "宿主就绪"

snap()  { $CURL "http://127.0.0.1:$PORT/snap" -o "$OUT/snap.json"; }
tree()  { $CURL "http://127.0.0.1:$PORT/d"    -o "$OUT/tree.txt"; }
shot()  { sleep 0.5; $CURL "http://127.0.0.1:$PORT/g?raw=1&t=$RANDOM$RANDOM" -o "$OUT/evidence/$1" 2>/dev/null; }

echo
echo "=== [2/7] 初始空状态 ==="
snap; tree
"$PY" tools/e2e.py texts 2>&1 | tail -6
echo "-- 空状态树尾 --"; tail -12 "$OUT/tree.txt"
shot "01-empty.png"

echo
echo "=== [3/7] 点「导入」展开面板 ==="
"$PY" tools/e2e.py open 2>&1
snap
"$PY" tools/e2e.py dump 2>&1 | grep -Ei "entry|import_panel" || echo "(未找到 entry/import_panel)"
shot "02-import-open.png"

echo
echo "=== [4/7] 灌入 seed.ics 并解析 ==="
"$PY" tools/e2e.py fill seed.ics 2>&1
"$PY" tools/e2e.py parse 2>&1 | tail -8
shot "03-parsed.png"

echo
echo "=== [5/7] 写入事件库 ==="
"$PY" tools/e2e.py write 2>&1 | tail -8
shot "04-written.png"

echo
echo "=== [6/7] 滚到列表区看事件 ==="
sleep 1
"$PY" tools/e2e.py scroll 420 >/dev/null 2>&1
sleep 1
snap
echo "-- 滚后视口内文本 --"
"$PY" tools/e2e.py texts 2>&1 | tail -22
shot "05-list.png"
echo "-- 再滚深 --"
"$PY" tools/e2e.py scroll 420 >/dev/null 2>&1
sleep 1
snap
"$PY" tools/e2e.py texts 2>&1 | tail -18
shot "06-list2.png"

echo
echo "=== [7/7] 错误检查 ==="
echo "编译/运行错误数: $(grep -c '\[E\]' "$OUT/run.log" 2>/dev/null || echo 0)"
grep -i "load failed\|404" "$OUT/run.log" | head -3 || true
echo "错误行（如有）:"; grep '\[E\]' "$OUT/run.log" | head -5 || true

echo
echo "=== 证据文件 ==="
ls -la "$OUT/evidence/" 2>/dev/null

# 收工
kill_host
echo "DONE"
