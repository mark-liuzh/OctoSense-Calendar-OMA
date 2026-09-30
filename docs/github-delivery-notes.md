# GitHub 交付链路打通记录

> 队伍 OMA · Agentic App 黑客松 2026 · 选题 OctoSense 日历
> 时间：2026-09-27 晚 · 初赛截止按官网 **10/4 23:59** 倒排

## 一、本次完成的事

| # | 事项 | 状态 | 结果 |
| --- | --- | --- | --- |
| 1 | 建 GitHub 公开仓库 | ✅ 完成 | `mark-liuzh/OctoSense-Calendar-OMA` |
| 2 | 推送本地代码与历史 | ✅ 完成 | 3 次提交合并入 main，无冲突 |
| 3 | 仓库设为 Apache-2.0 | ✅ 完成 | GitHub 识别 `license: Apache-2.0` |
| 4 | 邀请 ody-cai 为协作者 | ✅ 已发出 | invitation id `334936608`，权限 `write` |
| 5 | 邀请 ody-cai 为 admin | ❌ 受阻 | 个人账号仓库不支持 admin 角色 |

## 二、仓库最终状态

- 地址：`https://github.com/mark-liuzh/OctoSense-Calendar-OMA`
- 可见性：**public**（符合赛制「公开仓库」硬性要求）
- 许可证：**Apache-2.0**
- 默认分支：`main`
- 提交历史：
  - `3331c8f` chore: init repo for OctoSense calendar app (team OMA)
  - `e2e19a3` chore: add Apache-2.0 license, restructure docs
  - `3ec3831` chore: merge remote initial license commit
- 已推送文件：`README.md`、`LICENSE`、`.gitignore`、`docs/hackathon-notes.md`

## 三、卡点：admin 权限授不了

### 现象

以 `permission=admin` 调用 GitHub API 邀请协作者，返回：

```
422 Validation Failed
Cannot assign ody-cai permission of admin
```

### 根因

GitHub 的硬规则：**个人账号（User）持有的仓库，协作者角色上限是 write（push）**。
`admin` 角色只在 **Organization 持有的仓库**上可选。

已验证账号 `mark-liuzh` **不属于任何 Organization**（`gh api user/orgs` 返回空）。

### 三条可选解法

| 方案 | 操作 | 代价 |
| --- | --- | --- |
| A. 保持现状 | 接受 ody-cai 为 write 权限 | 零成本；日常协作（推代码、开 PR、改 issue）完全够用，只差「改仓库设置/加协作者/删仓库」这几项管理操作 |
| B. 建 Organization | 新建 org → 把仓库 transfer 过去 → 重新邀请 ody-cai 为 admin | 仓库 URL 会变（GitHub 会自动重定向旧地址）；需确认 org 与赛制提交要求兼容 |
| C. 不改权限 | 只把 owner 权限留在 mark-liuzh 手上 | 与用户原始要求（admin）有偏差 |

**建议 A**：赛事交付物核心是「代码公开 + 能跑」，write 已覆盖全部开发协作需求；admin 的差异只在仓库管理动作上，两位成员是队友不是陌生人，风险很低。若确需 admin，走 B。

## 四、技术路径复盘（供后续复用）

### 为什么不用 GitHub 连接器

GitHub 连接器（MCP）当前**只有读权限**：

- 建仓 `create_repository` → 403 `Resource not accessible by integration`（autoInit 开/关都试过）
- 读官方组织公开仓库文件 → 正常（说明读没问题）
- 对自己账号的写操作 → 一律失败

**结论：建仓、推代码、管协作者，一律走 `gh` CLI，不要指望连接器。**

### 打通 gh 的完整步骤（Windows）

```bash
# 1. 安装（约 1 分 40 秒）
winget install --id GitHub.cli --exact --accept-source-agreements --accept-package-agreements

# 2. 当前 bash session 的 PATH 不会刷新 —— 必须用全路径调用
"/c/Program Files/GitHub CLI/gh.exe" --version

# 3. 授权登录（device flow，需人工在浏览器粘贴设备码，约 46 秒）
"/c/Program Files/GitHub CLI/gh.exe" auth login --hostname github.com \
  --git-protocol https --web --scopes "repo,admin:org,delete_repo,workflow"

# 4. 让 git 用上 gh 的凭据（不做这步 git push 会报 terminal prompts disabled）
"/c/Program Files/GitHub CLI/gh.exe" auth setup-git

# 5. 建仓
"/c/Program Files/GitHub CLI/gh.exe" repo create OctoSense-Calendar-OMA \
  --public --description "..." --license apache-2.0
```

### 三个必须记住的坑

1. **`gh auth login` 必须后台跑**（`run_in_background=true`），否则会阻塞到命令行超时。
2. **`gh repo create --license` 会生成一个初始提交** —— 本地已有 git 历史时，先
   `git fetch && git merge origin/main --allow-unrelated-histories --no-edit`，再 push。
3. **`git credential fill` 会挂起等待输入**（凭据管理器为空时的表现），不要在能阻塞的地方执行。

## 五、下一步

1. **等 ody-cai 接受邀请**（对方邮箱/GitHub 通知里确认）
2. **决定 admin 方案**（建议 A：接受 write）
3. **验证 Windows 工具链**：Rust + CMake + `card-host` 能否在本机跑通 —— 这是当前最大单点风险，官方仅在 macOS Apple silicon 验证过
4. **拉取官方五仓库工作区**并构建 `hub` + `card-host`
5. **编写 `main.splash` + `manifest.json` 草案**
6. **按 10/4 23:59 倒排 7 天计划**
7. **资料库待办**：邀请队友的 WorkBuddy 账号加入本空间（需在 WorkBuddy 界面手动完成，脚本无邀请接口）
