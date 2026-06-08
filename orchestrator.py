#!/usr/bin/env python3
"""
Convergent Research Coordinator
多智能体迭代研究协调器：只负责主循环、收敛判定与最终报告调度。

执行细节分散在三个深度模块：
- AgentRunner    : agent 执行（并行/重试/失败追踪）
- ReportParser   : 报告解析（纯函数 text→data）
- RoundExecutor  : 单轮执行（模板→prompt→调度→落盘）
"""

import sys
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict

from agent_runner import AgentRunner
from report_parser import ReportParser
from round_executor import RoundExecutor


class ResearchCoordinator:
    """协调器：编排轮次序列、判定收敛、生成权威报告。"""

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
        last_round = max(
            int(d.name.split('_')[1]) for d in self.output_dir.glob("round_*")
        )
        final_report = self.round_executor.run_authoritative(
            question, last_round, self.conv_config['judge_agent']
        )

        print(f"\n✅ 研究完成！")
        print(f"📄 最终报告: {final_report}")
        print(f"📊 收敛历史: {self.output_dir / 'convergence_log.json'}")

        return final_report

    @staticmethod
    def _read_texts(reports: Dict[str, Path]) -> Dict[str, str]:
        """把 {agent: path} 读成 {agent: text}"""
        return {
            name: Path(p).read_text(encoding="utf-8")
            for name, p in reports.items()
        }

    def _extract_unified_references(self, comparison_reports: Dict[str, Path]) -> None:
        """提取统一参考资料并写入文件（解析委托给 ReportParser）"""
        print("   📚 提取统一参考资料...")

        all_refs = self.report_parser.extract_references(
            self._read_texts(comparison_reports)
        )

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

        scores = self.report_parser.extract_convergence_scores(
            self._read_texts(comparison_reports)
        )

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


def main():
    if len(sys.argv) < 3:
        print("用法: orchestrator.py <question> <output_dir>")
        sys.exit(1)

    question = sys.argv[1]
    output_dir = Path(sys.argv[2])

    # 配置文件路径
    script_dir = Path(__file__).parent
    config_path = script_dir / "agents" / "agents.yaml"

    coordinator = ResearchCoordinator(config_path, output_dir)
    coordinator.run(question)


if __name__ == "__main__":
    main()
