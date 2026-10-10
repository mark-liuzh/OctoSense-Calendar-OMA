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
#   ⚠️ 快照里格子里有**三种**同尺寸（3.5px）的小点，**长得一模一样**：
#      放假绿点 / 节日上班深灰点 / 事件赤陶点。所以 DOTS 是三者之和，
#      期望值必须按「放假天数 + 节日上班天数」推导，不能只数绿点
#      （详细推导见下方「点数期望值的三色构成」注释块）。
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

# ── 点数期望值的三色构成（2026-10-08 修，v0.5.0）────────────────────────
#★ 本节的 DOTS / eqkind 期望值此前只按「放假绿点」算，于是 5 条断言长期红。
#  根因不是应用画错，而是**期望值少算了一种点**：
#   /snap 快照不带颜色，holiday_marks() 只能按「3~4.5px 的小方块」统计划点，
#   而格子里其实有**三种**同尺寸的点（main.splash 标记行）：
#     ① 放假绿点  c_ok    #15803d  ← hol == 1（法定放假）
#     ② 上班深灰点 c_ink2 #6b6560  ← fest == 1（节日但照常上班）
#     ③ 事件赤陶点 c_accent #b4531f ← dot == 1（当天有日程）
#   三者都是 3.5px，快照里长得一模一样，**只能靠截图取色区分**（见下面 eqkind）。
#
#⇒ 恒等式（每一步的 DOTS 都按它推导，不要凭印象写数）：
#       DOTS = 放假天数 + 该月「节日但照常上班」的天数 + 该月有日程的天数
#   推导节日上班天数要查bundle/main.splash 的三张表：
#     HOLIDAYS     |YYYYMMDD|…            法定放假（绿点）
#     WORKDAYS     |YYYYMMDD|…            调休上班（写「班」字，不画点）
#     CN_SPANS     起|止|名|…中国法定节日区间 → 但落在 HOLIDAYS 里才算放假
#     CHINA_FIXED  MMDD|短名|简介 中国特别日（九一八/抗战/长征…）→ **永远照常上班 = 深灰点**
#     INTL_FIXED   MMDD|名称|简介 国际节日（万圣节…）→ 照常上班 = 深灰点
#   ⚠️ 下面每处期望值后面都注明了「哪几天、哪张表」，改数据表必须回来重算。
#  ⚠️ 事件点（③）只在导入过 ICS 的月份才会出现；本脚本全程不导入，
#     事件库为空 ⇒ 所有步骤的 DOTS 里**不含事件点**。

# 从 KEY=value 输出里取值
val() { printf '%s\n' "$2" | grep -m1 "^$1=" | cut -d= -f2- ; }

# 截图 + **同源快照**（2026-10-08 加）。
#   $1 = png名。快照存成同名 .snap.json，供 dotcolor 复用。
# ⚠️⚠️ 为什么必须成对导出（本轮最难查的一个假红，2026-10-08）：
#   `e2e.py dotcolor` 原本会**自己重新 snap()** 拿当前布局，再拿这些矩形去读
#   **几十毫秒前拍的那张 png**。翻月/切节日来源时两者会错开一个月：
#   文本断言读新月份、像素断言读旧截图 ⇒ 报「期望 8 个点、实际 5 个」，
#   看起来像应用画错了，真因是**测试自己混用了两个时刻的证据**。
#   实测 8 轮里有 1 轮复现（随机），所以必须同源，不能靠「多跑几次碰运气」。
# ⚠️ 顺序：**先取快照、后截图**（2026-10-09）。反过来的话，
#   快照与截图之间还夹着一次 HTTP往返，窗口更大。
#   快照走 `e2e.py dumpsnap` 而不是裸 curl —— 前者带「等渲染完成」，
#   裸curl 可能正好落在翻月后的重绘空窗里，导出一份没有格子的树。
shot() {
  # ⚠️ 这里**不要** `>/dev/null 2>&1`（2026-10-09 踩过）：
  #   dumpsnap 失败时会留下一个 0 字节的 .snap.json，
  #   dotcolor 之后拿它当快照 ⇒ 所有像素判定变成「（无）」，
  #   而真正的错误信息被丢弃、只见一堆莫名其妙的红。
  #   失败就让它显形，并顺手清掉空文件，避免被误当成有效快照。
  if ! "$PY" tools/e2e.py dumpsnap "$OUT/evidence/${1%.png}.snap.json"; then
    echo "  FAIL 导出同源快照失败（$1）" >&2
    rm -f "$OUT/evidence/${1%.png}.snap.json"
  fi
  $CURL "http://127.0.0.1:$PORT/g?raw=1&t=$RANDOM$RANDOM" -o "$OUT/evidence/$1" 2>/dev/null
}

