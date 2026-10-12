# 致 Ody：v0.5.5 需要 ai-host 环境与 manifest 重签

> 发件：mark-liuzh（本机实际开发者）  
> 收件：ody-cai  
> 背景：OctoSense 日历 v0.5.5 开发中，分支 `v0.5.5` 已推至 origin。

## 一、我们做了什么

v0.5.5 在 `bundle/main.splash` 中新增了以下功能：

1. **对话式 AI 排程**：自然语言创建日程，模型解析时间/参与人/重复规则/优先级，自动冲突检测与替代时段推荐，用户确认后写入。
2. **待办一键转日程**：待办行右侧「排期」按钮，按内容估算时长并自动挑空档生成事件。
3. **事件详情页**：笔记 / 纪要 / 跟进 / 链接，数据存本地 `event-notes.json`。
4. **OKR / 里程碑与手动周报**：目标支持设期限；手动生成本周周报文本，仅展示不自动外发。

设计约束：
- 不自动发邮件 / 邀请（宿主无可靠 API，且越权）。
- 不把用户日历详情泄漏给模型。
- 模型输出只参与建议，写入仍走 `reschedule()` 唯一入口并经过校验。

静态门禁 13/13 PASS。

## 二、为什么需要 ai-host

本地 `card-host.exe` **不注册 `model.complete` 服务**，因此本机只能验证 AI 排程的**降级分支**（模型不可用 → 提示用户手动创建）。

要验证 **成功路径**（自然语言 → 模型解析 → 冲突检查 → 用户确认 → 写入事件库），需要在**带 model 服务的宿主**上跑一遍。项目注释提到 "ai-host 也真的注册了 model.complete 服务"，因此需要 Ody 协助获取/配置该环境。

## 三、需要你提供或确认的事项

### 3.1 ai-host 环境

请提供以下任一即可：

- ai-host 的下载链接 / 安装包 / 构建方式；
- 或者一个已经配好 model provider 的可运行 ai-host 环境；
- 以及运行时需要配置的 model provider 信息（例如 OpenAI / Kimi / 其他，API key 由宿主管理还是需额外配置）。

### 3.2 manifest 重新签名

由于 `main.splash` 已修改，`bundle_blake3` 已变，原 OMA 签名失效。本地测试时我**临时移除了 `manifest.json` 的 `signature` 字段**（见 commit 记录），以便 `--allow-unsigned` 启动。

**最终提交/发版前必须由你使用 OMA 私钥重新签名。** 签名流程应为：

```bash
cd D:/Projects/Apps/octosense-calendar
D:/Projects/.cargo-target/octosense/release/hub.exe stamp bundle
# 然后使用 oma-publisher.key 签名 manifest
D:/Projects/.cargo-target/octosense/release/hub.exe sign-manifest bundle/manifest.json --key ~/.octosense/oma-publisher.key
```

具体 `sign-manifest` 参数以 `hub.exe --help` 或你之前的操作为准。

## 四、我们能先做的事

在你拿到 ai-host 之前，我会继续：
- 扩展 `tools/test_ai_gates.py` 或新增 `tools/test_ai_sched_gates.py`，离线验证 AI 排程后的写入校验逻辑。
- 跑全量回归的降级分支，确保模型不可用时界面不卡死、不丢数据。
- 更新 `docs/RELEASE-NOTES-v0.5.5.md`。

## 五、时间线

- 复赛版本冻结：**10/13 23:59**。
- 当前本地代码已完成功能实现，只差：① ai-host 真机验证；② manifest 重签；③ 全量回归；④ 提交/tag/发版。

请 Ody 在看到后回复能否提供 ai-host，以及何时方便重签 manifest。谢谢。
