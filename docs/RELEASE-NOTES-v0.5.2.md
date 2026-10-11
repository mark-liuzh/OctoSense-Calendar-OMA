# OctoSense 日历 v0.5.2 发布说明

日期：2026-10-11 · 基线：v0.5.1（commit `12a36b8`）
依据：Linux 全量测试反馈报告 + Windows 11 家庭版测试报告（两份均在 v0.5.1 上执行）

这一版的两个主题：**让静默的地方出声**，以及**让回归结果重新可信**。

---

## 一、修了什么

### 1. 测试基建（W1）——在它做完之前，任何回归结论都不成立

两份报告里那些「十几条红」的读法，全部指向同一个问题：**一条根因被放大成
一串假 FAIL**，而汇总里分不出来哪些是真应用失败。逐条修完后的实测：

| 工作项 | 修了什么 |
| --- | --- |
| W1-1 | 三个驱动脚本写死了开发者本机的 `D:/Projects/…/tools/octo`；`shot()` 又用 `capture_output=True` 吞掉 stderr 且从不检查退出码 ⇒ 干净克隆上 `FileNotFoundError`，一串 `px_at` 失败。改成「环境变量 → 仓库内 → PATH」解析，**找不到 octo 不再是致命**（直连宿主 `/g?raw=1` 抓帧），两条通道都查退出码 |
| W1-2 | `e2e.py open` 只查「entry 在树里」就算成功 —— 而 entry 与月历点击层是同层静态声明，宿主分步更新时会把**半帧**当成功。改成「entry 在树里 **且** 节点数大幅下降（实测 462→32）」连续两帧都满足；`fill` 失败 `exit(2)` 中断流程 |
| W1-3 | `run_e2e.sh` 补 `expect` / `expect_scroll` 双版本（`/snap` 只返回视口内控件） |
| W1-4 | `run_festival.sh` 用的是宽松 `grep -cE "error\|…"`，而其余 7 条只数 `[E]` —— **这一条口径不一致同时解释了 Linux 报的 1 和 Windows 报的 10** |
| W1-5 | `run_all.sh` 汇总分两行报「应用/断言失败（结论有效）」与「前置/夹具失败（不作应用结论）」 |
| W1-6 | `HOST_ERROR_WHITELIST` 从宽松子串改为锚定行首的精确匹配，并打 `[W] 白名单命中：` 让「0 错误」可追溯 |

配套把 `static_gate` 从 9 道扩到 13 道，新增 5 个纯 Python 夹具
（`host_errors` / `portability` / `shellsafe` / `writepoint` / 已有的 `ai_gates`）。

### 2. 应用本体（W2）

| 编号 | 修了什么 | 之前的表现 |
| --- | --- | --- |
| W2-1 | `reschedule()` 递增 `SEQUENCE` 并刷新 `DTSTAMP` | 原样透传 `e.sequence` ⇒ 改期多少次序号都不变。任何标准日历客户端按 RFC 5545 §3.8.7.4 会认为「这条从没被改过」而**静默丢弃**改期结果 |
| W2-2 | `build_advice()` 加全天门：两侧都全天不给建议；一侧全天只以定时方为 mover，且换一套文案 | 给全天事件算出「移到当天 09:00-21:00」的建议，用户点采纳后 `reschedule()` 静默返回 0 ⇒ **界面毫无反应** |
| W2-3 | 模型错误串白名单映射 | `"模型不可用（" + r.error + "）"` 把宿主原始错误串直入界面，无意义且可能泄露内部细节 |
| W2-4 | `listing.json` 的域名口径 | 第 8 行说「收成单域」、第 13 行说「用它换经纬度」，两句互相否定，而 manifest 实际是 2 域 |
| W2-5 | `AGENTS.md` 权限节 | 仍写「只列一个域」「geocoding-api 零引用已移除」—— v0.5.1 加城市后已作废 |

### 3. 静默丢弃与静默错算（W3，经拍板）

| 编号 | 决定 | 做了什么 |
| --- | --- | --- |
| W3-1 | 原样留存 + 导出写回 + 导入提示 | 不认识的属性（`VALARM` / `ATTENDEE` / `CATEGORIES` / `CLASS` / `TRANSP` / `GEO` / `PRIORITY` / `CREATED` / `LAST-MODIFIED` / `X-*` …）整行原文留在事件里，导出时原样写回；**容器属性（`BEGIN:VALARM`…`END:VALARM`）连包裹一起保留**，导出仍是合法 ICS；导入面板报「未识别 分类、公开度、占用 等 11 类属性，已原样保留」 |
| W3-2 | 只写明限制 | 跨时区**不做换算**，事件列表把「<TZID> 按字面」标出来；README 新增「已知限制」节写清原因（宿主没有时区库，完整实现要处理夏令时规则，半套比不做更危险） |
| W3-3 | 同时改 README | README 新增「已知限制 · Windows 上天气与城市选择拿不到数据」，写明这是**平台缺陷不是本应用 bug**，附完整源码链路 |

