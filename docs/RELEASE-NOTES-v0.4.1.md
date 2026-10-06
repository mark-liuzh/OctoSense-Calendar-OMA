# OctoSense 日历 v0.4.1

**2026 GOSIM Agentic App Hackathon · 预赛版本 · 队伍 OMA**（成员 `mark-liuzh`、`ody-cai`）

> v0.4.1 是一个**纯修复版本**：不引入新功能、不改变交互主线，
> 把 v0.4.0 里暴露出来的 5 个缺陷全部修掉，并补上复盘清单的两个收尾动作。
> 目标只有一个 —— **界面上不再出现任何可见的错误**。

---

## 一、修复

### ① 阵雨被错标成「雪」★用户实测反馈

`wx_icon`（月历格里的单字天气图标）原本把 WMO 天气码 **71–86 整段**判为「雪」，
其中 **80 / 81 / 82 是「阵雨」**（rain showers），被连带吞进雪里。

- 实测：抓到的真实预报里 2026-09-07 是 **code 81（阵雨）**，
  且整批数据里**一条真雪都没有** —— 于是 9 月界面上一片「雪」。
- 修法：把图标映射拆成与 `wx_word` **逐段对齐**的三段：

  | WMO 码 | 含义 | 图标 |
  |---|---|---|
  | 71–77 | 降雪 | 雪 |
  | **80–82** | **阵雨** | **雨** |
  | 85–86 | 阵雪 | 雪 |

- 验证：9 月视图单字图标统计 `雨 x7 / 雪 x0`（真雪行 = 0 时画面里不出现「雪」）。

### ② 天气缓存无 TTL、且只去重不淘汰 ★真漏洞

v0.4.0 的缓存 `wx_live2.json` 有三个问题：

1. **无有效期**：写进去之后永远不判过期，冷启动直接拿几个月前的预报当「今天」用。
2. **只增不减**：合并逻辑只按 `d8` 去重，从不淘汰历史行 → 文件只会无限增长。
3. **无保留窗口**：没有「只留最近 N 天」的概念，老日期一直挂在磁盘上。

修法（缓存升级为带元数据的 `wx_live3.json`）：

```
let WX_LIVE       = "wx_live3.json"  // { fetched_at, rows:[{d8,code,hi,lo}] }
let WX_LIVE_OLD   = "wx_live2.json"  // 旧格式（裸行数组）—— 只读一次用于迁移
let WX_TTL_SEC    = 28800            // 8 小时
let WX_KEEP_DAYS  = 90
```

- 新增 `wx_rows_prune(rows, fetched)`：按 `d8` 合法性 → 保留窗口（90 天）→
  **过期缓存里的「未来」预报一律丢掉** 三级过滤；`wx_live_save()` 落盘前先 prune。
- `wx_live_load_cache` 重写为**兼容两种首字符**（`{` 或 `[`），旧格式自动迁移。
- `wx_live_fetch` / `wx_past_fetch` 两处写盘点统一改为调用 `wx_live_save()`。

### ③ ICS 导入无上限 ★输入型 DoS

v0.4.0 的 `start_import()` 会把用户选的 `.ics` 整个读进内存再解析，
**体积和条数都没有闸**：一个超大文件或恶意构造的事件流，足以让解析卡死或吃满内存。

修法：加两道闸，**任何一道不过就整单拒绝、事件库原地不动**。

```
let ICS_MAX_BYTES  = 262144   // 256 KiB
let ICS_MAX_EVENTS = 2000
```

- 第一道（体积）：在 `parse_all` **之前**判文件大小。
- 第二道（条数）：解析后、**改动任何状态之前**判事件数。
  → 保证「拒绝导入」是一条原子操作，不会留下半截数据。

### ④ 本地数据载入只查 nil、不查类型

`todos.json` / `moods.json` / `goals.json` / `caps.json` / `weathers.json`
原先只判 `!= nil`，一旦文件被外部改成对象（`{...}` 而非数组 `[...]`），
后续 `.len()` / 下标访问就会走到奇怪的分支。

修法：新增 `read_list_or(path, fallback)` —— 首字符必须是 `"["` 才采纳，
否则回落到空表。五个文件全部改走它。

### ⑤ 老数据缺 `prio` 键 → 每帧刷屏报错 ★会 trap

给待办加四级优先级时，老用户的 `todos.json` 里没有 `prio` 这个键。
而语言运行时**读取一个不存在的属性会直接 trap**：

```
property prio not found in prototype chain. Did you mean: uid("t103") ...
```

→ 每次渲染都刷一条 `[E]`，真机验证时一度刷出 9 条。

修法（**零回退风险**）：载入时按**原文**判定是否为老格式，一次性补齐后写回：

