#!/usr/bin/env python3
"""
Convergent Research Orchestrator
多智能体迭代研究编排器，支持动态收敛检测
"""

import sys
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from agent_runner import AgentRunner
from report_parser import ReportParser
from round_executor import RoundExecutor


class ResearchOrchestrator:
    def __init__(self, config_path: Path, output_dir: Path):
        self.config_path = config_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 加载配置
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.agents = self.config['agents']
        self.exec_config = self.config['execution']
        self.conv_config = self.config['convergence']

        # 收敛历史
        self.convergence_log = []

        # 统一参考资料（第 2 轮后提取）
        self.unified_references = None

        # Agent 执行器（封装并行/重试/失败追踪）
        self.agent_runner = AgentRunner(
            agents=self.agents,
            exec_config=self.exec_config,
            output_dir=self.output_dir,
        )

        # 报告解析器（纯解析：text in / data out）
        self.report_parser = ReportParser()

        # 轮次执行器（模板加载 + prompt 构造 + agent 调度 + 元数据落盘）
        self.round_executor = RoundExecutor(
            agent_runner=self.agent_runner,
            report_parser=self.report_parser,
            agents=self.agents,
            prompt_dir=self.config_path.parent.parent / "prompts",
            output_dir=self.output_dir,
        )

    @property
    def successful_agents(self):
        """委托给 AgentRunner 的成功 agent 追踪（Bug #3 修复）"""
        return self.agent_runner.successful_agents

    def run(self, question: str) -> Path:
        """运行完整的研究流程，返回最终报告路径"""
        print(f"🚀 启动收敛研究系统")
        print(f"📝 研究问题: {question}")
        print(f"🤖 参与 Agent: {', '.join(self.agents.keys())}")
        print(f"📁 输出目录: {self.output_dir}")
        print(f"🎯 收敛阈值: {self.conv_config['threshold']}")
        print(f"🔄 最大轮次: {self.conv_config['max_rounds']}\n")

        round_num = 1

        # Round 1: 独立研究
        print(f"{'='*60}")
        print(f"第 {round_num} 轮：独立研究")
        print(f"{'='*60}")
        reports_r1 = self.round_executor.run_research(round_num, question)

        # 开始迭代循环
        while round_num < self.conv_config['max_rounds']:
            round_num += 1

            # 偶数轮：对比评估
            if round_num % 2 == 0:
                print(f"\n{'='*60}")
                print(f"第 {round_num} 轮：对比评估")
                print(f"{'='*60}")

                prev_round = round_num - 1
                prev_reports = self.round_executor.load_reports(prev_round)

                comparison_reports = self.round_executor.run_comparison(
                    round_num, question, prev_reports
                )

                # 第一次对比时提取统一参考资料
                if round_num == 2:
                    self._extract_unified_references(comparison_reports)

                # 评估收敛度
                convergence = self._evaluate_convergence(round_num, comparison_reports)
                self.convergence_log.append(convergence)
                self._save_convergence_log()

                print(f"\n📊 收敛度评估:")
                print(f"   分数: {convergence['score']:.2f}")
                print(f"   状态: {convergence['status']}")

                # 判断是否收敛
                if convergence['score'] >= self.conv_config['threshold']:
                    if round_num >= self.conv_config['min_rounds']:
                        print(f"\n✅ 研究已收敛！(score={convergence['score']:.2f})")
                        break
                    else:
                        print(f"\n⏳ 收敛但未达最小轮次，继续迭代...")

            # 奇数轮（≥3）：基于对比精炼
            else:
                print(f"\n{'='*60}")
                print(f"第 {round_num} 轮：基于对比精炼")
                print(f"{'='*60}")

                comparison_round = round_num - 1
                prev_research_round = round_num - 2

                comparison_reports = self.round_executor.load_reports(comparison_round)
                prev_research_reports = self.round_executor.load_reports(prev_research_round)

                refined_reports = self.round_executor.run_refine(
                    round_num, question,
                    prev_research_reports, comparison_reports,
                    self.unified_references,
                )

        # 生成最终权威报告
        print(f"\n{'='*60}")
        print(f"生成最终权威报告")
        print(f"{'='*60}")
        final_report = self._generate_authoritative_report(question)

        print(f"\n✅ 研究完成！")
        print(f"📄 最终报告: {final_report}")
        print(f"📊 收敛历史: {self.output_dir / 'convergence_log.json'}")

        return final_report

    def _extract_unified_references(self, comparison_reports: Dict[str, Path]) -> None:
        """提取统一参考资料并写入文件（解析委托给 ReportParser）"""
        print("   📚 提取统一参考资料...")

        # 读取文件内容，解析交给纯解析器
        report_texts = {
            name: Path(p).read_text(encoding="utf-8")
            for name, p in comparison_reports.items()
        }
        all_refs = self.report_parser.extract_references(report_texts)

        # 保存统一参考资料
        refs_path = self.output_dir / "round_02" / "unified_references.md"
        with open(refs_path, 'w', encoding='utf-8') as f:
            f.write("# 统一参考资料清单\n\n")
            f.write("（从第 2 轮对比报告中提取，供后续轮次使用）\n\n")
            if all_refs:
                for ref in all_refs:
                    f.write(f"- {ref}\n")
            else:
                f.write("（本轮未提取到参考资料，可能是纯理论问题或 agent 未在对比报告中列出参考资料）\n")

        self.unified_references = refs_path.read_text(encoding='utf-8')

        if all_refs:
            print(f"   ✅ 提取了 {len(all_refs)} 条参考资料")
        else:
            print(f"   ⚠️  未提取到参考资料（可能是纯理论问题）")

    def _evaluate_convergence(self, round_num: int,
                             comparison_reports: Dict[str, Path]) -> Dict:
        """评估收敛度（分数提取委托给 ReportParser，状态判定保留为策略）"""
        print("   🔍 评估收敛度...")

        # 读取文件内容，分数提取交给纯解析器
        report_texts = {
            name: Path(p).read_text(encoding="utf-8")
            for name, p in comparison_reports.items()
        }
        scores = self.report_parser.extract_convergence_scores(report_texts)

        # 计算平均分数
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # 判断状态（依赖配置阈值，属于编排策略，保留在此）
        if avg_score >= self.conv_config['threshold']:
            status = "converged"
        elif round_num >= self.conv_config['max_rounds']:
            status = "max_rounds_reached"
        else:
            status = "continue"

        return {
            'round': round_num,
            'score': avg_score,
            'individual_scores': scores,
            'status': status,
            'timestamp': datetime.now().isoformat()
        }

    def _save_convergence_log(self) -> None:
        """保存收敛历史"""
        log_path = self.output_dir / "convergence_log.json"
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(self.convergence_log, f, indent=2, ensure_ascii=False)

    def _generate_authoritative_report(self, question: str) -> Path:
        """生成最终权威报告"""
        auth_dir = self.output_dir / "authoritative"
        auth_dir.mkdir(exist_ok=True)

        # 找到最后一轮的报告
        last_round = max([
            int(d.name.split('_')[1])
            for d in self.output_dir.glob("round_*")
        ])

        final_reports = self.round_executor.load_reports(last_round)

        # 使用裁判 agent 生成权威报告
        judge_agent = self.conv_config['judge_agent']

        prompt = f"""
你是一个技术报告编辑专家。以下是经过 {last_round} 轮迭代后，{len(final_reports)} 个 agent
对同一研究问题的最终报告。这些报告已经过多轮对比和精炼，达到了收敛状态。

请基于这些报告，生成一份**权威版研究报告**，要求：

1. **合并共识**：提取所有 agent 都同意的核心结论
2. **解决分歧**：如果仍有分歧，基于源码引用的可靠性判断，选择最可信的结论
3. **标注来源**：每个关键结论都标注"经 X 个 agent 验证"或"基于 agent Y 的发现"
4. **完整性**：覆盖所有 agent 提出的有价值角度
5. **可读性**：结构清晰，适合作为最终交付文档

## 研究问题

{question}

## 各 Agent 的最终报告

{self.report_parser.format_for_prompt(final_reports)}

---

## 输出格式

生成一份完整的 Markdown 研究报告，包含：
- 标题：在原问题基础上加"—— 权威版"
- 状态说明：注明"经 {last_round} 轮迭代、{len(final_reports)} 个 agent 收敛验证"
- 完整的研究内容（结论速览、详细分析、核心结论、参考资料）
- 附录：与原始报告的差异说明、收敛历史

开始生成权威报告：
"""

        output_path = auth_dir / "final_report.md"
        print(f"   🤖 使用 {judge_agent} 生成权威报告...")
        self.agent_runner.run_single_agent(judge_agent, prompt, output_path)

        return output_path


def main():
    if len(sys.argv) < 3:
        print("用法: orchestrator.py <question> <output_dir>")
        sys.exit(1)

    question = sys.argv[1]
    output_dir = Path(sys.argv[2])

    # 配置文件路径
    script_dir = Path(__file__).parent
    config_path = script_dir / "agents" / "agents.yaml"

    orchestrator = ResearchOrchestrator(config_path, output_dir)
    orchestrator.run(question)


if __name__ == "__main__":
    main()
