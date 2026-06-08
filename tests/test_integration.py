#!/usr/bin/env python3
"""
端到端集成测试

验证四个模块（Coordinator + RoundExecutor + AgentRunner + ReportParser）
通过完整的多轮流程正确协作。subprocess 被 mock，不启动真实 agent。

覆盖：
- 完整跑通：研究 → 对比 → 收敛 → 权威报告
- 收敛判定驱动循环终止
- 失败 agent 不阻断流程（Bug #3 跨模块）
- 产物落盘（各轮目录、收敛日志、最终报告）
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import ResearchCoordinator


# ---------- Fixtures ----------

@pytest.fixture
def project(tmp_path):
    """搭一个最小但完整的项目：agents.yaml + prompts/，返回 config_path"""
    root = tmp_path / "proj"
    (root / "agents").mkdir(parents=True)
    (root / "prompts").mkdir()

    config = {
        "agents": {
            "alpha": {"cli": "alpha-cli", "prompt_flag": "-p"},
            "beta": {"cli": "beta-cli", "prompt_flag": "-p"},
        },
        "execution": {"parallel": False, "timeout": 600, "max_retries": 0},
        "convergence": {
            "threshold": 0.85,
            "min_rounds": 2,
            "max_rounds": 10,
            "judge_agent": "alpha",
        },
    }
    (root / "agents" / "agents.yaml").write_text(
        yaml.safe_dump(config), encoding="utf-8"
    )

    prompts = root / "prompts"
    (prompts / "round_research.md").write_text("研究:{question}", encoding="utf-8")
    (prompts / "round_comparison.md").write_text(
        "对比:{round_num}/{num_agents}/{question}\n{reports}", encoding="utf-8"
    )
    (prompts / "round_refine_summary.md").write_text(
        "精炼:{round_num}/{prev_research_round}/{question}/"
        "{your_previous_report}/{consensus_facts}/{agent_feedback}/"
        "{errors_to_fix}/{supplementary_angles}/{unified_references}",
        encoding="utf-8",
    )
    (prompts / "authoritative.md").write_text(
        "权威:{last_round}/{num_agents}/{question}\n{reports}", encoding="utf-8"
    )
    return root / "agents" / "agents.yaml"


def make_fake_run(score: float, fail_agents=None):
    """构造一个 subprocess.run 替身：
    - 对比轮的输出里写入指定收敛分数
    - fail_agents 中的 agent 返回非零退出码
    """
    fail_agents = fail_agents or set()

    def fake_run(cmd, **kwargs):
        agent_cli = cmd[0]
        result = MagicMock()
        result.stderr = ""
        if any(agent_cli.startswith(a) for a in fail_agents):
            result.returncode = 1
            result.stdout = ""
            return result
        result.returncode = 0
        # 输出里带上收敛分数 + 标准章节，供 parser 提取
        result.stdout = (
            "# 报告\n"
            "## 2. 已达成共识的事实\n- 一致结论\n"
            "## 3. 分歧点分析\n无\n"
            "## 5. 统一参考资料清单\n- ref.py\n"
            f"## 7. 收敛度自评\n- 收敛分数: {score}\n"
        )
        return result

    return fake_run


# ---------- 完整流程 ----------

class TestEndToEnd:
    def test_converges_and_produces_final_report(self, project, tmp_path):
        """高分立即收敛：第 2 轮达标 → 生成权威报告"""
        out = tmp_path / "out"
        coordinator = ResearchCoordinator(project, out)

        with patch("subprocess.run", side_effect=make_fake_run(0.90)):
            final = coordinator.run("什么是DMA")

        # 最终报告存在
        assert final.exists()
        assert final == out / "authoritative" / "final_report.md"
        # 第 1、2 轮产物落盘
        assert (out / "round_01" / "research").exists()
        assert (out / "round_02" / "comparison").exists()
        # 收敛日志记录且状态为 converged
        assert coordinator.convergence_log[-1]["status"] == "converged"
        assert coordinator.convergence_log[-1]["score"] == 0.90

    def test_low_score_continues_then_refines(self, project, tmp_path):
        """低分不收敛：进入第 3 轮精炼，产物落盘"""
        out = tmp_path / "out"
        coordinator = ResearchCoordinator(project, out)

        # 分数 0.50 < 0.85，但 max_rounds=10 会一直跑——
        # 用 side_effect 序列：前几轮低分，确保至少进了精炼轮
        with patch("subprocess.run", side_effect=make_fake_run(0.50)):
            # 把 max_rounds 调小避免长循环
            coordinator.conv_config["max_rounds"] = 3
            final = coordinator.run("q")

        assert (out / "round_03" / "refined").exists()
        assert final.exists()

    def test_unified_references_extracted(self, project, tmp_path):
        """第 2 轮应提取统一参考资料并落盘"""
        out = tmp_path / "out"
        coordinator = ResearchCoordinator(project, out)
        with patch("subprocess.run", side_effect=make_fake_run(0.90)):
            coordinator.run("q")
        refs = out / "round_02" / "unified_references.md"
        assert refs.exists()
        assert "ref.py" in refs.read_text(encoding="utf-8")

    def test_failed_agent_does_not_block(self, project, tmp_path):
        """beta 全程失败：流程仍跑通，最终报告生成（Bug #3 跨模块验证）"""
        out = tmp_path / "out"
        coordinator = ResearchCoordinator(project, out)
        with patch("subprocess.run",
                   side_effect=make_fake_run(0.90, fail_agents={"beta-cli"})):
            final = coordinator.run("q")
        assert final.exists()
        # beta 已被移除出成功集合
        assert "beta" not in coordinator.successful_agents
        assert "alpha" in coordinator.successful_agents

    def test_convergence_log_persisted(self, project, tmp_path):
        """收敛日志写入 convergence_log.json"""
        out = tmp_path / "out"
        coordinator = ResearchCoordinator(project, out)
        with patch("subprocess.run", side_effect=make_fake_run(0.90)):
            coordinator.run("q")
        log = out / "convergence_log.json"
        assert log.exists()