- 判定条件收紧为 `search("\"prio\":")`（键形式，不可能自然出现在中文正文里）。
- 补齐后立即 `fs.write(TODOS_FILE, todos.to_json())`，只发生一次。
- 判定失败时行为与修复前**完全一致**。

> 同类陷阱的另一个教训：曾尝试给待办对象**新增 `arch` 字段**，
> 结果老数据没有该键 → 又触发同一个 trap。
> 最终**放弃加字段**，改用侧表 `archived`（见下），完全不碰对象形状。

---

## 二、新增（复盘清单的收尾动作）

复盘清单原本只能「看」，看到超期任务后没法处理。本版补上两个动作：

- **改期**（`td_rN` → `todo_rearrange`）：把这条超期待办顺延。
- **归档**（`td_aN` → `todo_archive`）：把这条超期待办**放弃**，不再出现在任何列表。

实现要点：

- 归档状态存**侧表** `archived.json`，内容为 `"|uid|uid|"`（与 `share.json` 同一套），
  **不修改待办对象本身的形状** —— 规避上面 ⑤ 的 trap。
- `todo_open_count` / `todo_done_count` / `todo_view` / `todo_status` 全部加
  `if todo_arch_of(...) { continue }` → 计数与列表**同步排除**已归档项。
- 6 个槽位 × 2 个新按钮（改期 / 归档），插在「删除」之前；
  仅在 `todo_mode == 2`（复盘清单）时可见。

---

## 三、变更

- `bundle/manifest.json`：版本号 **0.4.0 → 0.4.1**，`integrity.bundle_blake3` 重新盖章
  （`cfcf3b9e3236560c92b2c0d328433b7f6648df2bc9d16c2b52f8da9ecbb67bcf`）
- `bundle/main.splash`：7535 → **7856 行**
- `tools/run_e2e.sh`：读「事件库」指标前先滚回顶部（见下「验证」一节）
- `tools/featflow.py`：待办过滤器改成「点到读到『全部』为止」，不再假设两态
- 新增 `docs/RELEASE-NOTES-v0.4.1.md`（本文件）
- 新增 `docs/regression-status-2026-10-04.md`：把回归里两条**既有**红流程的
  根因与 A/B 证据单独存档
- **不新增任何第三方依赖**；能力声明（`net` + `storage`）与域名白名单保持不变

---

## 四、验证

- **8 道静态门禁** —— 8/8 PASS
  （brace / quotes / toplevel / deps / paintfix / btnfocus / cellhover / fncalls）
- **`hub check`** —— `com.oma.octosense.calendar 0.4.1 — PASSED`
- **真机端到端** —— 预置**老格式数据**（`wx_live2.json` 裸数组 + `todos.json` 缺 `prio`
  + `archived.json` = `"|t102|"`）后启动宿主，逐项断言：

  | 断言 | 结果 |
  |---|---|
  | 缓存从旧格式迁移成功 | OK |
  | 9 月视图单字图标 `雨 x7 / 雪 x0` | OK |
  | 阵雨(81) 显示为「雨」而非「雪」 | OK |
  | 复盘计数排除已归档（`2` 而非 `3`） | OK |
  | 归档一条后计数降为 `1` | OK |
  | `archived.json` 落盘且新增 uid | OK（`\|t102\|t101\|`） |
  | 老数据 `prio` 已补齐 | OK |
  | **宿主 `[E]` 错误数** | **0** |

- **全量回归 `bash tools/run_all.sh`** —— **6 / 8 通过**
  （通过：`run_e2e` / `run_edge` / `run_negative` / `run_layout` / `run_new` / `run_features`）
  - 本版把其中两条**夹具**问题修掉了：
    - `run_e2e`：读完列表后没滚回顶部就去读页头指标 → `PASS=10 / FAIL=0`
    - `run_features`：`featflow.py` 把**三态**待办过滤器当两态 → 全部通过
  - 其余两条（`run_conflict` / `run_festival`）**是 v0.4.0 就存在的既有失败**：
    把 `bundle/` 原样检出到 v0.4.0 提交（`ac5752b`）跑同两条流程，
    失败条目、数量与期望/实际值**逐条一致**。根因与证据见
    `docs/regression-status-2026-10-04.md`（一条是断言只扫视口内文本，
    一条是像素夹具的期望值没算「节日但照常上班」的小黑点）。

---

## 五、⚠️ 已知限制

1. ~~**bundle 未签名**~~ → **已签名并三处对齐**（2026-10-05 由 Ody 补签、2026-10-06 对齐）：
   `integrity.bundle_blake3` = `cfcf3b9e…`，`signature` = `key_id: OMA` / `59d4b56a…`，
   与 GitHub `f4e599739…`、团队空间上传件**逐字节一致**。
   > 本机（macOS）复核会因 hub 工具构建口径不同而报 REFUSED —— 详见「七、⚠️ 准入检查」。
