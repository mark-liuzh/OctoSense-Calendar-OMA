#!/usr/bin/env bash
# OctoSense 端到端实测 · ④ 节假日标注 + 节日来源切换
#
# 覆盖用户明确提出的三点诉求：
#   1. 日历要标出法定节假日（放假 = 小绿点）
#   2. 调休上班日要有明显标记（写「班」字）
#   3. 节日来源可切换：仅中国 / 仅国际 / 全部，切换后标记要跟着变
#
# ★ 除了读布局树（/snap 只有 i/ty/r/w，**不带颜色**），
#   本脚本还会把截图回读成像素，逐个标记点**判定语义色**：
#     OK    = 放假（c_ok #15803d 绿）
#     WORK  = 节日但照常上班（c_ink2 #6b6560 深灰，用户要的「小黑点」）
#     EVENT = 有日程（c_accent #b4531f 赤陶）
#   「班」字也单独判色（应为 EVENT，即赤陶）。
#   判定器见 tools/e2e.py 的 dot_kinds()：在标记点中心 5×5 邻域里按像素**投票**。
#   为什么不能取中位/最深像素：3.5px 的点在当前 DPI 下只有约 6px、边缘一圈
#   全是抗锯齿过渡色；而绿 #15803d 与灰 #6b6560 的亮度几乎相同（≈100/≈102），
#   两种取法都判不准。
#
# 用法: bash tools/run_festival.sh
# 可选: PY=<python>  OCTO_CARD_HOST=<card-host>  PORT=<端口>
#
# ⚠️ 依赖真实日期：脚本假设「今天」落在 2026 年（日历默认停在本月）。
#    若在别的年份跑，[2/8] 步的期望值需要跟着改 —— 断言会明确报出来，
#    不会静默通过。
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
mkdir -p "$OUT/evidence"
rm -f "$OUT"/evidence/*.png 2>/dev/null || true
# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

static_gate

FAIL=0
ok()   { echo "  OK   $1"; }
bad()  { echo "  FAIL $1"; FAIL=1; }

# 断言 $3（实际输出）里必须 / 不得包含子串 $2
has()    { case "$3" in *"$2"*) ok "$1" ;; *) bad "$1 — 期望含「$2」，实际：$3" ;; esac; }
hasnot() { case "$3" in *"$2"*) bad "$1 — 不该含「$2」，实际：$3" ;; *) ok "$1" ;; esac; }
eqnum()  { if [ "$2" = "$3" ]; then ok "$1 = $3"; else bad "$1 — 期望 $2，实际 $3"; fi; }

# 从 KEY=value 输出里取值
val() { printf '%s\n' "$2" | grep -m1 "^$1=" | cut -d= -f2- ; }

shot() { sleep 0.7; $CURL "http://127.0.0.1:$PORT/g?raw=1&t=$RANDOM$RANDOM" -o "$OUT/evidence/$1" 2>/dev/null; }

# ── 像素级取色 ──
#   $1 = png，输出 DOTKIND= / DOTCOLORS= / BANKIND=
dots() { "$PY" tools/e2e.py dotcolor "$1" 2>&1; }
# 断言：所有标记点的语义色序列恰好等于 $2（$2 为空串 = 应当一个点都没有）
eqkind() {
  local got; got=$(val DOTKIND "$3")
  if [ "$got" = "$2" ]; then ok "$1 = ${2:-（无）}"; else bad "$1 — 期望 ${2:-（无）}，实际 ${got:-（无）}"; fi
}
# 断言：「班」字的颜色语义等于 $2（空串 = 不该有「班」字）
eqban() {
  local got; got=$(val BANKIND "$3")
  if [ "$got" = "$2" ]; then ok "$1 = ${2:-（无）}"; else bad "$1 — 期望 ${2:-（无）}，实际 $got"; fi
}

echo "=== [1/9] 启动宿主 ==="
boot_host "$OUT/run.log"
assert_clean
echo "宿主就绪"

echo
echo "=== [2/9] 默认来源「中国」· 本月（2026 年 9 月）==="
F=$("$PY" tools/e2e.py fest 2>&1)
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F"); SRC=$(val SRC "$F")
has    "节日行写出中秋"      "中秋"          "$FEST"
has    "放假行写出放假天数"  "放假 3 天"     "$HOL"
has    "放假行写出调休上班"  "9/20 上班"     "$HOL"
has    "来源按钮显示中国"    "节日 中国"     "$SRC"
eqnum  "调休「班」字个数"    "1"             "$(val BAN "$F")"
eqnum  "放假绿点个数"        "3"             "$(val DOTS "$F")"
has    "月历标题为 2026 年 9 月" "2026"      "$(val MONTH "$F")"
shot "01-sep-cn.png"
# 像素回读：3 个放假绿点 + 9/20 的「班」字（赤陶）
D=$(dots "$OUT/evidence/01-sep-cn.png")
eqkind "绿点像素判定（3 个都是放假绿）" "OK,OK,OK" "$D"
eqban  "「班」字像素判定（赤陶 EVENT）"  "EVENT"    "$D"

echo
echo "=== [3/9] 翻到 2026 年 10 月（国庆 7 天 + 10/10 补班）==="
"$PY" tools/e2e.py months 1 >/dev/null 2>&1
F=$("$PY" tools/e2e.py fest 2>&1)
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F")
has    "节日行写出国庆"      "国庆"          "$FEST"
has    "放假行写出放假天数"  "放假 7 天"     "$HOL"
has    "放假行写出调休上班"  "10/10 上班"    "$HOL"
eqnum  "调休「班」字个数"    "1"             "$(val BAN "$F")"
eqnum  "放假绿点个数"        "7"             "$(val DOTS "$F")"
shot "02-oct-cn.png"
D=$(dots "$OUT/evidence/02-oct-cn.png")
eqkind "绿点像素判定（7 个都是放假绿）" "OK,OK,OK,OK,OK,OK,OK" "$D"
eqban  "「班」字像素判定（赤陶 EVENT）"  "EVENT"                "$D"

echo
echo "=== [4/9] 切到「仅国际」：国内放假标记必须全部消失 ==="
"$PY" tools/e2e.py cycle >/dev/null 2>&1
F=$("$PY" tools/e2e.py fest 2>&1)
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F"); SRC=$(val SRC "$F")
has    "来源按钮显示国际"    "节日 国际"     "$SRC"
has    "节日行写出万圣节"    "万圣节 10/31"  "$FEST"
hasnot "不再显示国庆"        "国庆"          "$FEST"
hasnot "放假行整行让位"      "放假"          "$HOL"
eqnum  "调休「班」字清零"    "0"             "$(val BAN "$F")"
# 十月国际节日只有万圣节 10/31 → 「节日但照常上班」＝ 1 个小黑点。
# 快照 JSON 不带颜色，所以这里只能断言**总数**；
# 绿点/黑点/事件点三色要靠 03-oct-intl.png 肉眼确认。
eqnum  "只剩万圣节小黑点"    "1"             "$(val DOTS "$F")"
shot "03-oct-intl.png"
# 用户诉求里最关键的颜色区分：**国际节日照常上班 = 深灰小黑点**，
# 必须和「放假绿点」区分开。切到「仅国际」后国内放假标记应全部消失。
D=$(dots "$OUT/evidence/03-oct-intl.png")
eqkind "小黑点像素判定（深灰 WORK）" "WORK" "$D"
eqban  "无「班」字"                  ""     "$D"

echo
echo "=== [5/9] 切到「全部」：国内 + 国际并集 ==="
"$PY" tools/e2e.py cycle >/dev/null 2>&1
F=$("$PY" tools/e2e.py fest 2>&1)
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F"); SRC=$(val SRC "$F")
has    "来源按钮显示全部"    "节日 全部"     "$SRC"
has    "并集里有国庆"        "国庆"          "$FEST"
has    "并集里有万圣节"      "万圣节"        "$FEST"
hasnot "多节日时不写日期"    "10/31"         "$FEST"
has    "放假天数回来了"      "放假 7 天"     "$HOL"
eqnum  "调休「班」字个数"    "1"             "$(val BAN "$F")"
# 7 个放假绿点 + 1 个万圣节小黑点 = 8
eqnum  "放假绿点 + 小黑点"   "8"             "$(val DOTS "$F")"
shot "04-oct-all.png"
# 并集模式：7 个放假绿 + 1 个万圣节深灰（行优先顺序）
D=$(dots "$OUT/evidence/04-oct-all.png")
eqkind "并集像素判定（7 绿 + 1 深灰）" "OK,OK,OK,OK,OK,OK,OK,WORK" "$D"
eqban  "「班」字像素判定（赤陶 EVENT）"  "EVENT"                   "$D"

echo
echo "=== [6/9] 切回「仅中国」 ==="
"$PY" tools/e2e.py cycle >/dev/null 2>&1
F=$("$PY" tools/e2e.py fest 2>&1)
SRC=$(val SRC "$F"); FEST=$(val FEST "$F"); HOL=$(val HOL "$F")
has    "来源按钮回到中国"    "节日 中国"     "$SRC"
hasnot "不再显示万圣节"      "万圣节"        "$FEST"
ok     "按钮文案轮转一周无残留"

echo
echo "=== [7/9] 翻到 2025 年 10 月（2025 数据集：国庆中秋 8 天 + 10/11 补班）==="
# 起点的 2026-10 往前 12 个月 = 2025-10
"$PY" tools/e2e.py months -12 >/dev/null 2>&1
F=$("$PY" tools/e2e.py fest 2>&1)
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F"); MONTH=$(val MONTH "$F")
has    "落到 2025 年 10 月"    "2025 年 10 月"   "$MONTH"
has    "节日行写出国庆中秋"    "国庆中秋"        "$FEST"
has    "放假行写出放假天数"    "放假 8 天"       "$HOL"
has    "放假行写出 10/11 补班" "10/11"           "$HOL"
eqnum  "调休「班」字个数"      "1"               "$(val BAN "$F")"
eqnum  "放假绿点个数"          "8"               "$(val DOTS "$F")"
shot "05-oct2025-cn.png"
D=$(dots "$OUT/evidence/05-oct2025-cn.png")
eqkind "绿点像素判定（8 个都是放假绿）" "OK,OK,OK,OK,OK,OK,OK,OK" "$D"
eqban  "「班」字像素判定（赤陶 EVENT）"  "EVENT"                   "$D"

echo
echo "=== [8/9] 再往前 1 个月到 2025 年 9 月（9/28 是调休上班日）==="
# ⚠️ 9/28 属于**九月**，不是十月 —— 断言要落在正确的月份上。
#    （第一版写成在 10 月里找 9/28，测试自己错了，不是应用错。）
"$PY" tools/e2e.py months -1 >/dev/null 2>&1
F=$("$PY" tools/e2e.py fest 2>&1)
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F"); MONTH=$(val MONTH "$F")
has    "落到 2025 年 9 月"     "2025 年 9 月"    "$MONTH"
has    "放假行写出 9/28 补班"  "9/28 上班"       "$HOL"
hasnot "九月没有法定放假"      "放假"            "$HOL"
eqnum  "调休「班」字个数"      "1"               "$(val BAN "$F")"
eqnum  "放假绿点个数"          "0"               "$(val DOTS "$F")"
shot "06-sep2025-cn.png"
# 只有调休、没有放假：一个标记点都不该有，但有「班」字
D=$(dots "$OUT/evidence/06-sep2025-cn.png")
eqkind "没有任何标记点"                 ""      "$D"
eqban  "「班」字像素判定（赤陶 EVENT）"  "EVENT" "$D"

echo
echo "=== [9/9] 错误检查 ==="
ERR=$(grep -cE "error|SPLASH.*(not found|invalid|expect)" "$OUT/run.log" 2>/dev/null || true)
echo "编译/运行错误数: ${ERR:-0}"
if [ "${ERR:-0}" != "0" ]; then
  grep -nE "error|SPLASH.*(not found|invalid|expect)" "$OUT/run.log" | head -20
  FAIL=1
fi

echo
echo "=== 证据文件 ==="
ls -l "$OUT/evidence"/*.png 2>/dev/null
echo

# ⚠️ 必须收工（2026-09-30 修）：本脚本此前漏了 kill_host，跑完把宿主留在后台。
#    后果不是「本脚本失败」，而是**下一轮**失败：僵尸宿主占着端口与存储目录，
#    下一条流程既绑不上端口（就绪探测却打到了这个僵尸身上，整轮测的是别人的进程），
#    也清不掉存储（rm -rf 静默失败）——症状完全指不到真正的原因。
kill_host

if [ "$FAIL" = "0" ]; then echo "FESTIVAL PASS"; else echo "FESTIVAL FAIL"; fi
exit "$FAIL"
