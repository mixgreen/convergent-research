#!/usr/bin/env python3
"""
RoundExecutor 单元测试

策略：
- mock AgentRunner（避免真实 subprocess），用真实 ReportParser
- 用临时目录放 prompt 模板和输出
- 覆盖：三种轮次的 prompt 构造、agent 调度、元数据落盘、报告加载、失败 agent 跳过
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from round_executor import RoundExecutor
from report_parser import ReportParser


# ---------- Fixtures ----------

@pytest.fixture
def agents():
    return {"alpha": {"cli": "a"}, "beta": {"cli": "b"}}


@pytest.fixture
def prompt_dir(tmp_path):
    """写入三个最小 prompt 模板"""
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "round_research.md").write_text("研究：{question}", encoding="utf-8")
    (d / "round_comparison.md").write_text(
        "对比 第{round_num}轮 {num_agents}个agent 问题:{question}\n{reports}",
        encoding="utf-8",
    )
    (d / "round_refine_summary.md").write_text(
        "精炼 第{round_num}轮 prev:{prev_research_round} {question} "
        "我的报告:{your_previous_report} 共识:{consensus_facts} "
        "反馈:{agent_feedback} 错误:{errors_to_fix} "
        "补充:{supplementary_angles} 参考:{unified_references}",
        encoding="utf-8",
    )
    (d / "authoritative.md").write_text(
        "权威 {last_round}轮 {num_agents}agent 问题:{question}\n{reports}",
        encoding="utf-8",
    )
    return d


@pytest.fixture
def output_dir(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


@pytest.fixture
def mock_runner(agents):
    """模拟 AgentRunner：run_agents 真写文件并返回路径；记录调用的 prompt"""
    runner = MagicMock()
    runner.successful_agents = set(agents.keys())
    runner.captured_prompts = []

    def fake_run_agents(prompt, phase, out_dir, agent_filter=None):
        runner.captured_prompts.append((phase, prompt))
        result = {}
        for name in agents.keys():
            if name not in runner.successful_agents:
                continue
            p = out_dir / (f"{name}.md" if phase == "research" else f"{name}_{phase}.md")
            p.write_text(f"{name} 的 {phase} 报告", encoding="utf-8")
            result[name] = p
        return result

    def fake_run_single(name, prompt, out_path, retry_count=0):
        runner.captured_prompts.append(("single", prompt))
        out_path.write_text(f"{name} refined", encoding="utf-8")

    runner.run_agents.side_effect = fake_run_agents
    runner.run_single_agent.side_effect = fake_run_single
    return runner


@pytest.fixture
def executor(mock_runner, agents, prompt_dir, output_dir):
    return RoundExecutor(
        agent_runner=mock_runner,
        report_parser=ReportParser(),
        agents=agents,
        prompt_dir=prompt_dir,
        output_dir=output_dir,
    )


# ---------- run_research ----------

class TestRunResearch:
    def test_creates_dir_and_runs_agents(self, executor, output_dir):
        reports = executor.run_research(1, "什么是DMA")
        assert set(reports.keys()) == {"alpha", "beta"}
        assert (output_dir / "round_01" / "research").exists()

    def test_prompt_contains_question(self, executor, mock_runner):
        executor.run_research(1, "什么是DMA")
        phase, prompt = mock_runner.captured_prompts[0]
        assert phase == "research"
        assert "什么是DMA" in prompt

    def test_saves_round_metadata(self, executor, output_dir):
        executor.run_research(1, "q")
        meta = output_dir / "round_01" / "metadata.json"
        assert meta.exists()
        data = json.loads(meta.read_text(encoding="utf-8"))
        assert data["round"] == 1
        assert data["phase"] == "research"


# ---------- run_comparison ----------

class TestRunComparison:
    def test_prompt_includes_prev_reports_and_count(self, executor, mock_runner):
        prev = {"alpha": "报告A", "beta": "报告B"}
        executor.run_comparison(2, "q", prev)
        phase, prompt = mock_runner.captured_prompts[0]
        assert phase == "comparison"
        assert "2个agent" in prompt
        assert "报告A" in prompt and "报告B" in prompt


# ---------- run_refine ----------

class TestRunRefine:
    def test_refine_runs_per_agent(self, executor, mock_runner, output_dir):
        comparison = {
            "alpha": "## 2. 已达成共识的事实\n- 一致\n## 3. 分歧点分析\nalpha 错了\n",
            "beta": "## 2. 已达成共识的事实\n- 一致\n",
        }
        prev_research = {"alpha": "旧A", "beta": "旧B"}
        reports = executor.run_refine(3, "q", prev_research, comparison, "参考清单")
        assert set(reports.keys()) == {"alpha", "beta"}
        # 每个 agent 各调用一次 run_single_agent
        single_calls = [c for c in mock_runner.captured_prompts if c[0] == "single"]
        assert len(single_calls) == 2

    def test_refine_skips_failed_agent(self, executor, mock_runner):
        """beta 已失败 → 只精炼 alpha（Bug #3）"""
        mock_runner.successful_agents = {"alpha"}
        comparison = {"alpha": "## 3. 分歧点分析\nalpha\n"}
        reports = executor.run_refine(3, "q", {}, comparison, None)
        assert set(reports.keys()) == {"alpha"}

    def test_refine_injects_feedback_and_refs(self, executor, mock_runner):
        comparison = {"alpha": "## 3. 分歧点分析\n\nalpha 的方向反了\n"}
        executor.run_refine(3, "q", {"alpha": "旧"}, comparison, "REF清单")
        single = [p for ph, p in mock_runner.captured_prompts if ph == "single"][0]
        assert "方向反了" in single
        assert "REF清单" in single
        assert "旧" in single  # your_previous_report


# ---------- load_reports ----------

class TestLoadReports:
    def test_empty_when_no_round(self, executor):
        assert executor.load_reports(99) == {}

    def test_loads_research_reports(self, executor, output_dir):
        executor.run_research(1, "q")
        loaded = executor.load_reports(1)
        assert set(loaded.keys()) == {"alpha", "beta"}
        assert "research 报告" in loaded["alpha"]

    def test_loads_comparison_reports_with_suffix(self, executor):
        executor.run_comparison(2, "q", {"alpha": "x", "beta": "y"})
        loaded = executor.load_reports(2)
        assert set(loaded.keys()) == {"alpha", "beta"}
        assert "comparison 报告" in loaded["alpha"]


# ---------- run_authoritative ----------

class TestRunAuthoritative:
    def test_generates_final_report(self, executor, mock_runner, output_dir):
        # 先造一轮报告供加载
        executor.run_research(1, "q")
        path = executor.run_authoritative("什么是DMA", last_round=1, judge_agent="alpha")
        assert path == output_dir / "authoritative" / "final_report.md"
        assert path.exists()

    def test_prompt_includes_reports_and_counts(self, executor, mock_runner):
        executor.run_research(1, "q")
        executor.run_authoritative("什么是DMA", last_round=1, judge_agent="alpha")
        single = [p for ph, p in mock_runner.captured_prompts if ph == "single"][-1]
        assert "什么是DMA" in single
        assert "2agent" in single  # alpha + beta 的报告数
        assert "research 报告" in single  # 报告内容被拼入

