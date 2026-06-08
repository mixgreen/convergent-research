#!/usr/bin/env python3
"""
ReportParser 单元测试

纯解析模块，无需 mock —— 直接喂字符串、断言输出。
覆盖：
- format_for_prompt 拼接
- extract_references 多标题/去重/分隔符过滤
- extract_comparison_summary 共识/补充/针对性反馈
- extract_convergence_scores 中英文/缺失/多分数
- 边界：空输入、找不到章节
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from report_parser import ReportParser


# ---------- format_for_prompt ----------

class TestFormatForPrompt:
    def test_joins_agents_with_headers(self):
        reports = {"alpha": "hello", "beta": "world"}
        out = ReportParser.format_for_prompt(reports)
        assert "### Agent: alpha" in out
        assert "### Agent: beta" in out
        assert "hello" in out and "world" in out

    def test_empty_returns_empty_string(self):
        assert ReportParser.format_for_prompt({}) == ""


# ---------- extract_references ----------

class TestExtractReferences:
    def test_extracts_and_sorts_dedup(self):
        reports = {
            "a": "## 5. 统一参考资料清单\n- dds.py\n- duc.py\n",
            "b": "## 统一参考资料清单\n- duc.py\n- cossin.py\n",  # duc.py 重复
        }
        refs = ReportParser.extract_references(reports)
        assert refs == ["cossin.py", "dds.py", "duc.py"]  # 去重 + 排序

    def test_supports_alternate_markers(self):
        reports = {"a": "## 参考资料\n- foo.py\n"}
        assert ReportParser.extract_references(reports) == ["foo.py"]

    def test_filters_separators(self):
        reports = {"a": "## 参考资料\n- ---\n- foo.py\n- ...\n"}
        assert ReportParser.extract_references(reports) == ["foo.py"]

    def test_supports_asterisk_bullets(self):
        reports = {"a": "## 参考资料\n* bar.py\n"}
        assert ReportParser.extract_references(reports) == ["bar.py"]

    def test_no_section_returns_empty(self):
        reports = {"a": "## 1. 概述\n没有参考资料章节\n"}
        assert ReportParser.extract_references(reports) == []

    def test_stops_at_next_section(self):
        """参考资料后面紧跟另一章节，不应越界提取"""
        reports = {"a": "## 参考资料\n- foo.py\n## 6. 下一节\n- 不应被收录\n"}
        assert ReportParser.extract_references(reports) == ["foo.py"]


# ---------- extract_comparison_summary ----------

class TestExtractComparisonSummary:
    def test_extracts_consensus_and_supplementary(self):
        reports = {
            "a": (
                "## 2. 已达成共识的事实\n- DMA 无法消除延迟\n\n"
                "## 3. 分歧点分析\n关于 a 的级数有分歧\n\n"
                "## 4. 补充角度\nagy 提出频率路径\n"
            )
        }
        summary = ReportParser.extract_comparison_summary(reports)
        assert "DMA 无法消除延迟" in summary["consensus_facts"]
        assert "频率路径" in summary["supplementary_angles"]

    def test_per_agent_feedback_found(self):
        reports = {
            "alpha": "## 3. 分歧点分析\n\nalpha 的方向写反了\n\nbeta 计数边界不同\n",
            "beta": "## 3. 分歧点分析\n\nbeta 计数边界不同\n",
        }
        summary = ReportParser.extract_comparison_summary(reports)
        assert "方向写反" in summary["errors_to_fix"]["alpha"]
        assert "计数边界" in summary["errors_to_fix"]["beta"]

    def test_no_feedback_default_message(self):
        reports = {"alpha": "## 3. 分歧点分析\n\n无人提及\n"}
        summary = ReportParser.extract_comparison_summary(reports)
        assert summary["errors_to_fix"]["alpha"] == "（无明确错误指出）"

    def test_empty_reports_returns_skeleton(self):
        summary = ReportParser.extract_comparison_summary({})
        assert summary["consensus_facts"] == ""
        assert summary["supplementary_angles"] == ""
        assert summary["errors_to_fix"] == {}

    def test_missing_sections_yield_empty_strings(self):
        reports = {"a": "## 1. 只有概述\n没有共识章节\n"}
        summary = ReportParser.extract_comparison_summary(reports)
        assert summary["consensus_facts"] == ""
        assert summary["supplementary_angles"] == ""


# ---------- extract_convergence_scores ----------

class TestExtractConvergenceScores:
    def test_chinese_label(self):
        reports = {"a": "## 7. 收敛度自评\n- 收敛分数: 0.85\n"}
        assert ReportParser.extract_convergence_scores(reports) == [0.85]

    def test_english_label(self):
        reports = {"a": "convergence score: 0.92\n"}
        assert ReportParser.extract_convergence_scores(reports) == [0.92]

    def test_handles_1_0(self):
        reports = {"a": "收敛分数: 1.0\n"}
        assert ReportParser.extract_convergence_scores(reports) == [1.0]

    def test_multiple_agents(self):
        reports = {
            "a": "收敛分数: 0.75",
            "b": "收敛分数: 0.85",
            "c": "收敛分数: 0.82",
        }
        scores = ReportParser.extract_convergence_scores(reports)
        assert sorted(scores) == [0.75, 0.82, 0.85]

    def test_missing_score_skipped(self):
        """没有分数的报告被跳过，不计入（不污染平均值）"""
        reports = {"a": "收敛分数: 0.80", "b": "本报告未给出分数"}
        assert ReportParser.extract_convergence_scores(reports) == [0.80]

    def test_first_match_per_report(self):
        """每份报告只取第一个匹配，避免重复计分"""
        reports = {"a": "收敛分数: 0.80\n后文又提到 0.99"}
        assert ReportParser.extract_convergence_scores(reports) == [0.80]

    def test_empty_returns_empty(self):
        assert ReportParser.extract_convergence_scores({}) == []
