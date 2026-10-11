#!/usr/bin/env bash
# W3-1 定点验收：未知属性（VALARM / CATEGORIES / ATTENDEE …）是否**原样往返**。
#
# 为什么必须单独立项：UID 匹配的往返断言（新增 0 / 改期 0 / 跳过 N）
# 对「字段级缩水」是**无感的** —— 它只看 UID 有没有命中，不看字段还在不在。
# v0.5.1 把 VALARM / CATEGORIES / ATTENDEE 全部静默丢弃，往返测试照样全绿。
# 只有把导入 → 导出的文本**逐字段比对**才抓得到。
#
# 用法: bash tools/verify_extra.sh
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
EV="$OUT/evidence-extra"
mkdir -p "$EV"

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

# ⚠️ to_top / to_bottom 不在 _env.sh 里（run_conflict.sh / run_edge.sh 各自定义了一份），
#    这里自己补上：`/snap` **只返回视口内控件**，滚下去之后页头就出视口了。
to_top() { for _ in 1 2 3 4 5 6; do "$PY" tools/e2e.py scroll -400 >/dev/null 2>&1; done; }

static_gate

echo "=== [1/5] 启动宿主 ==="
boot_host "$OUT/run-extra.log"
assert_clean
echo "宿主就绪"

echo
echo "=== [2/5] 灌入带未知属性的 ICS 并写入 ==="
must_drive "打开导入面板" "$PY" tools/e2e.py open
must_drive "灌入 unknown-props.ics" "$PY" tools/e2e.py fill tools/fixtures/unknown-props.ics
"$PY" tools/e2e.py parse 2>&1 | grep -E "解析|预览" | tail -2
"$PY" tools/e2e.py write 2>&1 | grep -E "已写入|未识别|保留|FAIL" | head -2

echo
echo "=== [3/5] 提示文案必须如实说明「已原样保留」 ==="
# ⚠️ 状态条是单行，extra_note 只报类数；完整类名在导入面板那一行。
"$PY" tools/e2e.py texts 2>&1 | grep -oE "本次有 [0-9]+ 类属性未识别（[^）]*）" | head -1 || true
to_top
"$PY" tools/e2e.py open >/dev/null 2>&1
sleep 0.8
HINT=$("$PY" tools/e2e.py dump 2>/dev/null | grep -F "import_hint " | head -1)
echo "$HINT"
# ⚠️⚠️ 宽度硬断言（2026-10-11）：这一行是 width: Fill 的 Label，
#   **溢出不会换行、只会裁掉尾巴**。实测踩过一次：写「…（CATEGORIES、CLASS、
#   TRANSP 等），已原样保留」时 r 的宽是 389px，而面板可用宽 = 412-20*2 = 372px
#   ⇒ 被裁掉的恰恰是「已原样保留」这句最该让用户看到的话。
#   所以宽度必须**每次实测**，不能靠「看起来不长」。
# ⚠️ 余量留多少（2026-10-11 实测定档）：一行 Label 在 font_regular 11px 下
#   一个汉字 ≈ 11px、ASCII 字符 ≈ 6px。实测本提示行 360px（混排）——
#   也就是说「再加 1 个汉字」就会顶到 372。所以安全线定 364（≈ +1 汉字的余量）：
#   它能挡住「文案被加了整整一句话」这类真回归，又不会因为差 8px 就报红。
#   ⚠️ 别把安全线定成 372-20=352 —— 那会让本行**常态性失败**，
#   而一个长期红的断言等于没有断言（跑久就被无视了）。
PANEL_INNER=372
SAFE_MAX=364
HINT_W=$(printf '%s' "$HINT" | grep -oE 'r=\[[0-9]+, [0-9]+, [0-9]+,' | grep -oE '[0-9]+,?$' | tr -d ',')
if [ -n "${HINT_W:-}" ]; then
  echo "  提示行宽 ${HINT_W}px / 可用 ${PANEL_INNER}px（安全线 ${SAFE_MAX}px）"
  if [ "$HINT_W" -gt "$SAFE_MAX" ]; then
    echo "  FAIL 提示行超安全线，尾巴会被裁掉（超 $((HINT_W - PANEL_INNER))px / 余量不足）"
    WIDE=1
  else
    echo "  OK   提示行在安全线内（余量 $((PANEL_INNER - HINT_W))px）"
  fi
else
  echo "  WARN 没能读到 import_hint 的宽度（跳过该断言）"
fi

echo
echo "=== [4/5] 导出并逐字段比对（关键） ==="
"$PY" tools/e2e.py export >/dev/null 2>&1
"$PY" tools/e2e.py entry "$EV/exported.ics" >/dev/null 2>&1
echo "导出字节数: $(wc -c < "$EV/exported.ics" | tr -d ' ')"

MISS=0
need() {  # $1 = 必须原样出现的行
  if grep -qF "$1" "$EV/exported.ics"; then
    printf "  OK    %s\n" "$1"
  else
    printf "  MISS  %s\n" "$1"
    MISS=$((MISS + 1))
  fi
}
echo "-- 简单未知属性 --"
need "CATEGORIES:工作,重要"
need "CLASS:PRIVATE"
need "TRANSP:OPAQUE"
need "PRIORITY:2"
need "GEO:22.5431;114.0579"
need "CREATED:20260901T080000Z"
need "LAST-MODIFIED:20260920T090000Z"
need "X-APPLE-TRAVEL-DURATION:PT1H"
need "X-CUSTOM-FLAG:1"
echo "-- 带参数的未知属性（拆错位就会变形） --"
need "ATTENDEE;CN=Alice;ROLE=REQ-PARTICIPANT:mailto:alice@example.com"
echo "-- ★ 容器属性：VALARM 必须**连 BEGIN/END 一起**回来 --"
need "BEGIN:VALARM"
need "TRIGGER:-PT15M"
need "ACTION:DISPLAY"
need "DESCRIPTION:15分钟前提醒"
need "END:VALARM"
echo "-- 已知字段仍然无损（不能因为加了 extra 就挤掉别的） --"
need "SUMMARY:带提醒与分类的会议"
need "SUMMARY:只有单个未知属性的全天事件"
need "ORGANIZER:mailto:boss@example.com"
need "DTSTAMP:20260930T120000Z"

echo "  字段丢失数: $MISS"

echo
echo "=== [5/5] 往返幂等 + 错误检查 ==="
"$PY" tools/e2e.py fill "$EV/exported.ics" >/dev/null 2>&1
"$PY" tools/e2e.py parse 2>&1 | tail -2
RT=$("$PY" tools/e2e.py parse 2>&1 | grep -oE "新增 [0-9]+ / 改期 [0-9]+ / 跳过 [0-9]+" | head -1)
echo "  往返结果: ${RT:-<没抓到>}"
RT_OK=0
case "$RT" in
  *"新增 0 / 改期 0 / 跳过 2"*) echo "  OK   往返幂等（未知属性不产生副本）"; RT_OK=1 ;;
  *) echo "  FAIL 往返不幂等（期望 新增 0 / 改期 0 / 跳过 2）" ;;
esac

NERR=$(host_error_count "$OUT/run-extra.log")
echo "编译/运行错误数: $NERR"

kill_host

if [ "$MISS" != "0" ] || [ "$RT_OK" != "1" ] || [ "$NERR" != "0" ] || [ "${WIDE:-0}" != "0" ]; then
  echo "结论：FAIL"
  exit 1
fi
echo "结论：PASS"
exit 0