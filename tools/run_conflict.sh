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

# ★ 2026-10-02（自承薄弱点 P2e）：冲突流程每步都校验关键文案。
#   关键的硬证据有两处：
#     · [4/9] 冲突详情里「重叠 30 分钟」必须出来 —— 量化重叠时长
#     · [7/9] 往返结果必须等于「新增 0 / 改期 0 / 跳过 4」 —— 导出不丢信息
#   这两条 README 反复强调的硬证据之前只靠肉眼/布局树查，现在写进脚本。
#   期望值同样只取**最少的关键字**，避免实现微调时把测试拖崩。
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
#   metric_events [Label] r=[...]  '4'
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
# 读导出的 entry 框文本（用于 [6/9] / [7/9]）。注意：`e2e.py entry <file>`
# 会把 entry 框内容**写到文件**，并打印 9 个键值的 OK/MISS；不能复用
# 内部辅助 `entry_text()` —— 它不是 CLI 命令。
get_entry() {
  "$PY" tools/e2e.py entry "$1" 2>&1
  cat "$1"
}

echo
echo "=== [2/9] 导入基线 seed.ics（3 个事件，无冲突）==="
"$PY" tools/e2e.py open 2>&1 | tail -2
"$PY" tools/e2e.py fill seed.ics 2>&1 | tail -1
"$PY" tools/e2e.py parse 2>&1 | grep -E "解析|新增|状态" | tail -3
"$PY" tools/e2e.py write 2>&1 | grep -E "已写入|冲突|状态" | tail -3
shot "01-after-seed.png"
expect "已写入 3 个事件" "seed 写入后状态条应报「已写入 3 个事件」（零冲突）"
metric_is "3" "事件库应为 3 个事件"

echo
echo "=== [3/9] 再导入冲突 ICS（10-04 10:30-11:30 撞 10:00-11:00）==="
"$PY" tools/e2e.py open 2>&1 | tail -2
"$PY" tools/e2e.py fill conflict.ics 2>&1 | tail -1
"$PY" tools/e2e.py parse 2>&1 | grep -E "解析|新增" | tail -2
shot "02-conflict-preview.png"
"$PY" tools/e2e.py write 2>&1 | grep -E "已写入|冲突|发现|状态|剩余" | tail -5
sleep 1
shot "03-conflict-detected.png"
# ★ 关键硬证据：写完 4 个事件后**必须**检出 1 处冲突，否则「冲突消解」
#   就只是一句口号。
expect "已写入 4 个事件" "导入 conflict 后事件库应为 4 个"
expect "发现 1 处时间冲突" "状态条应明确报「发现 1 处时间冲突」"
metric_is "4" "事件库应为 4 个事件"

echo
echo "=== [4/9] 展开冲突详情 ==="
"$PY" tools/e2e.py more 2>&1 | grep -E "重叠|可动|建议|发现|保留" | tail -8
shot "04-conflict-detail.png"
# ★ 关键硬证据：冲突必须给出**量化时长**（30 分钟），不是笼统「有冲突」。
expect "重叠 30 分钟" "冲突详情应量化重叠时长"
expect "保留" "冲突详情应指出哪一项保留"

echo
echo "=== [5/9] 应用改期建议 ==="
"$PY" tools/e2e.py advice 2>&1 | grep -E "已应用|剩余|没有待处理" | tail -4
sleep 1
shot "05-after-advice.png"
# ★ 应用建议后**必须**归零，否则「一键消解」只是空话。
expect "剩余 0 处冲突" "应用改期建议后冲突必须归零"
expect "已应用" "状态条应确认「已应用 N 条改期建议」"
metric_is "4" "事件数仍为 4（被挪走的会更新而不是删除）"

echo
echo "=== [6/9] 导出 ICS（写入输入框）==="
"$PY" tools/e2e.py open 2>&1 | tail -1
"$PY" tools/e2e.py export 2>&1 | grep -E "entry 长度|DTSTART|DTEND|BEGIN:VEVENT|SUMMARY" | head -20
shot "06-export.png"
# 把 entry 文本存盘，下面 [7/9] 的「导出不丢信息」硬证据就要在这里取样。
"$PY" tools/e2e.py entry "$EV/exported.ics" >/dev/null
ENTRY=$(cat "$EV/exported.ics")
# 关键：导出文本必须以 BEGIN:VCALENDAR 开头、END:VCALENDAR 收尾。
if printf '%s' "$ENTRY" | head -1 | grep -qF "BEGIN:VCALENDAR"; then
  echo "  OK   导出文本以 BEGIN:VCALENDAR 开头"; PASS=$((PASS+1))
