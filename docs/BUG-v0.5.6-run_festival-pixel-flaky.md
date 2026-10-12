# Bug 记录：run_festival「班」字像素判定偶发失败

- **发现时间**：2026-10-12 全量回归测试
- **发现版本**：`v0.5.6`（本地 commit `933cace` / 远程 `e5475746`）
- **相关测试**：`run_festival`
- **严重等级**：中（flaky / 环境相关）
- **指派修复**：ody-cai（Windows + Linux 复测后修复）

## 现象

`bash tools/run_all.sh` 中 `run_festival` 流程出现 3 处像素断言失败：

```
FAIL 「班」字像素判定（赤陶 EVENT） — 期望 EVENT，实际 NONE  [302,489=NONE]
```

出现位置：
1. 2026 年 10 月，节日来源「中国」
2. 2026 年 10 月，节日来源「全部」
3. 2025 年 10 月，节日来源「中国」

同一条测试里：
- 2026 年 9 月「班」字判定 PASS
- 2025 年 9 月「班」字判定 PASS

说明坐标/定位器本身没有错，是**特定月份/渲染状态下颜色采样未命中**。

## 复现步骤

1. Windows 环境启动 `bash tools/run_all.sh`
2. 等待 `run_festival` 执行到 2026-10 或 2025-10
3. 观察「班」字像素判定结果

注：该问题为偶发，此前单跑 `run_festival` 时稳定 PASS。

## 根因判断

- 坐标 `[302,489]` 处的颜色未落在 `EVENT`（赤陶色）阈值内，实际读回 `NONE`。
- 可能原因：
  - Windows DWM / 字体渲染子像素定位差异；
  - 月份切换动画尚未完全稳定即采样；
  - 特定日期格子的背景/文字合成颜色与预期有偏差。
- **非 v0.5.6 功能回归**：v0.5.6 改动集中在事件详情页、历史回滚、取消重排，未修改节假日渲染逻辑。

## 建议修复方向

1. 在 `e2e.py` 的 `dotcolor` 中对「班」字区域做邻域投票或扩大采样窗口，降低单像素抖动影响。
2. 在翻页后增加额外稳定等待，确保渲染完全静止。
3. 在 Windows 与 Linux 上分别复测，确认是否为 Windows 特有 flaky；若是，可在 Windows 环境放宽阈值或改用文本断言替代像素断言。

## 相关文件

- 测试脚本：`tools/run_festival.sh`
- E2E 辅助：`tools/e2e.py`
- 完整日志：`.runtime/run-all/run_festival.txt`
- 截图证据：`.runtime/evidence/02-oct-cn.png`、`.runtime/evidence/04-oct-all.png`、`.runtime/evidence/05-oct2025-cn.png`