# 翻到指定月份，**并输出该月的 KEY=value**（供后续断言直接用）。
#   $1 = 目标月份 YYYY-MM；输出写到全局变量 FEST_OUT（供调用方取用）。
# ⚠️ 三轮返工才把这块做对（2026-10-08/09），记下来别再推翻：
#  1. 原来 4 处 `e2e.py goto YYYY-MM >/dev/null 2>&1` 把输出整个丢掉，
#     goto 没生效时**静默继续**，后面按月份写的断言全在错月份上跑。
#  2. 把「翻月」与「读界面」合并成**一次调用**（原先是 goto + fest 两条命令，
#     中间有窗口，宿主正好在窗口里复位状态 ⇒ 随机假红）。
#  3.宿主的点击是**排队异步落地**的，延迟可能超过 goto 内部的等待窗；
#     e2e.py 侧已经「整轮重试直到稳定」，这里再加一层整步重试兜底。
FEST_OUT=""
goto_month_check() {
  local ym="$1" out act stable i
  for i in 1 2 3; do
    out=$("$PY" tools/e2e.py goto "$ym" 2>&1)
    # ⚠️ grep 不能锚行首（2026-10-08 踩过）：TARGET/ACTUAL/STABLE 打在**同一行**，
    #   用 `^MONTHS_ACTUAL=` 会永远抓不到 → 误报「未到达」。
    act=$(printf '%s\n' "$out" | grep -m1 -o 'MONTHS_ACTUAL=[^ 	]*' | cut -d= -f2-)
    stable=$(printf '%s\n' "$out" | grep -m1 -o 'STABLE=[a-z]*' | cut -d= -f2-)
    if [ "$act" = "${ym}" ] && [ "$stable" = "yes" ]; then
      ok "翻到 ${ym}（已稳定）"
      # 只保留 KEY=value 行，丢掉 MONTHS_*/STABLE/FAIL 等控制行
      FEST_OUT=$(printf '%s\n' "$out" | grep -E '^(MONTH|FEST|HOL|SRC|BAN|DOTS|TEXTS)=')
      return 0
    fi
    sleep 0.5
  done
  # ⚠️ 这里**必须写 ${ym} 而不是 $ym**（2026-10-08 踩过）：
  #    macOS 自带 bash 3.2 解析 `$ym，`（美元符后紧跟全角逗号）时，
  #    会把全角逗号的**首字节当成变量名的一部分** ⇒ 报 `ym?: unbound variable`。
  #    凡是「$变量」后面紧跟中文字符的地方，一律加花括号。
  bad "翻月失败 — 期望 ${ym}，实际 ${act:-未到达}（重试 3 轮仍不稳定）"
  FEST_OUT=$(printf '%s\n' "$out" | grep -E '^(MONTH|FEST|HOL|SRC|BAN|DOTS|TEXTS)=')
  return 1
}

# 切换节日来源，**并输出该状态的 KEY=value**（供后续断言直接用）。
#   同goto_month_check 的理由：原来 3 处 `cycle >/dev/null 2>&1` 把输出丢了，
#   宿主偶发吞掉点击时整步在**旧来源**上断言，报「期望节日 国际、实际节日 中国」。
#   e2e.py cycle 现在自己闭环等待并在同一次调用里输出 fest。
#   $1 = 期望的来源文案；输出写到全局变量 FEST_OUT。
cycle_source_check() {
  local want="$1" out got i
  # 同样加整步重试：宿主点击排队异步落地，偶发「点了但没切过去」。
  # 每次重试 cycle 只会**再推进一格**，所以失败重来不会「跳过」目标来源 ——
  # 最多停在某个来源上，由下面的校验把话说清楚。
  for i in 1 2 3; do
    out=$("$PY" tools/e2e.py cycle 2>&1)
    # ⚠️ 不能用 `grep -o 'SRC=[^ \t]*'`（2026-10-08 踩过）：SRC 的值是
    #   「节日 国际」这种**含空格**的串，排除空白的写法只会取到「节日」。
    #   这里取整行再剥掉 `SRC=` 前缀。
    got=$(printf '%s\n' "$out" | grep -m1 '^SRC=' | cut -d= -f2-)
    if [ "$got" = "${want}" ]; then
      ok "切到${want}"
      FEST_OUT=$(printf '%s\n' "$out" | grep -E '^(MONTH|FEST|HOL|SRC|BAN|DOTS|TEXTS)=')
      return 0
    fi
  done
  bad "切节日来源失败 — 期望「${want}」，实际「${got:-未切换}」"
  FEST_OUT=$(printf '%s\n' "$out" | grep -E '^(MONTH|FEST|HOL|SRC|BAN|DOTS|TEXTS)=')
  return 1
}

