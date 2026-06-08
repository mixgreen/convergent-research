#!/usr/bin/env python3
"""
Round Executor Module
负责单个轮次的执行：模板加载 → prompt 构造 → agent 调用 → 元数据保存。

设计：
- 依赖注入 AgentRunner（执行）和 ReportParser（解析/格式化）
- 三种轮次类型各一个方法，调用方（Coordinator）只管按序调度
- 轮次间状态（如 unified_references）由调用方传入，本模块尽量无状态
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from agent_runner import AgentRunner
from report_parser import ReportParser


class RoundExecutor:
    """执行单个轮次的所有步骤。

    接口:
    - run_research(round_num, question)                      -> dict[agent, path]
    - run_comparison(round_num, question, prev_reports)      -> dict[agent, path]
    - run_refine(round_num, question, prev_research,
                 comparison_reports, unified_references)     -> dict[agent, path]
    - load_reports(round_num)                                -> dict[agent, text]

    实现细节（调用方无需关心）：模板加载、prompt 构造、agent 调度、元数据落盘。
    """

    def __init__(self,
                 agent_runner: AgentRunner,
                 report_parser: ReportParser,
                 agents: Dict[str, Dict],
                 prompt_dir: Path,
                 output_dir: Path):
        self.agent_runner = agent_runner
        self.report_parser = report_parser
        self.agents = agents
        self.prompt_dir = Path(prompt_dir)
        self.output_dir = Path(output_dir)

    # ---------- 三种轮次 ----------

    def run_research(self, round_num: int, question: str) -> Dict[str, Path]:
        """第 1 轮：各 agent 独立研究"""
        round_dir = self._round_subdir(round_num, "research")

        prompt_template = self._load_prompt_template("round_research.md")
        prompt = prompt_template.format(question=question)

        return self._execute_agents(round_dir, prompt, "research")

    def run_comparison(self, round_num: int, question: str,
                       prev_reports: Dict[str, str]) -> Dict[str, Path]:
        """偶数轮：对比评估上一轮的报告"""
        round_dir = self._round_subdir(round_num, "comparison")

        prompt_template = self._load_prompt_template("round_comparison.md")
        reports_text = self.report_parser.format_for_prompt(prev_reports)
        prompt = prompt_template.format(
            round_num=round_num,
            num_agents=len(prev_reports),
            question=question,
            reports=reports_text,
        )

        return self._execute_agents(round_dir, prompt, "comparison")

    def run_refine(self, round_num: int, question: str,
                   prev_research_reports: Dict[str, str],
                   comparison_reports: Dict[str, str],
                   unified_references: Optional[str] = None) -> Dict[str, Path]:
        """奇数轮（≥3）：基于对比摘要精炼报告（Bug #1：用精简模板）"""
        round_dir = self._round_subdir(round_num, "refined")

        prompt_template = self._load_prompt_template("round_refine_summary.md")

        print("   📊 提取对比报告摘要...")
        summary = self.report_parser.extract_comparison_summary(comparison_reports)

        reports = {}
        for agent_name in self.agents.keys():
            # Bug #3：跳过已失败的 agent
            if agent_name not in self.agent_runner.successful_agents:
                continue

            your_prev_report = prev_research_reports.get(
                agent_name, "（未找到你的上一轮报告）"
            )
            agent_feedback = summary["errors_to_fix"].get(
                agent_name, "（无明确错误指出）"
            )

            prompt = prompt_template.format(
                round_num=round_num,
                prev_research_round=round_num - 2,
                question=question,
                your_previous_report=your_prev_report,
                consensus_facts=summary["consensus_facts"],
                agent_feedback=agent_feedback,
                errors_to_fix=agent_feedback,
                supplementary_angles=summary["supplementary_angles"],
                unified_references=unified_references or "（尚未提取）",
            )

            output_path = round_dir / f"{agent_name}_refined.md"
            self.agent_runner.run_single_agent(agent_name, prompt, output_path)
            reports[agent_name] = output_path

        self._save_metadata(round_dir.parent, round_num, "refined",
                            list(reports.values()))
        return reports

    # ---------- 报告加载 ----------

    def load_reports(self, round_num: int) -> Dict[str, str]:
        """加载指定轮次所有 agent 的报告文本"""
        round_dir = self.output_dir / f"round_{round_num:02d}"
        reports = {}

        # 确定子目录（research / comparison / refined）
        for sub in ("research", "comparison", "refined"):
            if (round_dir / sub).exists():
                subdir = round_dir / sub
                break
        else:
            return reports

        for agent_name in self.agents.keys():
            for pattern in (f"{agent_name}.md", f"{agent_name}_*.md"):
                files = list(subdir.glob(pattern))
                if files:
                    reports[agent_name] = files[0].read_text(encoding="utf-8")
                    break

        return reports

    # ---------- 内部辅助 ----------

    def _round_subdir(self, round_num: int, phase: str) -> Path:
        """创建并返回 round_NN/<phase> 目录"""
        round_dir = self.output_dir / f"round_{round_num:02d}" / phase
        round_dir.mkdir(parents=True, exist_ok=True)
        return round_dir

    def _execute_agents(self, output_dir: Path, prompt: str,
                        phase: str) -> Dict[str, Path]:
        """执行所有 agent（委托 AgentRunner）并保存本轮元数据"""
        reports = self.agent_runner.run_agents(prompt, phase, output_dir)
        self._save_metadata(
            output_dir.parent,
            int(output_dir.parent.name.split("_")[1]),
            phase,
            list(reports.values()),
        )
        return reports

    def _load_prompt_template(self, filename: str) -> str:
        """加载 prompt 模板"""
        template_path = self.prompt_dir / filename
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()

    def _save_metadata(self, round_dir: Path, round_num: int,
                       phase: str, report_paths: List[Path]) -> None:
        """保存轮次元数据（汇总各 agent 的 .meta.json）"""
        meta_path = round_dir / "metadata.json"

        agents_meta = {}
        for report_path in report_paths:
            meta_file = report_path.with_suffix(".meta.json")
            if meta_file.exists():
                with open(meta_file, "r", encoding="utf-8") as f:
                    agents_meta[report_path.stem] = json.load(f)

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "round": round_num,
                "phase": phase,
                "timestamp": datetime.now().isoformat(),
                "agents": agents_meta,
            }, f, indent=2, ensure_ascii=False)
