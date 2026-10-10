# OctoSense 日历 v0.5.0

**2026 GOSIM Agentic App Hackathon · 队伍 OMA**（成员 `mark-liuzh`、`ody-cai`）

> 按初赛评委（ZhangHanDong，issue #77 comment）四条建议逐条处置。
> 第1 条是主要失分点 —— **接入了 `model.complete`，让模型真正参与改期**；
> 其余三条是权限口径与界面标注的收紧。
>
> 一句话概括这个版本的取向：**模型参与决策，但决定权不在模型手里。**

---

## 一、评委四条建议的处置

| # | 评委原话要点 | 处置 |
| --- | --- | --- |
| 1 | 「本作品没有任何 Agent/模型调用，按细则『需求与任务价值』上限 13 分是主要失分处；可以考虑接入 `model.complete` 做冲突消解建议」 | **接入 `model.complete`，模型参与改期**（详见 §2） |
| 2 | README 权限节先引宿主「Never contacts the network」再说明申请了 `net`，顺序易误读 | README 已调换为先陈述自己的口径、再引用宿主原话，并说明该原话只适用于 `storage` |
| 3 | `geocoding-api.open-meteo.com` 已声明但代码未使用 | **从 `network.hosts` 移除**（实测代码零引用）。`archive-api.open-meteo.com` 同理一并移除 —— 三个域收成`api.open-meteo.com` 一个 |
| 4 | 天气坐标硬编码北京，至少在界面标注 | 「翻到任意一天 · 自动联网天气」改为「**翻到任意一天 · 天气按北京**」 |

评委正面认定的三点继续保留并作为答辩支撑：闭环完整 + 八条端到端脚本、
网络权限最小化（断网保留上次缓存）、节气用 Meeus 算法实算且超范围降级为「≈」。

---

## 二、核心变化：模型参与改期

### 为什么现在能做

初赛时 `model` 能力尚未在宿主落地。**OctoSense `desktop-v0.1.0-rc.2`（2026-10-09）**
起这条路径真正可用：

- 它锁定的 App Hub `95e4831` 的 `KNOWN_CAPABILITIES` 含 `model`；
- `native-apps.json` 里 apphub 的 `implies` 含 `octosense-ai-host/llm`，
  `crates/ai-host/src/lib.rs:428` 确实调用 `register_model(...)`。

⚠️ 官方文档 `AI-SERVICES.zh-CN.md` 里「即将推出 / 暂时不要让提交依赖它」的说法
截至 2026-09-27，**现已过期**。

### 设计立场：模型输出是**不可信输入**，不是结论

规则引擎（`commitment_weight` + `propose_slot`）仍然先算出一份方案；
模型可以在此基础上**改主意**，提出自己的时段。但模型给的东西必须穿过
**七道闸**才允许写进事件库：

| 闸 | 拦什么 | 为什么必须有 |
| --- | --- | --- |
| 1 形状 | 字段齐、类型对、时长为正 | schema 只保证「形状」 |
| 2 身份 | 只能动规则引擎判定「可动」的那条，不许换人 | 硬承诺（标题含截止/deadline/答辩）必须被保留 |
| 3 日期 | 8 位、真实存在的日历日、偏移 −1..+7 天 | 防止模型把会议甩到几个月后 |
| 4 时段 | 起点<终点、不跨 24:00、对齐整分 | 半个钟点的时段无法写回 ICS |
| 5 日历 | 不撞**任何**事件（含跨天与全天） | **schema 保证不了「这个时段真的空着」** |
| 6 同意 | 用户点「采纳并改期」才写 | 模型不能自己落地 |
| 7 复核 | 写入后重扫；冲突没减少则自动 `undo_last()` 回滚 | 不留「改了但没用」的状态 |

任何一道不过 → 当场回退到规则引擎的方案，**界面上明说被哪道闸拦下**，不静默。

### 唯一写入点

`reschedule(uid, day, slot_start, slot_end)` —— 从 `apply_advice` 里抽出的唯一写入函数，
规则引擎（`apply_advice`）与模型（`apply_model_plan`）**共用**。

两处各写一遍 `events[k] = {...}` 迟早漂移：某天修了 `start_utc` 的 `Z` 后缀只改一处，
**往返无损立刻回归**（导出再导入报「改期 N」而不是 0）。