# ── 像素级取色 ──
#   $1 = png。**必须把同名 .snap.json 一起传进去**（见 shot()处的说明）：
#   不传的话 dotcolor 会重新取实时快照，与这张 png 可能不是同一个时刻。
#   输出 DOTKIND= / DOTCOLORS= / DOTXY / BANXY / BANKIND=
dots() {
  local png="$1"
  "$PY" tools/e2e.py dotcolor "$png" "${png%.png}.snap.json" 2>&1
}
# 断言：所有标记点的语义色序列恰好等于 $2（$2 为空串 = 应当一个点都没有）
eqkind() {
  local got; got=$(val DOTKIND "$3")
  if [ "$got" = "$2" ]; then ok "$1 = ${2:-（无）}"; else bad "$1 — 期望 ${2:-（无）}，实际 ${got:-（无）}"; fi
}
# 断言：所有「班」字的颜色语义序列等于 $2（空串 = 不该有「班」字）
# ⚠️ 2026-10-09（P2-5）：$2 现在是**逗号分隔的序列**（e.g. "EVENT,EVENT"），
#   因为 dotcolor 改成对**每一个**「班」都取色 —— 原来只判第1 个，
#   某月有多个调休日时后面的颜色错了也测不出来。
#   仍写"EVENT"（不带逗号）也能工作：那表示「恰好一个，且是 EVENT」。
eqban() {
  local got want
  got=$(val BANKIND "$3")
  # 单值期望 → 展开成「恰好一个」的判定，保持旧写法可用
  case "$2" in
    *,*) want="$2" ;;
    "")   want="" ;;
    *)   want="$2" ;;
  esac
  if [ "$got" = "$want" ]; then ok "$1 = ${want:-（无）}"
  else
    #红了就把逐个坐标的结果一起打出来，省得再跑一次探针
    bad "$1 — 期望 ${want:-（无）}，实际 ${got:-（无）}  [$(val BAN_KIND_DETAIL "$3")]"
  fi
}

echo "=== [1/9] 启动宿主 ==="
boot_host "$OUT/run.log"
assert_clean
echo "宿主就绪"

echo
echo "=== [2/9] 默认来源「中国」· 2026 年 9 月 ==="
# ★ 2026-10-01：显式**绝对定位**到 2026-09。
#   应用打开的是**当月**（今天 10-01 → 打开就是 10 月），而这一节以及后面几步的
#   期望值都是按「进来时是 9 月」写的（中秋 / 放假 3 天 / 9/20 上班）。
#   原来靠的是一个隐含假设，没有任何一行代码保证它 —— 日期一翻就整体错一格。
#   改成显式 goto，与「今天几号」解耦：任何设备、任何日期跑都对。
goto_month_check "2026-09"
F="$FEST_OUT"   # 同一次调用里带回来的快照（见 goto/cycle 的注释）
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F"); SRC=$(val SRC "$F")
has    "节日行写出中秋"      "中秋"          "$FEST"
has    "放假行写出放假天数"  "放假 3 天"     "$HOL"
has    "放假行写出调休上班"  "9/20 上班"     "$HOL"
has    "来源按钮显示中国"    "节日 中国"     "$SRC"
eqnum  "调休「班」字个数"    "1"             "$(val BAN "$F")"
# ★ 2026-10-08 重算：3 绿（中秋 9/25,26,27 · HOLIDAYS）+ 2 深灰
#   （9/3 抗战、9/18 九一八 · CHINA_FIXED 里的中国特别日，**永远照常上班**）= 5。
#   原来写 3 是只算了绿点 ⇒ 这条从 v0.4.0 起就一直红。
eqnum  "标记点个数（放假绿 + 节日上班深灰）" "5" "$(val DOTS "$F")"
# ⚠️ 原来只匹配 "2026"，而 10 月也含 "2026" ⇒ 这条从 v0.4.0 起**一直在空过**，
#    正是它让「月份没翻成功」这件事在前几轮里完全看不出来。改成匹配完整月份。
has    "月历标题为 2026 年 9 月" "2026 年 9 月" "$(val MONTH "$F")"
shot "01-sep-cn.png"
# 像素回读：行优先顺序 = 9/3 深灰 → 9/18 深灰 → 9/25,26,27 绿（按日历行从上到下）
D=$(dots "$OUT/evidence/01-sep-cn.png")
eqkind "标记点像素判定（2 深灰 WORK + 3 绿 OK）" "WORK,WORK,OK,OK,OK" "$D"
eqban  "「班」字像素判定（赤陶 EVENT）"  "EVENT"    "$D"

