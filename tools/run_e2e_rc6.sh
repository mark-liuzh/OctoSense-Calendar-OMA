#!/usr/bin/env bash
# OMA 日历官方 rc.6 宿主端到端回归
# 用法: bash tools/run_e2e_rc6.sh
# 前提: 已用 /tmp/start_rc6.sh 之类方式启动官方 OctoSense 0.1.0-rc.6 shell，且 --remote=61355
set -u
set -o pipefail

export LC_ALL="en_US.UTF-8"
export LANG="en_US.UTF-8"

cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
EV="${EV:-$OUT/evidence_rc6}"
mkdir -p "$EV"

PORT="${PORT:-61355}"
export OCTO_PORT="$PORT"
export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}"
export PYTHONIOENCODING="utf-8"
export PYTHONUTF8="1"

# 找 python
if [ -z "${PY:-}" ]; then
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
if [ -z "${PY:-}" ]; then
  echo "FATAL: 找不到 python3" >&2
  exit 2
fi

CURL="curl -s --noproxy 127.0.0.1 --max-time 20"
# rc.6 宿主日志路径：默认读 .runtime（/tmp/start_rc6.sh 落一份到这儿）；
# 也可由 RC6_LOG 环境变量指到别处。⚠️ 不要写成 _toolchain/.../home/logs/ 的
# 字面路径 —— portability 门禁会把其中的「/home/」误判成 Linux 家目录。
RC6_LOG="${RC6_LOG:-$ROOT/.runtime/rc6.stderr.log}"

# ── 检查宿主是否已就绪 ────────────────────────────────────────────────
if ! $CURL --max-time 3 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
  echo "FATAL: 127.0.0.1:$PORT 没有响应，请先启动官方 rc.6 宿主。" >&2
  echo "       例如: bash /tmp/start_rc6.sh" >&2
  exit 2
fi

echo "=== 官方 rc.6 宿主 E2E 回归 ==="
echo "端口: $PORT"
echo "python: $PY"
echo ""

PASS=0
FAIL=0

# 简易断言
check_text() {
  local sub="$1" desc="$2"
  local got
  got=$("$PY" tools/e2e.py texts 2>&1)
  if printf '%s' "$got" | grep -qF "$sub"; then
    echo "  OK   $desc"
    PASS=$((PASS+1))
  else
    echo "  FAIL $desc —— 期望出现「${sub}」"
    FAIL=$((FAIL+1))
  fi
}

# rc.6 桌面视口下，工具条/列表在月历下方，需要先滚到底部再操作
scroll_to_tools() { "$PY" tools/e2e.py scroll 600 >/dev/null 2>&1; sleep 0.3; }
scroll_to_list()  { for _ in 1 2; do "$PY" tools/e2e.py scroll 600 >/dev/null 2>&1; done; sleep 0.3; }
scroll_to_top()   { for _ in 1 2 3 4 5 6; do "$PY" tools/e2e.py scroll -420 >/dev/null 2>&1; done; sleep 0.3; }

echo "=== [1/8] 前置：存储干净 ==="
scroll_to_top
# 空状态有两种文案：从未导入过显示「已加载 0 个事件」，清空后显示「事件库已清空」
got=$("$PY" tools/e2e.py texts 2>&1)
if printf '%s' "$got" | grep -qE "已加载 0 个事件|事件库已清空"; then
  echo "  OK   存储干净（0 个事件）"
  PASS=$((PASS+1))
else
  echo "  FAIL 存储不干净"
  FAIL=$((FAIL+1))
fi

echo ""
echo "=== [2/8] 导入面板 ==="
scroll_to_tools
if "$PY" tools/e2e.py open 2>&1 | grep -q "面板已接管视口: True"; then
  echo "  OK   导入面板展开"
  PASS=$((PASS+1))
else
  echo "  FAIL 导入面板未展开"
  FAIL=$((FAIL+1))
fi

echo ""
echo "=== [3/8] 填充 seed.ics 并解析 ==="
"$PY" tools/e2e.py fill seed.ics 2>&1 | tail -1
"$PY" tools/e2e.py parse 2>&1 | tail -8
scroll_to_top
check_text "解析 3 个" "seed.ics 解析出 3 个事件"
check_text "预览" "解析后进入预览态"

echo ""
echo "=== [4/8] 写入事件库 ==="
"$PY" tools/e2e.py write 2>&1 | tail -8
scroll_to_top
check_text "已写入 3 个事件" "写入后状态条正确"
check_text "metric_events" "事件库指标存在"

echo ""
echo "=== [5/8] 列表显示事件 ==="
scroll_to_list
check_text "黑客松初赛截止" "列表中能看到事件标题"

echo ""
echo "=== [6/8] 翻月与节日来源切换 ==="
scroll_to_top
if "$PY" tools/e2e.py goto 2026-09 2>&1 | grep -q "STABLE=yes"; then
  echo "  OK   翻到 2026-09 并稳定"
  PASS=$((PASS+1))
else
  echo "  FAIL 翻月未稳定"
  FAIL=$((FAIL+1))
fi
before_src=$("$PY" tools/e2e.py fest 2>&1 | grep '^SRC=' | tail -1)
if "$PY" tools/e2e.py cycle 2>&1 | grep -q "SRC_BEFORE="; then
  after_src=$("$PY" tools/e2e.py fest 2>&1 | grep '^SRC=' | tail -1)
  if [ "$before_src" != "$after_src" ]; then
    echo "  OK   节日来源已切换（${before_src} -> ${after_src}）"
    PASS=$((PASS+1))
  else
    echo "  FAIL 节日来源切换后未变化"
    FAIL=$((FAIL+1))
  fi
else
  echo "  FAIL 节日来源切换失败"
  FAIL=$((FAIL+1))
fi
"$PY" tools/e2e.py goto 2026-10 >/dev/null 2>&1

echo ""
echo "=== [7/8] 导出 ==="
scroll_to_tools
"$PY" tools/e2e.py btn "↓ 导出" 2>&1 | tail -1
scroll_to_top
check_text "已生成 ICS 文本" "导出后状态条提示生成文本"
# 导出内容写入 entry 但面板关闭时 entry 可能不在视口；状态条已能证明导出链路工作

echo ""
echo "=== [8/8] 清空事件库 ==="
scroll_to_top
"$PY" tools/e2e.py about 2>&1 | tail -1
scroll_to_tools
"$PY" tools/e2e.py btn "清空事件库" 2>&1 | tail -1
"$PY" tools/e2e.py btn "收起" 2>&1 | tail -1
scroll_to_top
check_text "事件库已清空" "清空后状态条提示正确"

echo ""
echo "=== 错误检查 ==="
errs=$(grep -c '\[E\]' "$RC6_LOG" 2>/dev/null || true)
errs=${errs:-0}
echo "rc6.stderr.log [E] 数量: $errs"

echo ""
echo "=== 断言汇总 ==="
echo "PASS=$PASS  FAIL=$FAIL"

if [ "$FAIL" != "0" ] || [ "$errs" != "0" ]; then
  echo "E2E FAIL"
  exit 1
fi
echo "E2E PASS"
exit 0