### 4. 节假日数据收敛（B-1）

删掉 `HOLIDAYS` / `CN_SPANS` 的 2027–2055 段（`WORKDAYS` 本来就只到 2026；`SOLAR_TERMS` 是 Meeus 实算，正确，保留）。

那份数据由一个**自检就被判为不通过**的生成器产出（`docs/P2-1-holiday-data-plan.md:61`），
根因是对国务院规则有原理性误解：元旦/清明/端午/中秋的 3 天是「挪用最近的周末」
凑出来的，具体挪哪天因年而异、必须逐条对照公告。已核对的硬错里最刺眼的是
**2042 中秋 8/30** —— 农历八月十五在公历上绝不可能落在 8 月。

删除的理由不是「数据不够」：`WORKDAYS` 只到 2026 意味着留着也只能显示「放假 X 天」、
永远显示不出「X/X 上班」，**收益≈0 而风险是真的**。这与 `README:343` 自己写的
「宁可明确『没有数据』，也不要猜错让人误了上班」一致 —— 之前是代码违反了自己的产品原则。

---

## 二、★ 没修什么

这一节是本文档存在的理由。

### 1. Windows 上天气与城市选择仍然拿不到数据（平台缺陷，本应用改不了）

```
makepad/platform/src/script/res.rs:574             平台自己设了一个「保留」header
 → makepad/platform/network/src/backend/windows/http.rs:43
 → makepad/platform/network/src/blocking_http.rs:220  is_reserved_header → 拒绝
 → makepad/platform/network/src/blocking_http.rs:513  "user-agent" 在保留名单里
```

只有 Windows 中招：Linux 与 Apple 后端是手写 socket 直接拼 header 字符串，
绕过该校验；只有 Windows 后端复用了 `blocking_http::Request`。
修复归属 makepad 仓库。**v0.5.2 发布后这条依然存在。**

⚠️ 连带影响：`sys.geocodenum` 与 `sys.weather` 共用 `script_data_fetch`，
所以同一个缺陷**同时打掉了城市选择** —— 而那是 v0.5.1 的核心卖点。
Windows 用户的实际体验是：天气永远显示北京，换城市点了没反应，且没有任何错误提示。

### 2. 跨时区换算（v0.6.0 再议）

当前按字面时间使用。完整实现要处理 `VTIMEZONE` 里的 `STANDARD` / `DAYLIGHT`
夏令时规则，而宿主没有时区库。仓促实现半套会算出「看起来对、其实错」的时刻。

### 3. 导入的 RRULE 不展开

只原样保留、原样写回。展开要处理 `EXDATE` / `RDATE` / `COUNT` / `UNTIL` 与跨时区夏令时。

### 4. 其余沿用旧版限制

时间胶囊不加密 · 共享无实时互通 · 不申请 `location` 权限（宿主桌面端拿不到 GPS）。

---

## 三、两份测试报告的核对结论

两份报告合计提出 16 条。逐条回到源码复核后：

- **11 条属实**（已修，见上）
- **4 条需要修正定性**：其中「ICS 丢属性违反往返无损硬性要求」定性过高 —— 本应用的往返无损定义只覆盖**本应用能识别的字段**，性质是「静默丢弃」而非「往返丢数据」；「像素断言硬编码坐标」是事实错误（报告引用的坐标是**失败时打印的命中坐标**，不是脚本写死的输入），真问题在缩放基准写死与投票半径过小
- **1 条是误判且方向相反**：两份报告都强烈建议「删掉 `network.hosts` 里的 `geocoding-api`」并列为 P0 安全问题。**照做会让城市选择 100% 静默失效**。两份报告的推理都是 `grep -c geocoding bundle/main.splash` = 0 ⇒ 零引用，但那是「**用了但看不见**」：URL 由宿主 `splash.rs:1662 geocode_url` 拼装，`sys.geocodenum` 与 `sys.fetch` / `sys.weather` 共用 `platform/src/script/res.rs:551 script_url_allowed` 这道门禁。v0.5.0 曾按报告建议删过一次，本版已恢复并在 `AGENTS.md` 写明链路
- **两份报告都没提到的新发现**：城市选择在 Windows 上同样是坏的（见「没修什么」第 1 条）

**报告建议的那道静态门禁本身也会把 v0.5.2 卡死**：`grep -q "$key" bundle/main.splash`
对 `geocoding-api` 必然失败，因为应用侧的 key 是 `sys.geocodenum`。
门禁必须改成「域 ↔ 宿主内建能力映射表」，不能纯字符串匹配。

---

## 四、实测结果

```
静态门禁      13 道全过
端到端流程    8/8 exit=0，8 条流程全部「编译/运行错误数: 0」
  run_conflict  21 条断言   run_festival  58 项断言
  run_new       31 条断言   run_layout   21 个界面状态几何异常 0
定点验收      verify_extra.sh 20/20 字段原样往返，往返幂等 0/0/2
```

往返幂等（对外最强硬指标）在加了 SEQUENCE 递增与未知属性留存之后**仍然成立**。
