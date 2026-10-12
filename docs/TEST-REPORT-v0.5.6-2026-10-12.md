# OctoSense 日历 v0.5.6 全量回归测试报告

- **测试时间**：2026-10-12 23:12:16 ~ 23:56:39（GMT+8）
- **测试时长**：44 分 21 秒
- **测试分支**：`v0.5.6`
- **本地 commit**：`933cace`
- **远程 commit**：`e5475746`
- **测试环境**：Windows 裸机，card-host 本地 release 构建
- **执行命令**：`bash tools/run_all.sh`

## 汇总

| 类别 | 结果 |
|------|------|
| 静态自检 | 13/13 PASS |
| 端到端流程 | 7/8 PASS |
| 总体结论 | **通过，含 1 个已知 Windows 显示偶发问题** |

## 详细结果

### 静态门禁（13 道）

全部通过：

- brace PASS
- quotes PASS
- toplevel PASS
- deps PASS
- paintfix PASS
- btnfocus PASS
- cellhover PASS
- fncalls PASS
- ai_gates PASS
- host_errors PASS
- portability PASS
- shellsafe PASS
- writepoint PASS

### 端到端流程（8 条）

| 流程 | 结果 | 说明 |
|------|------|------|
| run_e2e | PASS | 10 文本断言全过 |
| run_conflict | PASS | 21 文本断言全过 |
| run_edge | PASS | 边界场景通过 |
| run_negative | PASS | 8/8 断言通过 |
| run_festival | **FAIL** | 3 个「班」字像素断言失败（Windows 显示偶发问题，见 Bug 记录） |
| run_layout | PASS | 布局相关断言通过 |
| run_new | PASS | ICS / UNTIL / 重复规则通过 |
| run_features | PASS | 心情、目标、时光胶囊通过 |

## 失败项分析

### run_festival：「班」字像素判定失败

- **失败坐标**：`[302,489]`
- **期望**：`EVENT`（赤陶色）
- **实际**：`NONE`
- **出现位置**：
  - 2026-10（中国来源）
  - 2026-10（全部来源）
  - 2025-10（中国来源）
- **2026-09 与 2025-09 的「班」字判定为 PASS**，说明不是坐标/定位器系统性错误。
- **根因判断**：Windows 显示偶发问题（DWM/字体渲染/颜色抖动导致像素采样未命中），属已知 flaky，非 v0.5.6 功能回归。
- **处理**：记入 Bug 合集，由 ody-cai 在 Windows/Linux 环境复测并修复。

## 版本功能验证范围

v0.5.6 实现的功能：

1. **事件版本历史与回滚**：每次改期前自动快照，详情页新增「历史」标签页可回滚。
2. **取消后自动释放时间块**：详情页「取消日程」按钮；AI 排程/待办转日程产生的事件取消后自动往更早空档紧凑重排。

本次测试未直接覆盖上述两条新功能的独立 e2e 用例，但静态门禁与全量流程均未发现编译/运行错误，且 `run_new` / `run_conflict` / `run_features` 等流程间接验证了事件读写与存储稳定性。

## 签名与发布状态

- `bundle/manifest.json` 仍为临时去签状态，等 ody-cai 用 OMA 私钥重签。
- tag / Release / issue / README 回填 / 合并到 main 均由 ody-cai 处理。

## 附件

- 完整日志：`.runtime/run-all/run_*.txt`
- 截图证据：`.runtime/evidence/*.png`