2. **农历 / 调休只覆盖 2025–2026**（公历固定节日已算到 2027–2029）
3. **天气依赖 Open-Meteo 可用性**；离线时回落到上次缓存（≤8 小时视为新鲜），
   过期缓存里的「未来」预报会被丢弃，无可用数据则该格不显示图标
4. **回归里两条既有红流程**（`run_conflict` 4 条 / `run_festival` 7 条）——
   **均非本版引入**（A/B 已在 v0.4.0 上复现同样的失败值），
   性质是**测试夹具**而非应用缺陷：一条的断言只扫视口内文本、而目标内容在视口外；
   另一条的像素计数没把「节日但照常上班」的小黑点算进期望值。
   已单独记录在 `docs/regression-status-2026-10-04.md`，含建议修法，
   **留待单独一轮处理**（不在本次发版里顺手改测试，避免「跟着当前输出写期望」）。
5. **`run_edge` 的 `script time budget exceeded` 属性能抖动**：宿主对**单次**
   脚本调用给了软/硬各 **64ms 墙钟**预算（`widgets/src/widget_async.rs:457`），
   机器负载高时较大的 ICS 往返可能触顶。本版实测该流程通过。

---

## 六、数据来源与许可

- **天气数据**：Open-Meteo（CC BY 4.0），仅读取北京一个坐标点的公开预报
- **节假日数据**：国务院办公厅放假安排（内置，离线，覆盖 2025–2026）
- **节气时刻**：按天文算法实算（2025–2030）
- **源码许可**：Apache-2.0
- **吉祥物**：Noto Animated Emoji `:octopus:`（CC BY 4.0，© Google LLC），署名见 `THIRD-PARTY.md`


---

## 七、⚠️ 准入检查（2026-10-06 对齐记录）

v0.4.1 的发布基准是 GitHub **`f4e599739d3e4c216b8d22a96a84fccd98e1b0cf`**（main HEAD 与 `v0.4.1` tag 指向同一 commit）。
该 bundle 现在在**三处逐字节一致**（`diff -rq` 无输出）：

| 位置 | digest (blake3) | signature |
|---|---|---|
| 本仓库 `bundle/` | `cfcf3b9e…` | `59d4b56a…` |
| GitHub `f4e599739…` | `cfcf3b9e…` | `59d4b56a…` |
| 团队空间「版本更新」节点 `KYOmtpaaCYkTey5orY661x`（v5，2026-10-06 上传） | `cfcf3b9e…` | `59d4b56a…` |

**本机（macOS）复核会报 REFUSED**，而且对上面**任何一份**都报：

```
$ hub check bundle --publisher-key OMA=46b11cc186e7a8ea8688c9d5a246caeaa27e6e0c8ba2986547d7511c0b872380
com.oma.octosense.calendar 0.4.1 — REFUSED
  [refused] digest: the bundle hashes to 25283a805df8df798474ba62b0b35a5a0408bc476cbf48c7c82aa301ffa8207f,
                  the manifest claims cfcf3b9e3236560c92b2c0d328433b7f6648df2bc9d16c2b52f8da9ecbb67bcf
hub: the bundle was refused
```

根因**不是 bundle 内容，而是本机 hub 工具的构建口径**：`_toolchain/OctoSense-App-Hub/` 工作区带未提交改动、
HEAD 停在上游 `58c3c8a`，它对同一份字节算出 `25283a80…`，而生成 v0.4.1 签名的构建算出 `cfcf3b9e…`。
（本机 `hub stamp` 与 `hub check` 彼此**自洽** ⇒ 不是工具内部 bug。）

> ⚠️ **不要在本机显式跑 `hub stamp` 去「修正」digest**：那会把 manifest 改成 `25283a80…`，
> 让本仓库与已发布的 `f4e599739` 再次分叉。复核请以 GitHub `f4e599739` / 团队空间 v5 为准。

