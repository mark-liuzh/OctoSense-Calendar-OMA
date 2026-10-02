# OctoSense 日历 v0.3.1

**2026 GOSIM Agentic App Hackathon · 初赛提交前清理 · 队伍 OMA**（成员 `mark-liuzh`、`ody-cai`）

> v0.3.1 是 v0.3.0 的提交前清理（patch）。功能与用户可见行为**零变化**，全部是「参赛合规 + 自检体系」层面的修补。

---

## 这个版本相对于 v0.3.0 的差异

### 参赛合规（避 hub 硬上限 REFUSED）

- `bundle/listing.json` 字段**同时踩上限**的问题被削掉 buffer：
  - `keywords` 10 → 7（去掉 `recurring` / `mood` / `local-first` —— 与
    `calendar` / `scheduling` / `offline` 语义重叠）
  - `screenshots` 8 → 7（去掉 `screenshots/03-conflict.png` —— 与
    `04-conflict-detail` 信息重叠）
  - 留 **3 个 keywords buffer + 1 个 screenshots buffer**，复赛加图 / 换关键词不会再被 REFUSED
- 自我审查的硬上限表（`docs/selfcheck-hardening.md`）从**过期值**改成实际值

### 自检体系加固（selfcheck §8.1 / §8.2 自承的薄弱点）

- `bash tools/run_all.sh --fast` 不再是空话 —— 把 card-host 必需性检查从 `_env.sh`
  顶层移到 `boot_host` 内；之前 `--fast` 在 source 阶段就被 FATAL 拦死，根本进不到
  静态自检；现在真·秒级通过。
- `run_e2e.sh` / `run_conflict.sh` 引入 `expect()` / `metric_is()` 函数（与
  `run_negative.sh` 同款）+ PASS/FAIL 计数。
  - 期望值只取**最少的关键字**，避免实现微调时把测试拖崩。
  - run_conflict 把 README 反复强调的两条硬证据写进脚本：
    - `[4/9]` 冲突详情必须出现「重叠 30 分钟」
    - `[7/9]` 往返幂等必须等于「新增 0 / 改期 0 / 跳过 4」
- `run_conflict.sh` 补上资源加载硬断言（与 `run_e2e.sh` 同款；之前漏了）：
  - 去掉裸 `404`（会误匹配宿主源码 `splash.rs:404:9` 行号）
  - 改为 `load failed` / `failed to load` / `failed to fetch` / `no such file` 四模式
  - 命中真 exit 1，不再 `|| true` 静默放过

### Dead code 清理

- `main.splash` 删 6 行死代码：
  - line 342-346 五个 unused iOS 系统色 let（`ink` / `secondary` / `accent` / `warn` / `okc`），
    与设计语言「档案卷宗」完全冲突
  - line 325 重复的 `status_text`（被 line 337 完全覆盖）
  - `toplevel.py` 只检查 `fn` / `start_timeout`，对 `let` 重复定义不报警，
    静态门禁不会拦，但实际是死代码

---

## 验证结论

- **8 道静态门禁** —— 8/8 PASS（brace / quotes / toplevel / deps / paintfix /
  btnfocus / cellhover / fncalls）
- **bash -n** —— 9 个 shell 脚本全 OK
- **`bash tools/run_all.sh --fast`** —— 真·秒级通过
- **端到端流程** —— 没在无宿主机上重跑；提交前需要在装了 card-host 的机器上
  `bash tools/run_e2e.sh` + `bash tools/run_conflict.sh` 各跑一次，确认新断言
  不会因我对 splash 文案解读偏差而误报

---

## ⚠️ bundle 完整性戳与签名

本次 commit `83137a0` 改了 `bundle/main.splash` 与 `bundle/listing.json`，**`integrity.bundle_blake3` 与内容不一致**。提交 App Hub 前必须：

```bash
hub stamp bundle
hub sign-manifest bundle --key ~/.octosense/oma-publisher.key --key-id OMA
hub check bundle --publisher-key OMA=46b11cc186e7a8ea8688c9d5a246caeaa27e6e0c8ba2986547d7511c0b872380
```

期望 `— PASSED` 且**无警告**。新 digest / 新签名值会写进 manifest，
之后还得 commit + push 这次 stamp 的改动。

---

## 许可与第三方

同 v0.3.0。本项目源码以 **Apache-2.0** 发布；界面吉祥物为 Noto Animated Emoji `:octopus:`（CC BY 4.0，© Google LLC），署名见 `THIRD-PARTY.md`。
