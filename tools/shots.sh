#!/usr/bin/env bash
# OctoSense 商店截图生成（写入 bundle/screenshots/）
#
# 为什么单独一个脚本：listing.json 里引用的 7 张截图必须是**实机截取**，
# 界面一改就得重出，所以把「怎么摆出这 7 个状态」固化下来，而不是靠手工点。
#
# 用法: bash tools/shots.sh
# 可选: PY=<python>  OCTO_CARD_HOST=<card-host>  PORT=<端口>
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
DST="$ROOT/bundle/screenshots"
mkdir -p "$DST"

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

static_gate

echo "=== 启动宿主 ==="
boot_host "$OUT/run-shots.log"
assert_clean
echo "宿主就绪"

e2e() { "$PY" tools/e2e.py "$@" >/dev/null 2>&1; }
# 截图：加随机参数破缓存（代理/中间层会缓存同一 URL 的响应 → 拿到陈旧帧）
shot() { sleep 0.6; $CURL "http://127.0.0.1:$PORT/g?raw=1&t=$RANDOM$RANDOM" -o "$DST/$1" 2>/dev/null; }

echo "=== 灌入 seed.ics ==="
e2e open; e2e fill seed.ics; e2e parse; e2e write

echo "=== 01 主界面（月历 + 事件列表）==="
# 往下滚一点，让月历和列表同框
e2e scroll 260
shot "01-list.png"

echo "=== 02 导入面板 ==="
e2e scroll -400
e2e open
shot "02-import.png"

echo "=== 03 冲突检出 ==="
e2e fill conflict.ics
e2e parse
e2e write
shot "03-conflict.png"

echo "=== 04 冲突详情 ==="
e2e more
shot "04-conflict-detail.png"

echo "=== 05 应用建议后 ==="
e2e advice
shot "05-after-advice.png"

echo "=== 06 导出 ICS ==="
e2e open
e2e export
shot "06-export.png"

echo "=== 07 关于页 ==="
e2e cancel
e2e about
shot "07-about.png"

echo
echo "编译/运行错误数: $(grep -c '\[E\]' "$OUT/run-shots.log" 2>/dev/null || echo 0)"
ls -l "$DST"
kill_host
echo "DONE"
