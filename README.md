# Convergent Research

> Multi-agent iterative research system with convergence detection for Claude Code

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 概述

Convergent Research 是一个 Claude Code plugin，通过启动多个独立 AI agent 对同一研究问题进行迭代研究，自动对比、精炼，直到结论收敛，最终生成权威版研究报告。

### 核心特性

- 🤖 **4 个独立 Agent**：hermes、codex、claude、agy 并行研究
- 🔄 **动态收敛循环**：自动检测结论一致性，达到阈值后终止
- 📚 **统一参考资料**：第 2 轮自动提取并统一所有 agent 的参考资料
- 📊 **完整元数据**：记录每个 agent 的 token 消耗、执行时间、退出码
- 📝 **权威报告生成**：收敛后自动合并所有 agent 的共识结论

## 工作流程

```
第 1 轮：独立研究
  ├─ hermes   → 报告 A
  ├─ codex    → 报告 B
  ├─ claude   → 报告 C
  └─ agy      → 报告 D

第 2 轮：对比评估
  ├─ 识别共识与分歧
  ├─ 提取统一参考资料
  └─ 评估收敛度 → 未收敛，继续

第 3 轮：精炼报告
  ├─ 基于对比结果修正错误
  ├─ 补充遗漏角度
  └─ 使用统一参考资料

第 4 轮：再次对比
  └─ 评估收敛度 → 已收敛 ✅

最终：生成权威报告
  └─ 合并所有 agent 的共识结论
```

## 安装

### 方法 1：通过 Claude Code Plugin 系统（推荐）

```bash
# 克隆到 skills 目录
cd ~/.claude/skills
git clone https://github.com/mixgreen/convergent-research.git

# 重新加载 plugins
# 在 Claude Code 中执行：/reload-plugins
```

### 方法 2：手动安装

```bash
# 下载并解压到 ~/.claude/skills/convergent-research/
curl -L https://github.com/mixgreen/convergent-research/archive/main.tar.gz | tar xz
mv convergent-research-main ~/.claude/skills/convergent-research
```

## 使用方法

在 Claude Code 中调用：

```
/convergent-research "你的研究问题" [输出目录]
```

### 示例

```
/convergent-research "分析 Phaser MTDDS 中 amplitude 和 phase 参数的传播延迟差异" ./research_output
```

### 参数

- `<研究问题>`：必需，用引号包裹的研究问题
- `[输出目录]`：可选，默认为 `./convergent_research_<timestamp>`

## 输出结构

```
<output_dir>/
├── round_01/
│   ├── research/
│   │   ├── hermes.md              # Agent 研究报告
│   │   ├── hermes.meta.json       # Token 消耗等元数据
│   │   └── ...
│   └── metadata.json              # 本轮汇总元数据
│
├── round_02/
│   ├── comparison/
│   │   ├── hermes_comparison.md   # 对比评估报告
│   │   └── ...
│   ├── unified_references.md      # 统一参考资料清单
│   └── metadata.json
│
├── round_03/
│   ├── refined/
│   │   ├── hermes_refined.md      # 精炼后的报告
│   │   └── ...
│   └── metadata.json
│
├── authoritative/
│   └── final_report.md            # 最终权威报告
│
└── convergence_log.json           # 收敛历史
```

## 配置

编辑 `agents/agents.yaml` 可调整：

```yaml
agents:
  hermes:
    cli: hermes
    prompt_flag: -z
  # ... 其他 agent

execution:
  parallel: true          # 并行/串行执行
  timeout: 600            # 超时时间（秒）
  max_retries: 2          # 失败重试次数

convergence:
  threshold: 0.85         # 收敛阈值（0.0-1.0）
  max_rounds: 10          # 最大轮次
  min_rounds: 2           # 最小轮次
  judge_agent: claude     # 裁判 agent
```

## 依赖

### 必需

- **Claude Code**：主框架
- **Python 3.8+**：编排器运行环境
- **PyYAML**：配置文件解析

### Agent CLI（至少需要其中一个）