echo
echo "=== [3/9] 翻到 2026 年 10 月（国庆 7 天 + 10/10 补班）==="
goto_month_check "2026-10"
F="$FEST_OUT"   # 同一次调用里带回来的快照（见 goto/cycle 的注释）
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F")
has    "节日行写出国庆"      "国庆"          "$FEST"
has    "放假行写出放假天数"  "放假 7 天"     "$HOL"
has    "放假行写出调休上班"  "10/10 上班"    "$HOL"
eqnum  "调休「班」字个数"    "1"             "$(val BAN "$F")"
# ★ 2026-10-08 重算：7 绿（国庆 10/1..10/7 · HOLIDAYS）+ 1 深灰
#   （10/22 长征 · CHINA_FIXED）= 8。原来写 7 只算了绿点。
eqnum  "标记点个数（放假绿 + 节日上班深灰）" "8" "$(val DOTS "$F")"
shot "02-oct-cn.png"
D=$(dots "$OUT/evidence/02-oct-cn.png")
eqkind "标记点像素判定（7 绿 OK + 1 深灰 WORK）" "OK,OK,OK,OK,OK,OK,OK,WORK" "$D"
eqban  "「班」字像素判定（赤陶 EVENT）"  "EVENT"                "$D"

echo
echo "=== [4/9] 切到「仅国际」：国内放假标记必须全部消失 ==="
cycle_source_check "节日 国际"
F="$FEST_OUT"   # 同一次调用里带回来的快照（见 goto/cycle 的注释）
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F"); SRC=$(val SRC "$F")
has    "来源按钮显示国际"    "节日 国际"     "$SRC"
has    "节日行写出万圣节"    "万圣节 10/31"  "$FEST"
hasnot "不再显示国庆"        "国庆"          "$FEST"
hasnot "放假行整行让位"      "放假"          "$HOL"
eqnum  "调休「班」字清零"    "0"             "$(val BAN "$F")"
# 十月国内有 2 个节日上班日：10/22 长征（CHINA_FIXED）+ 万圣节 10/31（INTL_FIXED）。
# 国内绿点 7 个在切到「仅国际」时全部消失 —— 这一步就是验证「切了个寂寞」没有发生。
# 快照 JSON 不带颜色，所以这里只能断言**总数**；
# 深灰点要靠 03-oct-intl.png 的像素判定确认（下面 eqkind）。
eqnum  "只剩万圣节深灰点"    "1"             "$(val DOTS "$F")"
shot "03-oct-intl.png"
# 用户诉求里最关键的颜色区分：**国际节日照常上班 = 深灰小黑点**，
# 必须和「放假绿点」区分开。切到「仅国际」后国内放假标记应全部消失。
D=$(dots "$OUT/evidence/03-oct-intl.png")
eqkind "小黑点像素判定（深灰 WORK）" "WORK" "$D"
eqban  "无「班」字"                  ""     "$D"

echo
echo "=== [5/9] 切到「全部」：国内 + 国际并集 ==="
cycle_source_check "节日 全部"
F="$FEST_OUT"   # 同一次调用里带回来的快照（见 goto/cycle 的注释）
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F"); SRC=$(val SRC "$F")
has    "来源按钮显示全部"    "节日 全部"     "$SRC"
has    "并集里有国庆"        "国庆"          "$FEST"
has    "并集里有万圣节"      "万圣节"        "$FEST"
hasnot "多节日时不写日期"    "10/31"         "$FEST"
has    "放假天数回来了"      "放假 7 天"     "$HOL"
eqnum  "调休「班」字个数"    "1"             "$(val BAN "$F")"
# ★ 2026-10-08 重算：并集 = 7 绿（国庆）+ 2 深灰（10/22 长征 + 10/31 万圣节）= 9。
#   原来写 8 —— 漏了长征那个点，只数了万圣节。
eqnum  "标记点个数（7 绿 + 2 深灰并集）" "9" "$(val DOTS "$F")"
shot "04-oct-all.png"
# 并集模式：7 个放假绿 + 长征深灰 + 万圣节深灰（行优先顺序：长征 10/22 在万圣节 10/31 之前）
D=$(dots "$OUT/evidence/04-oct-all.png")
eqkind "并集像素判定（7 绿 + 2 深灰）" "OK,OK,OK,OK,OK,OK,OK,WORK,WORK" "$D"
eqban  "「班」字像素判定（赤陶 EVENT）"  "EVENT"                   "$D"

