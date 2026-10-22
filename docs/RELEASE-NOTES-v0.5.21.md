# OctoSense 日历 v0.5.21 发布说明

日期：2026-10-22 · 基线：v0.5.9（tag `v0.5.9` → `a9d8649`，GOSIM 复赛评审基准）
主题：官方宿主实机验证与修复全链 —— 指令预算根治 / AI 契约 / 邮件契约 / 数据安全

## 发布件

| 项 | 值 |
|---|---|
| Commit | `7267275fc60cbe8aa966767e5406bce67fa8fd5c`（main） |
| Tag | `v0.5.21` |
| Release | id `420521924`（已发布，非 draft） |
| Zip | `octosense-calendar-0.5.21-bundle.zip` · 2,770,879 bytes（22 files） · sha256 `cea63e4ac1d50ffd9840bbd5e8ea8df8c8195cf8c68f55f713c9a54b4872eb3c`（远端下载实测一致 ✅） |
| Bundle blake3 | `17c9ac72c924871111f112ac3faf1da270cfb4232b902d23eed8836c93c0b02f` |
| Publisher key id | `OMA` |
| App Hub 提交 issue | [#234](https://github.com/OctoSense-org/OctoSense-App-Hub/issues/234)；复赛声明 issue #232 已评论回验（comment id 6337362251） |
| 准入检查 | `hub check bundle --publisher-key OMA=46b11cc1…` → **PASSED**（2026-10-22） |

## 一、本版主题

把「本地回归全绿」升级成「官方宿主可用」。GOSIM 复赛（#232 按 v0.5.9/a9d8649 评）指出三个失分点：
①指令预算、②model schema、③mail 契约——它们都只在**官方宿主**暴露：本机 `card-host`
无脚本指令上限、不注册 model / mail 服务，本地回归全绿无法覆盖。

本版在官方 **OctoSense 0.1.0-rc.6** 桌面宿主（macOS arm64，真实 `HostLimits::default()`
= 20M 指令预算 / 64 MiB heap / 16 MiB storage，真实 `model.complete` 与 `mail.*` 服务）上
完整跑通应用，三个失分点全部根治，并修复实机新发现的 6 类问题。

## 二、修复清单（全部 rc.6 实测复现并回验）

### 1. 指令预算超限（评审点①）——根治

- **症状**：月历刷新 / 导入后 refresh 触发 `script instruction limit exceeded`（20M），
  事件回调静默中断（评审观察到的「写入确认条不出现」）。
- **定位路径**：`with_instruction_limit` 按 eval epoch 共享 20M 池；经「查表短路探针」
  （把 `month_cache_build()` 日循环查表全部短路）实证 **3 个 eval epoch 错误归零**，
  锁定边际项 = `cal_cells()` 首帧 `ensure_month_cache()` 的按日 × 按表双重查表。
- **根治（两层）**：
  1. `month_cache_stub()`：eval 期先填 42 格空缓存，首帧只画占位；`cal_cells()` 不再
     `ensure_month_cache()`；整月构建收口到 `refresh_all()` 顶部（0.4s 后独立 handler、独占一池）。
     节日/天气标记晚 ~0.4s 出现（可接受）。
  2. `month_cache_build()` 索引化：放假/调休（含 `cn_holiday_shown()` 门 = `festival_mode != 1`）、
     节日名（CN 区间 → 中国特别日 → 国际，含 festival_mode 优先级）、天气图标三张表
     **每月各扫一遍**，按日装配零查表，构建成本降到约 1/4。
- **结果**：boot 三个 eval epoch（含两次天气触发 re-eval）的 `[E]` 由 3 → **0**。
  （manifest `compute.instruction_budget` 被 clamp 到 host max 20M——**提额无路，只能降耗**。）

### 2. AI 改期回调崩溃（评审点②漏网）——根治

`ai_verify()` 对模型输出的 number 误调 `.to_f64()`（rc.6 的 `parse_json` 已把 JSON
integer 解析为 number，再调报 "method to_f64 not found on number"），「请模型给方案」
回调必崩、方案区空白。修复：直取 number（`p.start` / `p.end`）。
改期链路回验：过闸方案（`20261004 09:00-10:00`）正常构建显示。

### 3. AI 排程可选字段崩溃——根治

宿主构造的 `model.complete` 输出对象**读缺失键直接抛** "property not found in
prototype chain"（与 parse_json 对象行为不同）。模型对可选字段会真省
（如「一小时」无提醒需求 → 省 `reminder_minutes`），回调无条件读 → 崩溃、面板停在「解析中」。
修复：`reminder_minutes` / `participants` / `location` 列入 schema `required`
（缺失 = 宿主 schema 校验失败 → 走 `!r.is_ok` 干净失败路，不再炸回调）；提示词补 location 指引。
回验：原必崩输入「后天上午十点项目评审，一小时」→「项目评审 2026-10-24 10:00-11:00」请确认，无新 `[E]`。

### 4. AI 超时

`AI_TIMEOUT_SEC` 12s → 30s（Minimax 改期任务实测 12–15s；方案本可迟到送达，
12s 时 UI 先闪「无响应」）。

### 5. mail 契约（评审点③）——根治

1. `mail.list` 先经 `mail.accounts` 取 `r.data[0].id`，再 `mail.list {account, limit}`
   （此前直传报 "There is no such account"）。
2. 发件人字段名 `from` → `sender`（rc.6 mail.list 契约字段）。
3. mail.list 消息无 `date` 字段（契约 = id/subject/sender/address/time/preview/unread），
   改传空串回退主题解析日期。
4. rc.6 邮件账户**按 app 授权**（`.host/mail/accounts.json` 的 `apps` 数组，不含调用方则
   `mail.accounts` 返回空）；第三方应用的授权弹窗入口在 rc.6 未观察到（开放问题）。

### 6. 邮件预览数据安全（实机新发现，高危）

`add_mail_preview()` 在 `merged` 为空时只 push 邮件事件，而 `confirm_import()` 是
`events = merged` **全量替换**——点「写入」会把事件库冲成只剩这一条（实测 5 → 1）。
修复：先以事件库为底逐条拷入再追加，与 ICS 导入合并语义对齐（回验：3 → 4 事件完整保留）。

### 7. Splash 引擎适配

- 正则不支持 `\s`（全库仅 2 处在用，整条匹配失败）；
- `.exec()` 捕获分组在该引擎取不到（邮件事件全落默认值）；
- `search` 返回**字节**下标、`substr` 按**字符**切（中文串混用必炸）；
- `ok` / `me` / `self` / `scope` 是保留字，不能当变量名。
→ 邮件日期/时间解析弃用 regex，改 `to_chars()` **码点扫描**（与 ICS 解析同款原语）；
  支持「15:00」「2026-10-23」「10 月 23 日」（含任意空格）三种形态，全角冒号兼收。

### 8. 字段完整性

- `reschedule()` 重建字面量写齐 `d8*` 七字段（writepoint 门禁④；此前只靠 `event_finish`
  事后补，文本缺席）。
- `save_new()` 补 `event_finish(ev)`（v0.5.9 起漏调；v0.5.10 月缓存改读 `ev.d8` 后
  手工事件在格子热度 / 圆点 / 「最近日程」里全隐身——run_new 三红）。
- 重复事件**原发日**不再被「精确命中 + 重复展开」双重计数（热度档位正确，
  「妈妈生日」格底色 #fef8f4 而非 #fcecdf）。

### 9. 工程治理

- `ipart` / `pad2` 定义挪到 `d8_*` 之前（deps 门禁建树前向引用 5 → 0）。
- 关于页版本号与 manifest 单源（version_gate 绿）。
- 测试夹具 `tools/featflow.py` 兼容数组化数据表（`let NAME_ARR = [...]`，空首元素还原 leading pipe）。
- rc.6 宿主日志落点改 `.runtime/`（portability 门禁绿，`RC6_LOG` 环境变量可覆盖）。
- 新增 `tools/run_e2e_rc6.sh`（官方宿主 E2E：存储干净 / 导入 / 解析 / 写入 / 列表 / 翻月与节日切换 / 导出 / 清空）。

## 三、验证结果（全部实机）

| 宿主 | 结果 |
|---|---|
| card-host 全量回归（`run_all.sh` 9 套件串行） | **9/9 PASS**（静态 14 道门禁全绿；日志 `/tmp/run_all_fix4.log`） |
| 官方 OctoSense 0.1.0-rc.6 E2E（`run_e2e_rc6.sh`） | **10/11**，宿主 `[E]` = **0** |
| rc.6 boot 指令预算（3 个 eval epoch 含天气 re-eval） | **[E] = 0** |
| rc.6 AI 排程（Minimax `MiniMax-M3.1-Flash`） | 草稿 → 确认 → 写入全通（含原必崩用例） |
| rc.6 AI 改期（冲突 → 请模型给方案） | 回调 + 七道闸正常，过闸方案正常构建 |
| rc.6 邮件全链（真实 Gmail 账户） | accounts → list → 候选 → 预览 → 写入全通 |

> rc.6 套件唯一一红「翻月未稳定」：官方桌面宿主对 `animating=true` 的卡片**每帧连续重绘**，
> 测试夹具「连续 0.3s 帧指纹一致」的判稳条件在此环境天然不成立（同一断言在 card-host 上通过）。
> 翻月本身功能正确（月份、节日标记、天气图标、补班字全部实测到位）——**非应用缺陷**。

## 四、不变式

`reschedule()` 唯一写入点；七道闸判定逐字未动（`test_ai_gates.py --sync` 通过）；
ICS 往返 `新增 0 / 改期 0 / 跳过 N` 仍成立；全天事件仍不参与自动改期；
权限声明（`storage` + `net` 两域 + `model` + `mail`）零新增。

## 五、已知边界（如实记录）

- **AI 改期 30s 超时仍可能 < 个别慢响应**：方案可迟到送达，但 UI 会先显示规则建议兜底（不阻断）。
- **第三方应用邮件授权入口未观察到**：rc.6 邮件账户按 app 授权，第三方应用如何触发授权弹窗
  （或设置项）未见文档；本次验证用账户系手工加入授权列表后完成。
- **rc.6 桌面多窗口环境**：App Hub 等模块与日历并存时，`/snap` 快照混有双方节点，
  测试驱动需先保证目标模块在前台（本次回归流程已内置该步骤）。