- `hermes`：Hermes Agent CLI
- `codex`：OpenAI Codex CLI
- `claude`：Claude Code CLI
- `agy`：AntiGravity CLI

> 注：可以在 `agents/agents.yaml` 中删除未安装的 agent

## 工作原理

### 收敛检测

每轮对比后，系统会：

1. 提取各 agent 报告的"收敛度自评"分数
2. 计算平均收敛分数
3. 判断是否达到阈值（默认 0.85）
4. 决定继续迭代或终止

### 参考资料统一

第 2 轮对比时，系统会：

1. 从所有对比报告中提取引用的源码文件、文档、URL
2. 去重后生成统一参考资料清单
3. 后续轮次所有 agent 使用相同的参考资料

### 元数据记录

每个 agent 执行后，系统会记录：

```json
{
  "agent": "hermes",
  "timestamp": "2026-06-01T17:30:00",
  "elapsed_seconds": 45.2,
  "exit_code": 0,
  "tokens": {
    "raw": "tokens used: 18,906"
  },
  "stderr": null
}
```

## 注意事项

1. **执行时间**：每轮需要所有 agent 完成，单轮可能耗时数分钟到数十分钟
2. **Token 消耗**：多轮迭代会消耗大量 token，建议在重要研究问题上使用
3. **工作目录**：Agent 会在当前工作目录执行，确保它们能访问需要的源码/文档
4. **并行执行**：默认并行执行所有 agent，如遇资源限制可在配置中改为串行

## 开发

### 项目结构

```
convergent-research/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── agents/
│   └── agents.yaml              # Agent 配置
├── prompts/
│   ├── round_research.md        # 研究 prompt 模板
│   ├── round_comparison.md      # 对比 prompt 模板
│   ├── round_refine_summary.md  # 精炼 prompt 模板（精简版）
│   └── authoritative.md         # 权威报告 prompt 模板
├── orchestrator.py              # ResearchCoordinator：主循环 + 收敛判定
├── agent_runner.py              # AgentRunner：执行（并行/重试/失败追踪）
├── report_parser.py             # ReportParser：纯解析（text → data）
├── round_executor.py            # RoundExecutor：单轮执行（模板→prompt→调度→落盘）
├── tests/                       # 单元测试（pytest，49 个）
│   ├── test_agent_runner.py
│   ├── test_report_parser.py
│   └── test_round_executor.py
├── SKILL.md                     # Skill 入口文档
├── README.md                    # 本文件
└── LICENSE                      # MIT License
```

### 架构

入口 `orchestrator.py` 中的 `ResearchCoordinator` 只负责编排——主循环、
收敛判定、统一参考资料落盘。执行细节分散在三个深度模块，各自可独立测试：

| 模块 | 职责 | 接口要点 |
|------|------|---------|
| `AgentRunner` | agent 执行 | 并行/串行、超时重试、失败 agent 追踪 |
| `ReportParser` | 报告解析（纯函数） | text→data，无 I/O、无状态 |
| `RoundExecutor` | 单轮执行 | 模板加载→prompt 构造→agent 调度→元数据落盘 |

运行测试：

```bash
python3 -m pytest tests/ -q
```

### 添加新 Agent

在 `agents/agents.yaml` 中添加：

```yaml
agents:
  your_agent:
    cli: your-agent-cli
    prompt_flag: -p
    description: "Your Agent Description"
```

### 自定义 Prompt 模板

编辑 `prompts/` 目录下的模板文件，使用 `{variable}` 占位符。

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 致谢

- [Claude Code](https://claude.ai/code) - 主框架
- [Hermes Agent](https://github.com/anthropics/hermes)
- [OpenAI Codex](https://openai.com/codex)
- [Google Gemini](https://ai.google.dev/)

## 贡献

欢迎提交 Issue 和 Pull Request！

## 作者

green ([@mixgreen](https://github.com/mixgreen))

---

**相关项目**

- [artiq-develop](https://github.com/mixgreen/artiq-develop) - ARTIQ 开发辅助 skill
- [llm-wiki-toolchain](https://github.com/mixgreen/llm-wiki-toolchain) - LLM 知识库工具链
