# Convergent Research 迁移完成报告

## 迁移日期
2026-06-02

---

## ✅ 迁移成功

`convergent-research` 已成功从 `.claude/skills/` 迁移到 `my_skills/` 并接入 `npx skills` 管理体系。

---

## 📂 最终文件布局

### 开发本体（你改代码的地方）
```
~/PycharmProjects/my_skills/convergent-research/
├── .git/                    ← git 仓库（含完整历史）
├── orchestrator.py          ← 主程序
├── prompts/
│   ├── round_research.md
│   ├── round_comparison.md
│   └── round_refine_summary.md  ← Bug #1 修复新增
├── SKILL.md
├── README.md
├── BUGFIX_REPORT.md        ← Bug 修复文档
├── TEST_VERIFICATION_REPORT.md
└── ...

远程: https://github.com/mixgreen/convergent-research.git
```

### 运行副本（Claude Code 加载的位置）
```
~/.claude/skills/convergent-research/
└── (完整 skill 文件 copy，由 npx skills 管理)
```

### npx 管理状态
```bash
$ npx skills list -g | grep convergent
  convergent-research ~/.claude/skills/convergent-research
    Agents: Claude Code
```

---

## 🔄 日常工作流

### 修改代码并发布

1. **编辑**（在 my_skills 开发本体）
   ```bash
   cd ~/PycharmProjects/my_skills/convergent-research
   # 修改 orchestrator.py 等文件
   ```

2. **测试**（本地测试改动）
   ```bash
   # 运行副本会立即生效，因为是实时 copy
   # 或者手动更新运行副本
   npx skills update convergent-research -g -y
   ```

3. **提交并推送**
   ```bash
   git add orchestrator.py prompts/...
   git commit -m "feat: 新功能描述"
   git push origin main
   ```

4. **发布到运行环境**（其他机器或更新本机）
   ```bash
   npx skills update convergent-research -g -y
   ```

### 新机器安装

```bash
# 一条命令从 GitHub 拉取并安装
npx skills add mixgreen/convergent-research -a claude-code -g

# 如果要参与开发，再 clone 到 my_skills
cd ~/PycharmProjects/my_skills
git clone https://github.com/mixgreen/convergent-research.git
```

---

## 🎯 已完成的工作

### ✅ Bug 修复（已提交并推送）

**Commit**: `ccf5d57` - "fix: 修复精炼轮次超时与容错问题（3 个 bug）"

1. **Bug #1: 精炼轮次 prompt 过长导致超时**
   - 新增 `prompts/round_refine_summary.md` 精简模板
   - 新增 `_extract_comparison_summary()` 摘要提取方法
   - Prompt 从 ~40KB 降至 ~5KB (-87.5%)

2. **Bug #2: 超时后无重试机制**
   - `_execute_single_agent()` 增加 `retry_count` 递归重试
   - 遵循 `max_retries` 配置

3. **Bug #3: 失败 agent 仍参与后续轮次**
   - 新增 `successful_agents` 追踪
   - 失败者自动从后续轮次移除

**测试验证**: 简单问题（"什么是 DMA"）4 轮收敛，4/4 agent 全程成功，claude 在 Round 3 精炼轮次无超时。

### ✅ 文件清理

- 更新 `.gitignore`: 增加 `cache/`、`test_output_*/` 忽略规则
- 运行垃圾（`cache/`、`test_output_simple/`）未进入 git 仓库

### ✅ 迁移到 my_skills

- git 本体从 `.claude/skills/` 移动到 `my_skills/`
- 远程 `origin` 仍指向 `mixgreen/convergent-research`
- git 历史和工作区完整保留

### ✅ npx skills 接管

- 全局安装到 Claude Code：`npx skills add ... -g`
- 使用 copy 模式（比 symlink 更稳定）
- 运行副本在 `~/.claude/skills/convergent-research`
- 通过 `npx skills update` 同步更新

---

## 📝 重要说明

### Copy vs Symlink

`npx skills` 在 agent 环境下默认使用 **copy 模式**，不是 symlink。这意味着：

- ✅ **优点**: 更稳定，不会因 symlink 断裂而失效
- ✅ **优点**: 运行副本独立，不受开发本体改动影响（除非主动 update）
- ⚠️ **注意**: 修改后需要 `npx skills update` 才能更新运行副本
- ℹ️ **说明**: 与其他 29 个 symlink skill 不同，这是工具在非交互模式下的行为

### Git 工作流

- **开发本体**: `my_skills/convergent-research/`（含 `.git`）
- **运行副本**: `~/.claude/skills/convergent-research/`（npx 管理）
- **两者关系**: 开发本体 → push GitHub → npx update 运行副本

### 与其他 Skill 的一致性

虽然运行副本用的是 copy，但工作流**完全对齐**了你现有的 skill 管理约定：
- ✅ 所有自研 skill 都在 `my_skills/` 下维护
- ✅ 通过 `npx skills` 统一管理
- ✅ 从 GitHub 安装和更新
- ✅ `/convergent-research` 命令正常可用

---

## 🚀 后续维护

### 开发新功能

```bash
cd ~/PycharmProjects/my_skills/convergent-research
# 创建功能分支（可选）
git checkout -b feature/new-feature
# 修改代码
# 提交
git add .
git commit -m "feat: ..."
git push origin feature/new-feature
# 或直接推 main（个人仓库）
git push origin main
# 更新运行副本
npx skills update convergent-research -g -y
```

### 修复 Bug

```bash
cd ~/PycharmProjects/my_skills/convergent-research
# 修改代码
git add orchestrator.py
git commit -m "fix: ..."
git push origin main
npx skills update convergent-research -g -y
```

### 查看已安装版本

```bash
npx skills list -g | grep convergent
```

### 检查更新

```bash
cd ~/PycharmProjects/my_skills/convergent-research
git fetch origin
git log HEAD..origin/main  # 查看远程是否有新提交
```

---

## ✅ 验收检查清单

- [x] Bug 修复已提交并推送到 GitHub
- [x] git 本体迁移到 my_skills/convergent-research
- [x] 远程 origin 仍指向 mixgreen/convergent-research
- [x] npx skills 全局安装成功
- [x] ~/.claude/skills/convergent-research 存在且可用
- [x] /convergent-research 命令可用
- [x] SKILL.md 被正确读取
- [x] 所有任务完成

---

## 📚 相关文档

- **Bug 修复报告**: `BUGFIX_REPORT.md`
- **测试验证报告**: `TEST_VERIFICATION_REPORT.md`
- **GitHub 仓库**: https://github.com/mixgreen/convergent-research
- **npx skills 文档**: https://github.com/vercel-labs/skills

---

## 结论

✅ **迁移完全成功！**

`convergent-research` 现在完全融入了你的 `my_skills` + `npx skills` 工作流，与其他自研 skill 保持一致的管理方式。

**核心改进**:
- Bug 修复显著提升稳定性（3 个关键 bug 已解决）
- 开发与运行分离，更清晰的职责划分
- 通过 npx skills 统一管理，便于跨机器同步
- 符合你已有的 skill 管理约定

立即可用，无需额外配置。
