---
name: convergent-research
description: |
  Multi-agent iterative research system with convergence detection.
  Use when the user asks to:
  - "run convergent research on <question>"
  - "multi-agent research <question>"
  - "iterative research with multiple agents"
  - "research <question> with convergence"
  Launches 5 independent agents (hermes, codex, claude, gemini, agy) to research
  the same question, then iteratively compares and refines until conclusions converge.
---

# Convergent Research

多智能体迭代研究系统，通过多轮对比与精炼实现结论收敛。

## 功能

启动 5 个独立 agent（hermes、codex、claude、gemini、agy）对同一研究问题进行迭代研究：

1. **第 1 轮**：各 agent 独立研究，生成初始报告
2. **第 2 轮**：各 agent 对比所有报告，识别共识与分歧，提取统一参考资料
3. **第 3 轮**：各 agent 基于对比结果精炼报告，修正错误、补充遗漏
4. **第 4+ 轮**：重复"对比 → 精炼"循环，直到收敛或达到最大轮次
5. **最终**：生成权威版研究报告

## 收敛判定

- **收敛阈值**：所有 agent 的核心结论一致性 ≥ 85%
- **最小轮次**：至少 2 轮（1 次研究 + 1 次对比）
- **最大轮次**：10 轮（防止无限循环）

## 调用步骤

当用户请求进行收敛研究时：

1. **解析参数**：
   - 提取研究问题（必需）
   - 提取输出目录（可选，默认 `./convergent_research_<timestamp>`）

2. **确认执行**：
   - 告知用户将启动 5 个 agent、可能耗时较长、消耗大量 token
   - 显示预估轮次范围（2-10 轮）
   - 询问是否继续

3. **调用编排器**：
   ```bash
   python3 ~/.claude/skills/convergent-research/orchestrator.py \
     "<研究问题>" \
     "<输出目录>"
   ```

4. **监控进度**：
   - 实时显示各轮次的执行状态
   - 显示收敛分数变化

5. **返回结果**：
   - 显示最终报告路径
   - 显示收敛历史
   - 提供查看报告的建议（`Read` 最终报告）

## 用法示例

用户输入：
```
/convergent-research "分析 Phaser MTDDS 中 amplitude 和 phase 参数的传播延迟差异"
```

你应该：
1. 确认问题和输出目录（默认 `./convergent_research_<timestamp>`）
2. 告知用户将启动 5 个 agent（hermes/codex/claude/gemini/agy）
3. 调用 `orchestrator.py`
4. 实时显示进度
5. 完成后读取并展示最终报告的摘要

## 输出结构

```
<output_dir>/
├── round_01/
│   ├── research/
│   │   ├── hermes.md
│   │   ├── codex.md
│   │   ├── claude.md
│   │   ├── gemini.md
│   │   ├── agy.md
│   │   ├── hermes.meta.json      # token 消耗等元数据
│   │   └── ...
│   └── metadata.json              # 本轮汇总元数据
│
├── round_02/
│   ├── comparison/
│   │   ├── hermes_comparison.md
│   │   └── ...
│   ├── unified_references.md      # 统一参考资料清单
│   └── metadata.json
│
├── round_03/
│   ├── refined/
│   │   ├── hermes_refined.md
│   │   └── ...
│   └── metadata.json
│
├── ...
│
├── authoritative/
│   └── final_report.md            # 最终权威报告
│
└── convergence_log.json           # 收敛历史
```

## 配置

编辑 `~/.claude/skills/convergent-research/agents/agents.yaml` 可调整：

- Agent 列表（增删 agent）
- 执行模式（并行/串行）
- 超时时间
- 收敛阈值
- 最大轮次

## 注意事项

1. **执行时间**：每轮需要所有 agent 完成，单轮可能耗时数分钟到数十分钟
2. **Token 消耗**：多轮迭代会消耗大量 token，建议在重要研究问题上使用
3. **工作目录**：Agent 会在当前工作目录执行，确保它们能访问需要的源码/文档
4. **并行执行**：默认并行执行所有 agent，如遇资源限制可在配置中改为串行