模型只能改变「挪到哪个时段」，碰不到 DTSTART 的类型后缀、`TZID`、`EXDATE/RDATE`
—— 那些字段由 `reschedule()` 一律沿用原值。这是往返无损在本版本仍然成立的根本原因。

### 隐私口径

只有用户点「请模型给方案」时，才把**这一条冲突**的标题与时长发给用户自己配置的
AI 提供方。地点、描述、参与人、附件一律不送。发什么、不发什么，写在应用界面上，
不只写在 README。

### 不可用是正常状态

宿主可能没有注册模型服务、或用户没有配置 provider。因此 `host.request` 的失败分支
必须完整降级：应用侧起一个 12 秒的 `start_timeout` 兜底（宿主超时由它自己计时，
**回调是否回来没有保证**），超时或失败都退回规则建议，界面其余部分一字不变。

---

## 三、权限变化

| 能力 | v0.4.1 | v0.5.0 |
| --- | --- | --- |
| `storage` | ✓ | ✓ |
| `net` | ✓ | ✓ |
| `model` | — | ✓ **新增** |
| `network.hosts` | 3 个 open-meteo 域 | **1 个**（`api.open-meteo.com`） |

宿主实测授予：`capabilities {"model", "net", "storage"}`，`hosts {"api.open-meteo.com"}`。

---

## 四、验证

| 项 | 结果 |
| --- | --- |
| 静态门禁（brace / quotes / toplevel / deps / paintfix / btnfocus / cellhover / fncalls / **ai_gates**） | 全过 |
| 七道闸判定夹具 `tools/test_ai_gates.py` | **38/38**，且 13 条拒绝理由与 `ai_verify` 逐字一致 |
| `tools/run_conflict.sh` 全量回归 | **21/21 PASS**，宿主编译/运行错误 **0** |
| 对照基线（v0.4.1 剥签名副本） | 21/21（证明 21 是全量） |
| **ICS 往返无损**（AI 区存在时） | **新增 0 / 改期 0 / 跳过 4** |
| 视口 | AI 区两个按钮 `y=758`，`758+25=783 < 892`，未被裁 |
| 模型不可用的降级 | 立即失败 ✓ · 12 秒超时 ✓ · 超时不覆盖已有结论 ✓ |
| `hub check --publisher-key` | `PASSED`，无警告 |

### 已知未验证项

**`model.complete` 的成功路径尚未验证。** 本机 `card-host` 不注册该服务，
真机验证又要求本版本先提交进 App Hub 商店才能安装。本版本已具备提交条件，
成功路径待商店侧受理后在真机补验（届时需配置 AI provider）。

已能持续验证的是七道闸的判定逻辑 —— 它是成功路径中唯一能在本机覆盖的部分，
已做成常驻门禁（`static_gate` 的第九道）。

---

## 五、本轮踩到的三个宿主坑（已写进 `AGENTS.md`）

1. **Splash 不支持三元表达式 `?:`** —— 会被解析器误识别为「named arg」，
   报 `Expected )`。⚠️ `brace.py` / `quotes.py` **抓不到**（括号确实配平），
   只有真跑宿主才炸。`main.splash:6062` 早有这条注释，本轮还是又踩了一次。
2. **`Label` 没有 `render()` 方法** —— 调用报 `widget method render not found`
   并**静默中断该回调后面的所有语句**（本轮因此让 `start_timeout` 压根没执行）。
   ⇒ 回调里没生效时，先查宿主日志有没有 `[E] splash`。
3. **`card-host` 不注册 `model` 服务** —— `host.request` 既不立刻回失败也不回调
   （实测卡住 15 秒）⇒ 应用侧必须自己兜超时。

---

## 六、发布件

| 项 | 值 |
| --- | --- |
| App ID | `com.oma.octosense.calendar` |
| Version | `0.5.0` |
| Tag | `v0.5.0` |
| Bundle blake3 | 见 `bundle/manifest.json` 的 `integrity.bundle_blake3` |
| Publisher key id | `OMA`（Ed25519，沿用 v0.4.1 的同一把钥匙） |
| 复核命令 | `hub check bundle --publisher-key OMA=<pubkey>` |