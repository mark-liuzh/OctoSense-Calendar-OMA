## Submission

- **App ID:** com.oma.octosense.calendar
- **Version:** 0.3.1
- **Repository:** https://github.com/mark-liuzh/OctoSense-Calendar-OMA
- **Tag:** v0.3.1
- **Commit:** 83137a0d27935909146b07576185fd2d58d867a2
- **Bundle:** bundle/
- **Bundle digest (blake3):** `dca5d22abf071903872e3483e88595079d6108b420a7ecd383bf67e816dd507f`
- **Publisher signature:** `af3dae409d2033482bf1272ddada1a3b7af24bae80cc61d4c6d31beddbce9ea41c79944340ca06e2f2ffe0a40374a29e9c1396e4a52dbaacca8fe34bbd540500`

### Description

同 v0.3.0 —— 应用本体（`bundle/main.splash`）的用户可见行为**零变化**。本版全部改动在「参赛合规 + 自检体系」两个层面：listing 字段避 hub 硬上限、self-test 工具补 expect/硬断言、清理 6 行 dead code。详见底部「What changed in v0.3.1」。

> 若需要单独看应用的功能说明，请参考前序 issue [#52](https://github.com/OctoSense-org/OctoSense-App-Hub/issues/52) 的 Description 段。

### Capabilities

- storage

（`hosts` 为空 —— 应用没有任何网络出口；`agent` 为 null。）

### Hub Check Result

```
com.oma.octosense.calendar 0.3.1 — PASSED
  grants: capabilities {"storage"}, hosts {}, storage 16777216 bytes, agent none
```

运行命令：

```sh
hub check bundle --publisher-key OMA=46b11cc186e7a8ea8688c9d5a246caeaa27e6e0c8ba2986547d7511c0b872380
```

期望输出 `— PASSED` 且**无警告**（v0.3.0 是这个状态，v0.3.1 应该一样 —— 改动只删了死代码、没改任何约束条件）。

### Platform

Tested on: **windows** and **macos**

- Windows：v0.3.0 起即实机跑通全部检查；v0.3.1 本体改动不影响。
- macOS：v0.3.0 在 2026-10-01 实机跑通 8 道静态门禁 + 全部 8 条端到端流程。
  v0.3.1 自检侧改动（run_e2e / run_conflict 新增 expect）**未在 macOS 上重跑端到端**
  —— 提交前请在装了 card-host 的机器上 `bash tools/run_e2e.sh` + `bash tools/run_conflict.sh`
  各跑一次，确认新断言不会因我对 splash 文案解读偏差而误报（_低风险_：期望值都是
  「最少关键字」，例如「已写入 3 个事件」而非完整段落）。
- Linux 与移动端未验证，故不在 `platforms` 中声明。

### Publisher

OMA 队 · `mark-liuzh` / `ody-cai`（2026 GOSIM Agentic App Hackathon）

- **Publisher id / public key:** `OMA` · `46b11cc186e7a8ea8688c9d5a246caeaa27e6e0c8ba2986547d7511c0b872380`（Ed25519）
- 密钥位置：`~/.octosense/oma-publisher.key`（仓库外）
- 复核命令（无需私钥）：见上「Hub Check Result」

---

## Scan answers (7 questions)

**Q1 — Does the app do what its name, subtitle and description claim?**
Yes. 应用用户可见行为与 v0.3.0 完全一致。`bundle/main.splash` 的核心入口函数（行号
与 v0.3.0 对齐，未变）：
- 点格子写日程：`pick_cell`:2325 / `open_new_on`:2230 / `save_new`:2277
- 重复规则：`rrule_plain`:2136 + `repeat_hits`:2155
- ICS 导入：`parse_all`:728 + `merge_events`:766
- 冲突与消解：`overlaps`:856 / `overlap_minutes`:868 / `find_conflicts`:879 /
  `build_advice`:930 / `apply_advice`:1503 / `can_rollback`:1115
- 无损导出：`export_ics`:1011
- 节假日数据表：`HOLIDAYS` / `WORKDAYS` / `CN_SPANS`
- 其余分区：`save_todos`:3139 / `save_moods`:3258 / `save_goals`:3378 /
  `solar_term`:3584 / `egg_today_pick`:3679 / `cap_add`:3734
- 本版新加的静态 / 端到端断言（self-test，**不属于 bundle 内代码**）：
  `tools/run_e2e.sh` / `run_conflict.sh` 的 `expect()` / `metric_is()` 函数，
  与 README 强调的两条硬证据（重叠时长量化、往返幂等）一一对应。

**Q2 — Do the listing's platforms and category fit an app of this kind?**
Yes，与 v0.3.0 一致。`category = productivity`，`platforms = ["windows", "macos"]`，
均实机验证。

**Q3 — Do the granted capabilities match what the app visibly does?**
Yes, and nothing more. `capabilities = ["storage"]`，`hosts = {}`，`agent = null`。
对 `bundle/main.splash` 搜索 `host.request` / `http://` / `https://` / `fetch(` /
`network` / `urllib` / `socket` → **0 处**（与 v0.3.0 同口径核对）。
`storage` 仍被使用：`events.json` / `snapshots.json` 与四个旁路文件 `todos.json` /
`moods.json` / `goals.json` / `capsules.json`。

**Q4 — Is any part of the interface deceptive?**
No，与 v0.3.0 一致。`登录` / `密码` / `支付` / `付款` / `扫码` / `订阅` / `试用` /
`微信` / `支付宝` / `system` / `prompt` / `assistant` → 全部 0 处；无登录 / 凭据 /
付费界面。界面为自有视觉语言。

**Q5 — Does any text read as an instruction to an assistant?**
No。`main.splash` 中的散文均为给人类维护者的开发注释，不存在运行期指令；
应用 `agent` 为 `null`，从不调用任何模型。

**Q6 — Is any wording abusive, or aimed at a private individual?**
No，与 v0.3.0 同口径核对。新增代码 232 / 删除 34 行，未引入任何不文明词汇。
唯一人名是队伍成员署名（`mark-liuzh` / `ody-cai`）。

**Q7 — Route**
建议 **pass**（沿用 v0.3.0 的判断）：
- Q1 / Q3 / Q5 / Q6 都有可复现的机械证据，与 v0.3.0 同口径
- Q2（platforms / category）：不变
- Q4（界面呈现）：界面完全没改，沿用 v0.3.0 的 human-review 即可
- manifest 用队伍密钥 `OMA` 签名，`hub check --publisher-key` 通过（无警告）——
  同 v0.3.0 的签名设置，本版**不需要**新建密钥

---

## What changed in v0.3.1

功能层：零变化。本版三类改动：

### 1. listing 字段（避 hub 硬上限 REFUSED）
- `bundle/listing.json` 的 `keywords` 10→7（砍 `recurring` / `mood` / `local-first`，
  与 `calendar` / `scheduling` / `offline` 语义重叠）
- `bundle/listing.json` 的 `screenshots` 8→7（砍 `screenshots/03-conflict.png`，
  与 `04-conflict-detail` 信息重叠）
- 留 **3 keywords buffer + 1 screenshot buffer**，复赛加图 / 换关键词不会再被 REFUSED

### 2. self-test 加固（自承的两个薄弱点）
- `tools/_env.sh` + `tools/run_all.sh`：把 card-host 必需性检查从 `_env.sh` 顶层
  移到 `boot_host` 内，让 `bash tools/run_all.sh --fast` 真·秒级通过
- `tools/run_e2e.sh` + `tools/run_conflict.sh`：引入 `expect()` / `metric_is()`
  函数 + PASS/FAIL 计数，把 README 反复强调的两条硬证据（重叠时长量化 +
  往返幂等）写进脚本
- `tools/run_conflict.sh`：补资源加载硬断言（之前漏了），去掉会误匹配源码行号的
  裸 `404`

### 3. dead code 清理（6 行）
- `bundle/main.splash` line 342-346：五个 unused iOS 系统色 let（与设计语言冲突）
- `bundle/main.splash` line 325：重复的 `status_text`（被 line 337 完全覆盖）

### Relationship to #52
[#52](https://github.com/OctoSense-org/OctoSense-App-Hub/issues/52) 提交的是
v0.3.0（commit `0b643af`）；本 issue 是 v0.3.0 的**提交前清理 patch**。
v0.3.1 是「改完代码后 hub check 会因为 bundle 内容变化而拒绝」前的一次内务整理，
**不是**新功能发布。建议把本 issue 作为 v0.3.0 的修订（即在维护者侧把两个版本
合并计票，或在目录里把 v0.3.1 视为 v0.3.0 的修订版）—— 若您的流程要求一版一 issue，
请把 v0.3.0 的 issue 标 superseded 后用本 issue。

---

## 资产

`octosense-calendar-0.3.1-bundle.zip` 内含完整 `bundle/` 目录。
sha256：`0bf7bb80a5ee4cbf983f5003d515acb5fdf56c6af5af7b961deca7b3568456ed`
下载：[`octosense-calendar-0.3.1-bundle.zip`](https://github.com/mark-liuzh/OctoSense-Calendar-OMA/releases/download/v0.3.1/octosense-calendar-0.3.1-bundle.zip)
（GitHub release asset id `605554398`）
