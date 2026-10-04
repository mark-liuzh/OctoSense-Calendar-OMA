# OctoSense 日历 v0.4.0

**2026 GOSIM Agentic App Hackathon · 决赛版本 · 队伍 OMA**（成员 `mark-liuzh`、`ody-cai`）

> v0.4.0 是第一个**联网**版本：接入真实天气预报（含过去 30 天历史）、新增假期倒计时、
> 给日程与待办加上四级优先级标记。同时修掉了三个会让界面**静默消失**的缺陷。

---

## 一、新增

### 1. 实时天气进月历（联网）

- 月历每个格子的**左上角**显示当天天气：晴 / 多 / 阴 / 雨 / 雪 / 雷 / 雾（单字，8px）
  - 数字**恒定居中**于格子中心，不受图标影响
- 数据源：[Open-Meteo](https://open-meteo.com/)（`api.open-meteo.com`），
  北京坐标 `39.9042 / 116.4074`，`timezone=auto`
- **过去 30 天 + 未来 7 天**：
  - 未来 → `forecast_days=7`（JSON，走宿主内置天气原语）
  - 过去 → `past_days=30&format=csv`（自解析，容忍 CRLF，逐字符扫数字前缀）
- 冷启动只拉一次，结果缓存到本地 `wx_live2.json`；重开应用先读缓存、再异步刷新
- **离线回落**：取不到网时用上次缓存；无缓存则该格不显示图标（不报错、不空白）

### 2. 假期倒计时

- **待办区顶部**一张系统提示卡，例如
  `★ 国庆假期中，下个假 春节 还有 17周5天`
- **月历格子**：下个假期**当天**显示 `★`、**前一天**显示 `·`
- 只算国务院放假的那些天，**不提醒补班**；假期结束 24h 后卡片自动消失
- 节日只在**第一天**标记（不会国庆 7 天每天写一遍）

### 3. 日程 / 待办四级标记

| 等级 | 颜色 | 判定依据 |
|---|---|---|
| **紧急** | 红 `#b91c1c` | 承诺权重 ≥ 3（标题含 截止 / 提交 / deadline / 答辩） |
| **重要** | 琥珀 | 承诺权重 = 2（含 `ORGANIZER` 等） |
| **常规** | 无标记 | 默认 |
| **纪念** | 紫 `#6d5bd0` | 每年重复 / 生日 / 纪念 / 周年（`FREQ=YEARLY`） |

- **临期自动升级**：3 天内的「重要」**自动升到紧急档显示**
  （实测：同一条事件在 10/05 显示红、在 10/08 显示琥珀 —— 升级规则生效）
- 主列表左侧竖条按等级变色 + 事件标签出现「紧急 / 重要 / 纪念」chip
- 待办条目左侧出现对应颜色的小圆点

### 4. 复盘清单

- 待办区新增第三档过滤：**全部 / 只看未完成 / 复盘清单**
- 「复盘清单」= 跨日期聚合**所有超期未完成**的待办，每条带原日期
  （实测输出 `复盘清单：1 条超期未完成`）

---

## 二、修复

### ① 联网完全失效（Windows 平台）

`sys.fetch` 在 Windows 上被 UA 运行时挡掉。修复落在宿主侧：
`platform/network/src/backend/windows/http.rs`（跳过底层已自行处理的保留头）+
`blocking_http.rs`（`is_reserved_header` 改为 `pub`）。

### ② 「心情 / 目标 / 时光」三个分区整片白屏 ★严重

v0.4.0 新增的倒计时卡 `countdown_card` **结尾漏了一个 `}`**。
它从未闭合，把紧随其后的输入行以及 **`sec_mood` / `sec_goal` / `sec_egg`
三个分区全部吞成自己的子节点**；切到那三个标签时父节点 `sec_todo` 被隐藏
→ 整棵子树不参与布局 → 白屏。**运行时 0 报错**，静态门禁也全绿。

### ③ `tools/brace.py` 是一道形同虚设的门禁 ★严重

它**从来不 `sys.exit(1)`**，只 print 花括号深度；而 `run_all.sh` 判的是**退出码**
→ 这道门禁**永远是 PASS**。缺括号那版它会打印「最终 depth = 1」，流水线照常绿 ——
**这正是 ② 溜进去的原因**。

已重写为真门禁：
- 最终 depth ≠ 0 / depth 为负 / 有未闭合 `{` → `exit(1)`
- 用**栈**记录每个 `{` 的行号，EOF 时仍在栈里的直接打印「第 N 行 … 未闭合」
- 加**缩进启发式**：净增量 > 0 的行若「缩进 ≤ 父块缩进」→ 判为疑似缺 `}` 处
  （实测在坏文件上直接点名 `第 6162 行（父块开于 6144）` = `countdown_card`）

### ④ 月历里带天气的格子数字不居中

数字行原本是横向排列（`flow: Right`），右端挂天气图标
→ 数字占据的是「**扣掉图标之后的余量**」，于是**有天气的格子数字左移、
没天气的格子居中**，同一行之内数字错位。

改为**分层叠加**（`flow: Overlay`）：数字层占满整格宽度并居中，图标层单独贴左上角。
实测（读布局树坐标）：带天气 9 格的数字中心偏移均值 `-2.67px`，
无天气 26 格 `-2.56px`，**差 0.11px**。

### ⑤ 今天那格的黑圆把天气图标挡住

「今天」的实心黑圆 26px 几乎占满 27px 的数字行，图标放哪都会压上去。

根因是 **makepad 的 `Label` 自带默认 `margin` / `padding`** ——
一个 8px 的汉字图标其矩形宽达 **17px**（字形本身只有 9px）。
把两个图标 Label 的 padding / margin 归零后缩到 **11px**，
今天那格的图标与黑圆**恰好错开**，不再遮挡。

---

## 三、变更

- `bundle/manifest.json`：新增 `net` 能力 + 3 个域名白名单
  （`api.open-meteo.com` / `geocoding-api.open-meteo.com` / `archive-api.open-meteo.com`）
- 版本号 **0.3.1 → 0.4.0**
- `tools/_env.sh`：Windows 兼容补丁（splash 首次 eval 需 4–6s，
  「存储干净」前置检查改为轮询 15 次）
- `tools/featflow.py` / `shotfeat.py` / `shots.sh`：同步 UI 改名「小知识」→「时光」
- `bundle/assets/icon.svg`、`AGENTS.md` 等：仅行尾统一（无内容变化）

---

## 四、验证

- **8 道静态门禁** —— 8/8 PASS
  （brace / quotes / toplevel / deps / paintfix / btnfocus / cellhover / fncalls）
- **真机运行** —— 0 编译 / 运行错误；联网取数
  `loaded 1465 bytes (status 200)` + `loaded 1071 bytes (status 200)`，
  `live re-eval: epoch 0 -> 1`（429891 bytes）
- **能力授权** —— 宿主日志
  `admitted — capabilities {"net", "storage"}, hosts {"api.open-meteo.com", "archive-api.open-meteo.com", "geocoding-api.open-meteo.com"}`
- **四级标记** —— 用像素回读确认竖条颜色 `#b91c1c`、chip 底色 `#fdecec`，
  并以「同一条事件在不同日期显示不同等级」作为升级规则的活证据

---

## 五、⚠️ 已知限制

1. **bundle 未签名**：`integrity.bundle_blake3` 已是当前 bundle 的真实哈希，
   但 `signature` 字段为空 —— OMA 私钥只在 Ody 的机器上，需由 Ody 补签：
   ```bash
   hub stamp bundle
   hub sign-manifest bundle --key ~/.octosense/oma-publisher.key --key-id OMA
   hub check  bundle --publisher-key OMA=<publisher-key>
   ```
2. **农历 / 调休只覆盖 2025–2026**（公历固定节日已算到 2027–2029）
3. **天气依赖 Open-Meteo 可用性**；离线时自动回落到上次缓存，无缓存则不显示图标
4. **全量回归** `run_festival` 有一条已知 race（`[7/9]` 宿主偶发退出导致后续全 fail）；
   该流程单跑稳定 PASS，属于测试环境问题、不影响应用本身

---

## 六、数据来源与许可

- **天气数据**：Open-Meteo（CC BY 4.0），仅读取北京一个坐标点的公开预报
- **节假日数据**：国务院办公厅放假安排（内置，离线，覆盖 2025–2026）
- **节气时刻**：按天文算法实算（2025–2030）
- **源码许可**：Apache-2.0
- **吉祥物**：Noto Animated Emoji `:octopus:`（CC BY 4.0，© Google LLC），署名见 `THIRD-PARTY.md`
