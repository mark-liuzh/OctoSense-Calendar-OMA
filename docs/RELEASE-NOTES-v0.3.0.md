# OctoSense 日历 v0.3.0

**2026 GOSIM Agentic App Hackathon · 初赛提交版本（第二轮） · 队伍 OMA**（成员 `mark-liuzh`、`ody-cai`）

> 初赛截止 10/4 23:59；复赛 10/9 23:59（版本冻结）。

## 这个版本能做什么

在 v0.1.0「ICS 导入 → 冲突消解 → 无损导出」的主线之上，v0.3.0 把它补成了一个  
**本地优先的完整日历**。全程离线，只申请 `storage` 一项能力，没有任何网络出口。

**日程本身**

- 月历 42 个格子每个都能点：点一下面板在下方展开，日期自动预填成那天；写标题、按「重复」切到每天 / 每周 / 每月 / 每年，保存即可
- 点中的格子会留一层赤陶底纹；**换日期时已经敲进去的标题与重复档位不会被清掉**；翻月则连同选中一起收起，不会留下「面板写着 9 月、日历翻到 10 月」这种对不上的状态
- 月 / 周 / 日三种视图切换

**五个新分区**（同一时刻只显示一段，且面板打开时自动收起 —— 为了守住竖向预算，不把底部按钮挤出视口）

- **待办清单**：按「天」记，点左边方框勾掉或取消，可「全部 / 只看未完成」过滤，单条可删
- **情绪日记**：5 档心情 + 一句备注，月历下方显示「本月已记 N 天」
- **目标与子任务**：中长期目标放首页，每张卡可拆成阶段性小任务，用纯文本画的进度条显示「1/2 步」
- **小知识 / 事件彩蛋**：节气科普（2025–2030 按天文算法实算，不是查表凑的）、历史上的今天（选编 **75** 条）、时间胶囊（封存到某个解封日，到期前只显示「封存中」）
- **事件图**：不另开图表区，而是把图放回日历本身 —— 月视图每个格子按当天日程数上色（热度 4 档），周视图 7 行摘要，日视图列出当天安排

**其余**

- **节假日**：内置 2025 / 2026 国务院放假安排。放假的每一天既标小绿点、又写出是哪个节日；调休补班标「班」字；只过节不放假标深灰小黑点。来源可在 中国 / 国际 / 全部 之间切换
- **冲突与消解**：按时间轴量化重叠时长（例如「重叠 30 分钟」），按承诺权重给改期建议，一键应用、改错可回滚
- **导出**：符合 RFC 5545，保留 `TZID` / `VALUE=DATE` / `Z` 后缀
- 首页章鱼吉祥物（Noto Animated Emoji，CC BY 4.0），点它会换一句话

## 准入检查

```
com.oma.octosense.calendar 0.3.0 — PASSED
  grants: capabilities {"storage"}, hosts {}, storage 16777216 bytes, agent none
```

**无任何警告** —— 本版已由发布者以队伍身份签名（`key_id: OMA`，Ed25519）。  
签名覆盖整个 manifest（含 `integrity.bundle_blake3`），任何人可用公钥独立复核：

```sh
hub check bundle --publisher-key OMA=46b11cc186e7a8ea8688c9d5a246caeaa27e6e0c8ba2986547d7511c0b872380
```

权限只有 `storage`，**没有网络权限**。

> 本版修掉了一个会让准入**直接失败**的问题：`bundle/manifest.json` 里的完整性戳  
> `integrity.bundle_blake3` 停留在更早的中间状态，与 bundle 实际内容对不上。  
> 按 App Hub PUBLISHING.md 直接跑 `hub check` 是 `REFUSED`；之所以之前没暴露，  
> 是因为 `tools/octo check` 会先自动 `hub stamp` 再 check，把不一致盖住了。  
> 已重算，并用**全新 clone** 验证过「不 stamp 也 PASSED」。

## 如何运行

见仓库 README 的[「快速开始」](https://github.com/mark-liuzh/OctoSense-Calendar-OMA#快速开始)。  
最短路径：

```bash
card-host --bundle bundle --app-data /tmp/octo-data --allow-unsigned --stamp
```

## 实测结论

**8 道静态门禁** `brace / quotes / toplevel / deps / paintfix / btnfocus / cellhover / fncalls` —— **8/8 PASS**。

**8 条端到端流程** —— **全部 PASS**：

| 流程             | 覆盖                               |
| -------------- | -------------------------------- |
| `run_e2e`      | 导入 → 解析 → 写入 → 导出 主线             |
| `run_conflict` | 冲突检出与消解建议                        |
| `run_edge`     | 边界字段（UTC / TZID / 全天 / SEQUENCE） |
| `run_negative` | 异常输入（非 ICS / 空壳 / 残缺事件 / 不存在的日期） |
| `run_festival` | 节假日与调休标记                         |
| `run_layout`   | 12 个界面状态的几何扫描                    |
| `run_new`      | 点格子写日程 / RRULE 展开                |
| `run_features` | 五个新分区 + 本地存储读回                   |

其中含**截图回读的像素级颜色断言**、与源码数据表的**逐字交叉校验**、以及  
**杀进程重启后的本地读回**。编译与运行错误数 **0**。

**平台**：Windows 与 macOS 均已在实机跑通上述全部检查。  
本版把 `listing.json` 的 `platforms` 从 `["windows"]` 扩为 `["windows", "macos"]`，  
并把 macOS 侧补齐过程中发现的三处「测试写死的隐含假设」一并修掉  
（月份绝对定位、输入框清空语义、按钮掉出视口）—— 这些是测试驱动的问题，  
应用本身改动为零。

## 资产

`octosense-calendar-0.3.0-bundle.zip` 内含完整 `bundle/` 目录（应用本体：`main.splash`、  
元数据、图标、截图、吉祥物素材）。解压后以 `--bundle <解压目录>/bundle` 运行即可。

## 已知限制

- **法定节假日数据只到 2026 年**。2027 及以后打开会显示空白（节气与「历史上的今天」不受影响）。
- **`FREQ=YEARLY` 起始于 2 月 29 日**时，平年没有这一天，那一年整年不出现（按 RFC 5545，无效日期跳过，不顺延到 3 月 1 日）；**`FREQ=MONTHLY` 起始于 31 日**时，只有 31 天的月份才有标记。界面不会为这两种情况额外提醒。
- **带修饰的 RRULE 不展开**（如 `FREQ=MONTHLY;BYDAY=-1FR`、`FREQ=WEEKLY;INTERVAL=2`），只保留原样导入 / 导出 + `DTSTART` 当天一个标记。这是刻意取舍：**宁可少标，不可乱标**。
- **不做实时互通**：应用没有网络出口，共享走的是「标记愿意分享的事件 → 导出只带这些 → 用你自己的渠道交换」这个诚实版本。

## 许可

本项目源码以 **Apache-2.0** 发布。界面吉祥物为 Noto Animated Emoji `:octopus:`（CC BY 4.0，  
© Google LLC），署名见 `THIRD-PARTY.md`。
