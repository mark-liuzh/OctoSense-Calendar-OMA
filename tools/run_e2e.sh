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

static_gate

echo "=== [1/7] 启动宿主 ==="
echo "python:    $PY"
echo "card-host: $HOST"
# 每次清空应用私有数据 → 每次都是「干净首次导入」，结果可复现
boot_host "$OUT/run.log"
assert_clean
echo "宿主就绪"

snap()  { $CURL "http://127.0.0.1:$PORT/snap" -o "$OUT/snap.json"; }
tree()  { $CURL "http://127.0.0.1:$PORT/d"    -o "$OUT/tree.txt"; }
shot()  { sleep 0.5; $CURL "http://127.0.0.1:$PORT/g?raw=1&t=$RANDOM$RANDOM" -o "$OUT/evidence/$1" 2>/dev/null; }

# ★ 2026-10-02（自承薄弱点 P2e）：给基本流程加正向文本断言。
#   之前「通过」只意味着「跑完了、宿主日志里 0 个 [E]」；现在每步都校验
#   关键文案，让「导入后看不到东西」「写入其实没生效」这类问题在脚本里
#   就被卡掉，不必等评委看截图才发现。
#   期望值故意只取**最少的关键字**（不写完整事件标题、不写整段状态文案），
#   避免「跟着实现写测试」导致实现微调就误判失败。
PASS=0; FAIL=0
expect() {  # $1 = 期望子串, $2 = 用例说明
  local got
  got=$("$PY" tools/e2e.py texts 2>&1)
  if printf '%s' "$got" | grep -qF "$1"; then
    echo "  OK   $2"; PASS=$((PASS+1))
  else
    echo "  FAIL $2 —— 期望出现「$1」"
    FAIL=$((FAIL+1))
  fi
}
# 读「事件库」指标（= events.len()）。dump 一行形如
#   metric_events [Label] r=[...]  '3'
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

echo
echo "=== [2/7] 初始空状态 ==="
snap; tree
"$PY" tools/e2e.py texts 2>&1 | tail -6
echo "-- 空状态树尾 --"; tail -12 "$OUT/tree.txt"
shot "01-empty.png"
expect "已加载 0 个事件" "空状态：状态条应报「已加载 0 个事件」"
metric_is "0" "事件库起始为 0"

echo
echo "=== [3/7] 点「导入」展开面板 ==="
"$PY" tools/e2e.py open 2>&1
snap
"$PY" tools/e2e.py dump 2>&1 | grep -Ei "entry|import_panel" || echo "(未找到 entry/import_panel)"
shot "02-import-open.png"
expect "解析" "点导入后面板应展开，能找到「解析」按钮"
expect "导入" "点导入后面板标题应是「导入」"

echo
echo "=== [4/7] 灌入 seed.ics 并解析 ==="
"$PY" tools/e2e.py fill seed.ics 2>&1
"$PY" tools/e2e.py parse 2>&1 | tail -8
shot "03-parsed.png"
# parse 完成后状态条会写「解析 3 个：新增 3 · 改期 0 · 跳过 0」
expect "解析 3 个" "seed.ics 含 3 个事件，解析后状态条应报「解析 3 个」"
expect "预览" "解析完成应进入「预览」态"

echo
echo "=== [5/7] 写入事件库 ==="
"$PY" tools/e2e.py write 2>&1 | tail -8
shot "04-written.png"
# seed.ics 全部日期都是未来，零冲突，所以走「已写入」分支
expect "已写入 3 个事件" "写入后状态条应报「已写入 3 个事件」"
metric_is "3" "事件库应恰好 3 个事件"

echo
echo "=== [6/7] 滚到列表区看事件 ==="
sleep 1
"$PY" tools/e2e.py scroll 420 >/dev/null 2>&1
sleep 1
snap
echo "-- 滚后视口内文本 --"
"$PY" tools/e2e.py texts 2>&1 | tail -22
shot "05-list.png"
# 列表是 ScrollYView，要滚到底才有所有 3 个日期分组。
# 这里故意只断言「至少有一个事件标题出现」—— 不写完整 3 个事件标题，
# 避免实现微调（合并行、截断等）时把测试拖崩。
echo "-- 再滚深 --"
"$PY" tools/e2e.py scroll 420 >/dev/null 2>&1
sleep 1
snap
"$PY" tools/e2e.py texts 2>&1 | tail -18
shot "06-list2.png"
# seed.ics 里有「黑客松初赛截止」—— 用它做探针：只要事件真的渲染进列表，这串字就会出现。
expect "黑客松初赛截止" "列表里应至少能看到一个事件标题"
metric_is "3" "列表翻完后事件库仍为 3"

echo
echo "=== [7/7] 错误检查 ==="
# ⚠️ 取错误数必须走 host_error_count —— 直接写 `$(grep -c ... || echo 0)`
#    会得到两行 "0\n0"，下面的 `= "0"` 比较就会假失败（见 _env.sh 的说明）。
errs=$(host_error_count "$OUT/run.log")
echo "编译/运行错误数: $errs"
echo "错误行（如有）:"; grep '\[E\]' "$OUT/run.log" | head -5 || true

# 资源加载失败：硬断言（原先是「只打印、不失败」）。
#   ⚠️ 不要匹配裸 `404` —— 宿主日志里的 `splash.rs:404:9` 是**源码行号**，
#      与 HTTP 状态码无关，实测会命中假阳性（2026-09-30）。
#      只认明确的加载失败措辞。
asset_bad=0
if grep -qiE "load failed|failed to load|failed to fetch|no such file" "$OUT/run.log"; then
  echo "FAIL: 宿主日志里出现资源加载失败："
  grep -inE "load failed|failed to load|failed to fetch|no such file" "$OUT/run.log" | head -5
  asset_bad=1
fi
if [ "$errs" != "0" ]; then
  echo "FAIL: 编译/运行错误数不为 0"
  exit 1
fi

echo
echo "=== 证据文件 ==="
ls -la "$OUT/evidence/" 2>/dev/null

echo
echo "=== 断言汇总 ==="
echo "文本断言: PASS=$PASS  FAIL=$FAIL"

# 收工
kill_host
if [ "$asset_bad" != "0" ]; then
  echo "DONE（带资源加载失败）"
  exit 1
fi
if [ "$FAIL" != "0" ] || [ "$errs" != "0" ]; then
  echo "E2E FAIL"
  exit 1
fi
echo "E2E PASS"
exit 0