echo
echo "=== [6/9] 切回「仅中国」 ==="
cycle_source_check "节日 中国"
F="$FEST_OUT"   # 同一次调用里带回来的快照（见 goto/cycle 的注释）
SRC=$(val SRC "$F"); FEST=$(val FEST "$F"); HOL=$(val HOL "$F")
has    "来源按钮回到中国"    "节日 中国"     "$SRC"
hasnot "不再显示万圣节"      "万圣节"        "$FEST"
ok     "按钮文案轮转一周无残留"

echo
echo "=== [7/9] 翻到 2025 年 10 月（2025 数据集：国庆中秋 8 天 + 10/11 补班）==="
# 2025-10：直接 goto，不再依赖「现在正好在 2026-10」这个前置条件
goto_month_check "2025-10"
F="$FEST_OUT"   # 同一次调用里带回来的快照（见 goto/cycle 的注释）
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F"); MONTH=$(val MONTH "$F")
has    "落到 2025 年 10 月"    "2025 年 10 月"   "$MONTH"
has    "节日行写出国庆中秋"    "国庆中秋"        "$FEST"
has    "放假行写出放假天数"    "放假 8 天"       "$HOL"
has    "放假行写出 10/11 补班" "10/11"           "$HOL"
eqnum  "调休「班」字个数"      "1"               "$(val BAN "$F")"
# ★ 2026-10-08 重算：8 绿（国庆中秋 10/1..10/8 · HOLIDAYS）+ 1 深灰
#   （10/22 长征 · CHINA_FIXED）= 9。原来写 8 只算了绿点。
eqnum  "标记点个数（放假绿 + 节日上班深灰）" "9" "$(val DOTS "$F")"
shot "05-oct2025-cn.png"
D=$(dots "$OUT/evidence/05-oct2025-cn.png")
eqkind "标记点像素判定（8 绿 OK + 1 深灰 WORK）" "OK,OK,OK,OK,OK,OK,OK,OK,WORK" "$D"
eqban  "「班」字像素判定（赤陶 EVENT）"  "EVENT"                   "$D"

echo
echo "=== [8/9] 再往前 1 个月到 2025 年 9 月（9/28 是调休上班日）==="
# ⚠️ 9/28 属于**九月**，不是十月 —— 断言要落在正确的月份上。
#    （第一版写成在 10 月里找 9/28，测试自己错了，不是应用错。）
goto_month_check "2025-09"
F="$FEST_OUT"   # 同一次调用里带回来的快照（见 goto/cycle 的注释）
printf '%s\n' "$F"
FEST=$(val FEST "$F"); HOL=$(val HOL "$F"); MONTH=$(val MONTH "$F")
has    "落到 2025 年 9 月"     "2025 年 9 月"    "$MONTH"
has    "放假行写出 9/28 补班"  "9/28 上班"       "$HOL"
hasnot "九月没有法定放假"      "放假"            "$HOL"
eqnum  "调休「班」字个数"      "1"               "$(val BAN "$F")"
# ★ 2026-10-08 重算：2025-09 **没有任何法定放假** ⇒ 绿点 0；
#   但有 2 个节日上班日 → 2 个深灰点（9/3 抗战、9/18 九一八 · CHINA_FIXED）。
#   9/28 是调休上班（WORKDAYS），它只写「班」字、**不画点**，所以不计入 DOTS。
#   原来写 0（当时以为「一个点都没有」）⇒ 这条长期红。
eqnum  "标记点个数（0 绿 + 2 节日上班深灰）" "2" "$(val DOTS "$F")"
shot "06-sep2025-cn.png"
# 2025-09：没有放假 ⇒ 一个绿点都没有，但两个深灰点必须都在（行优先：9/3 → 9/18）
D=$(dots "$OUT/evidence/06-sep2025-cn.png")
eqkind "无放假绿点、只有 2 个节日上班深灰点" "WORK,WORK" "$D"
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