else
  echo "  FAIL 导出文本不是以 BEGIN:VCALENDAR 开头"; FAIL=$((FAIL+1))
fi
if printf '%s' "$ENTRY" | tail -1 | grep -qF "END:VCALENDAR"; then
  echo "  OK   导出文本以 END:VCALENDAR 结尾"; PASS=$((PASS+1))
else
  echo "  FAIL 导出文本不是以 END:VCALENDAR 结尾"; FAIL=$((FAIL+1))
fi
expect "BEGIN:VCALENDAR" "导出文本应能在界面上读到 BEGIN:VCALENDAR"

echo
echo "=== [7/9] 往返幂等：把导出的 ICS 原样再解析一次 ==="
echo "（★ 关键硬证据：新增 0 / 改期 0 / 跳过 4 —— 导出不丢信息）"
"$PY" tools/e2e.py fill "$EV/exported.ics" 2>&1 | tail -1
"$PY" tools/e2e.py parse 2>&1 | grep -E "解析|新增" | tail -2
"$PY" tools/e2e.py write 2>&1 | grep -E "已写入|新增|改期|跳过|冲突" | tail -5
shot "07-roundtrip.png"
# 「导出不丢信息」的判据：往返一次，新事件=0，改期=0，跳过=4。
expect "新增 0" "往返：导出后重新导入应新增 0（丢字段就会失败）"
expect "改期 0" "往返：导出后重新导入应改期 0"
expect "跳过 4" "往返：4 个事件应全部识别为已存在（UID 命中）"
metric_is "4" "往返后事件库仍为 4"

echo
echo "=== [8/9] 回滚上一次导入 ==="
# ★ 回滚前的「取消」会把面板收起来，但回滚是按快照走的；面板收起来
#    后「回滚」按钮仍在 —— 直接 rollback。
"$PY" tools/e2e.py rollback 2>&1 | tail -2
sleep 1
"$PY" tools/e2e.py texts 2>&1 | grep -E "回滚|没有可回滚" | tail -3
shot "08-rollback.png"
expect "已回滚" "回滚后状态条应报「已回滚到 N 个事件」"
metric_is "4" "回滚把状态恢复到导入 conflict 之前（仍是 4 个：seed=3 + conflict=1）"

echo
echo "=== [9/9] 关于页（吉祥物 + CC BY 4.0 署名）==="
"$PY" tools/e2e.py about >/dev/null 2>&1
"$PY" tools/e2e.py texts 2>&1 | grep -E "CC BY|Noto|OctoSense|队伍|Apache|storage|清空事件库|收起" | tail -8
shot "09-about.png"
expect "Apache" "关于页应包含 Apache-2.0 字样"
expect "Noto" "关于页应包含吉祥物 Noto Animated Emoji 字样"

echo
echo "=== 错误检查 ==="
errs=$(host_error_count "$OUT/run-conflict.log")
echo "编译/运行错误数: $errs"
echo "错误行（如有）:"; grep '\[E\]' "$OUT/run-conflict.log" | head -5 || true

# ★ 资源加载失败硬断言（与 run_e2e.sh 同款，2026-10-02 补齐）：
#   ⚠️ 不要匹配裸 `404` —— 宿主日志里的 `splash.rs:404:9` 是**源码行号**，
#      与 HTTP 状态码无关，会命中假阳性。只认明确的加载失败措辞。
asset_bad=0
if grep -qiE "load failed|failed to load|failed to fetch|no such file" "$OUT/run-conflict.log"; then
  echo "FAIL: 宿主日志里出现资源加载失败："
  grep -inE "load failed|failed to load|failed to fetch|no such file" "$OUT/run-conflict.log" | head -5
  asset_bad=1
fi

echo
echo "=== 证据文件 ==="
ls -la "$EV"
echo "=== 断言汇总 ==="
echo "文本断言: PASS=$PASS  FAIL=$FAIL"

kill_host
if [ "$asset_bad" != "0" ]; then
  echo "DONE（带资源加载失败）"
  exit 1
fi
if [ "$FAIL" != "0" ] || [ "$errs" != "0" ]; then
  echo "CONFLICT FAIL"
  exit 1
fi
echo "CONFLICT PASS"
exit 0
