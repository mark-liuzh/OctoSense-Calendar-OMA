# OctoSense 日历 v0.5.7 全量回归报告

- **时间**：2026-10-14 00:29–00:39（GMT+8，跨零点，含应用/驱动日期对齐验证场景）
- **基线**：分支 `v0.5.7` HEAD `ba3724f`（发布提交前）
- **环境**：macOS · card-host `_toolchain/OctoSense-App-Hub/target/release/card-host` · bundle `.runtime/bundle-dev`（剥签名副本）· 窗口 412x1000
- **总评**：**9 / 9 全过**（静态门禁 13 道 + 9 条端到端流程），宿主编译/运行错误数 **0**

## 汇总

| 套件 | 结果 | 关键断言 |
|---|---|---|
| 静态门禁（13 道） | PASS | brace / quotes / toplevel / deps / paintfix / btnfocus / cellhover / fncalls / ai_gates / host_errors / portability / shellsafe / writepoint |
| run_e2e | PASS 10/10 | 空状态→导入→写入→列表，文本断言全过 |
| run_conflict | PASS 21/21 | 冲突消解 + AI 七道闸；**ICS 往返 0/0/N 保持** |
| run_edge | PASS | RRULE / EXDATE / RDATE / UTC / VALUE=DATE 往返字段丢失数 **0**，幂等 0/0/6 |
| run_negative | PASS 8/8 | 非法输入、空 ICS、坏日期等负向路径 |
| run_festival | PASS | 节假日渲染 + 来源标注 |
| run_layout | PASS | 布局扫描零尺寸/负坐标/越界 = 0 |
| run_new | PASS | 新建流程 + RRULE UNTIL 边界（不越界标） |
| run_features | PASS | 六大分区交互 + 磁盘读回（重启后数据仍在） |
| run_new_features | PASS 18/18 | 历史回滚 + 取消后自动释放：排期避开阻塞（10:00-11:00）→ 取消阻塞 → auto 前移 09:00 → 历史版本含 rebalance 前时间 → UI 回滚闭环 |

## 本版修复的专项验证

1. **详情面板 tab 修复**（`f0b3049`）：真人窗口实测五个 tab 互斥切换、内容全在视口内；e2e 侧 run_e2e / run_layout / run_new_features 全绿。
2. **测试日期对齐**（`ba3724f`）：本次运行跨零点（00:29 启动），run_new_features 18/18 全过——驱动「今天」与应用进程日期（UTC 锚定）不再错位。
3. **auto 事件重排正确性**（`f852315` 修复项）：60 分钟待办按 60 分钟重排；「事件详情」默认打开当天首个活跃事件；取消阻塞事件后 auto 事件正确前移。

## 已知非阻塞项

- 详情页 tab 行**宿主合成点击** capture 缺陷（click 到达 VM 概率 ~6%，hover 100% 命中；9 方案穷举无效，定位于宿主层 button.rs）——真人鼠标不受影响；e2e 用数据层断言兜底。
- run_edge / run_features 在早前个别轮次出现过灌入夹具/点击落点抖动（退出码 2 / 单项 None），复跑即过；本轮 9/9 一次通过。

## 复跑命令

```bash
OCTO_CARD_HOST="$PWD/_toolchain/OctoSense-App-Hub/target/release/card-host" \
OCTO_BUNDLE=.runtime/bundle-dev \
bash tools/run_all.sh
```