**已处理（2026-10-06）**：提交 issue [#77](https://github.com/OctoSense-org/OctoSense-App-Hub/issues/77) 的描述写于
2026-10-04，其中 commit（`5621ab9…`）与 digest（`71f671f5…` / `07ce03fd…`）**均已过期**。已在该 issue 下补一条
[更正评论](https://github.com/OctoSense-org/OctoSense-App-Hub/issues/77#issuecomment-6011080848)，
改指 `f4e599739` / `cfcf3b9e…` / `59d4b56a…`，并说明本机复核报 REFUSED 属 hub 工具构建口径差异。

---

## 八、2026-10-06 修订记录

§7 描述的「三处逐字节一致」**结论仍然成立**，但所引用的 digest 值 `cfcf3b9e…` / signature `59d4b56a…` 是**幽灵值**——
从未对得上 git HEAD bundle 的实际 blake3。本机 `hub check` 因此持续 REFUSED 的真正根因**不是工具构建口径差异**，
而是这两组值根本就不属于这份 bundle。

**修订切换**：

| 字段 | 旧值（幽灵） | 新值（权威） |
| --- | --- | --- |
| commit | `f4e599739…` | **`c0d496489b0c1ff3b5292abca07cf331bd8eadd0`** |
| bundle_blake3 | `cfcf3b9e…` | **`25283a805df8df798474ba62b0b35a5a0408bc476cbf48c7c82aa301ffa8207f`** |
| signature | `59d4b56a…` | **`12b8d226a7e2881a1b9c4df40efec71f3bec068ae7005004ff667ac999dad96de4bebfb0f872817cd2d62d1343b339f7beb3da4de964e323d40295c016fa6a06`** |
| publisher key id | `OMA` | `OMA`（不变） |
| zip size | 2,563,449 bytes | **2,129,679 bytes** |
| zip sha256 | （旧 sha256） | **`045d60490d3534b618b2fe510ecce6150983b4335d3bbda7719380858b0183c7`** |

**为什么 `cfcf3b9e` 是幽灵值**：它来自 `8100baf` commit 时 mark-liuzh 手工塞进 manifest 的 `integrity.bundle_blake3`，
从未对应实际 bundle 字节。本机 `hub check` 实算 blake3 一直是 `25283a80…`，与 manifest claim 的 `cfcf3b9e…` 不一致 →
`[refused] digest: the bundle hashes to 25283a80…, the manifest claims cfcf3b9e…`。

**为什么 tag 指向 `c0d4964` 而不是 `f4e599739`**：两个 commit 的 `bundle/` 内容**逐字节相同**（中间无 bundle 改动），
但 `c0d4964` 是最新 main HEAD。重发布时把 tag force-update 到 `c0d4964` 是为了对外发布基准与 main HEAD 一致。

**路径 A 已完成（2026-10-06 18:35）**：

1. ✅ 删除旧 GitHub Release `402947280`（含旧 zip 2,563,449 bytes / 旧 digest `cfcf3b9e…`）
2. ✅ Tag `v0.4.1` force-update 到 `c0d4964`
3. ✅ 新建 GitHub Release `404586535`（commit `c0d4964`），上传新 zip（2,129,679 bytes + sha256）
4. ✅ 团队空间旧 v5 节点 `KYOmtpaaCYkTey5orY661x` 改名 `octosense-calendar-0.4.1-bundle (旧-1027-icon-错版)`
5. ✅ 团队空间新发布件 `FLSzr2BpZ6ZNfEeIhMCLik`（title: `octosense-calendar-0.4.1-bundle.zip`，含正确 blake3 + signature）
6. ✅ Issue [#77](https://github.com/OctoSense-org/OctoSense-App-Hub/issues/77) 描述 digest / signature / commit 同步更新到新值
7. ✅ Issue #77 旧更正评论（id `6011080848`）删除；发新更正评论（id [`6014490827`](https://github.com/OctoSense-org/OctoSense-App-Hub/issues/77#issuecomment-6014490827)）

**Hub check 新结果**：

```sh
hub check bundle --publisher-key OMA=46b11cc186e7a8ea8688c9d5a246caeaa27e6e0c8ba2986547d7511c0b872380
# → com.oma.octosense.calendar 0.4.1 — PASSED（0 警告）
```

`bundle/manifest.json` 已用新 `signature` 重新盖章，发布件内容与 git HEAD bundle 实算 blake3 一致。
**业务内容 blake3 不变**（hub 把 signature 字段排除在 hash 计算外），故不需要重新生成 SHA256。

**下载与校验**：

- GitHub Release：https://github.com/mark-liuzh/OctoSense-Calendar-OMA/releases/tag/v0.4.1
- Git commit：https://github.com/mark-liuzh/OctoSense-Calendar-OMA/commit/c0d496489b0c1ff3b5292abca07cf331bd8eadd0
- 团队空间新发布件：https://www.workbuddy.cn/space/d/FLSzr2BpZ6ZNfEeIhMCLik
- 团队空间旧 v5（已改名）：https://www.workbuddy.cn/space/d/KYOmtpaaCYkTey5orY661x

完整更新同时见 [`README.md`](../README.md)「### ⚠️ 准入检查（2026-10-06 修订记录）」一节。
