#!/usr/bin/env python3
"""
AgentRunner 单元测试

通过 mock subprocess.run 测试 agent 执行的核心逻辑：
- 单 agent 执行成功/失败
- 超时重试（Bug #2）
- 失败 agent 追踪与移除（Bug #3）
- 并行/串行执行
- 输出文件路径规则
- 元数据保存
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# 让测试能 import 项目根目录的模块
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_runner import AgentRunner


# ---------- Fixtures ----------

@pytest.fixture
def agents_config():
    """两个 agent 的最小配置"""
    return {
        "alpha": {"cli": "alpha-cli", "prompt_flag": "-p"},
        "beta": {"cli": "beta-cli", "prompt_flag": "-p"},
    }


@pytest.fixture
def exec_config():
    """执行配置：并行、超时 600s、重试 2 次"""
    return {"parallel": True, "timeout": 600, "max_retries": 2}


@pytest.fixture
def runner(agents_config, exec_config, tmp_path):
    """构造一个 AgentRunner，输出到临时目录"""
    return AgentRunner(agents_config, exec_config, tmp_path)


def _ok_result(stdout="# report\nconvergence", returncode=0, stderr=""):
    """构造一个成功的 subprocess 返回值"""
    mock = MagicMock()
    mock.stdout = stdout
    mock.stderr = stderr
    mock.returncode = returncode
    return mock


# ---------- run_single_agent ----------

class TestRunSingleAgent:
    def test_success_writes_output_and_meta(self, runner, tmp_path):
        """成功执行：写入 .md 输出和 .meta.json 元数据"""
        out = tmp_path / "alpha.md"
        with patch("subprocess.run", return_value=_ok_result("hello")):
            runner.run_single_agent("alpha", "prompt", out)

        assert out.read_text(encoding="utf-8") == "hello"
        meta = json.loads(out.with_suffix(".meta.json").read_text(encoding="utf-8"))
        assert meta["agent"] == "alpha"
        assert meta["exit_code"] == 0
        assert meta["retry_count"] == 0

    def test_nonzero_exit_raises(self, runner, tmp_path):
        """非零退出码：抛 RuntimeError"""
        out = tmp_path / "alpha.md"
        with patch("subprocess.run", return_value=_ok_result(returncode=1)):
            with pytest.raises(RuntimeError, match="Exit code 1"):
                runner.run_single_agent("alpha", "prompt", out)

    def test_command_construction_with_flag(self, runner, tmp_path):
        """带 prompt_flag 的命令构造：[cli, flag, prompt]"""
        out = tmp_path / "alpha.md"
        with patch("subprocess.run", return_value=_ok_result()) as m:
            runner.run_single_agent("alpha", "my-prompt", out)
        cmd = m.call_args[0][0]
        assert cmd == ["alpha-cli", "-p", "my-prompt"]

    def test_command_construction_without_flag(self, agents_config, exec_config, tmp_path):
        """无 prompt_flag（如 codex exec）：cli.split() + [prompt]"""
        agents_config["gamma"] = {"cli": "codex exec", "prompt_flag": None}
        runner = AgentRunner(agents_config, exec_config, tmp_path)
        out = tmp_path / "gamma.md"
        with patch("subprocess.run", return_value=_ok_result()) as m:
            runner.run_single_agent("gamma", "my-prompt", out)
        cmd = m.call_args[0][0]
        assert cmd == ["codex", "exec", "my-prompt"]


# ---------- 超时重试（Bug #2） ----------

class TestTimeoutRetry:
    def test_retry_succeeds_on_second_attempt(self, runner, tmp_path):
        """首次超时、第二次成功：共调用 2 次，最终写出结果"""
        out = tmp_path / "alpha.md"
        side_effects = [
            subprocess.TimeoutExpired(cmd=["alpha-cli"], timeout=600),
            _ok_result("recovered"),
        ]
        with patch("subprocess.run", side_effect=side_effects) as m:
            runner.run_single_agent("alpha", "prompt", out)
        assert m.call_count == 2
        assert out.read_text(encoding="utf-8") == "recovered"

    def test_retry_records_retry_count_in_meta(self, runner, tmp_path):
        """重试成功后，元数据记录 retry_count=1"""
        out = tmp_path / "alpha.md"
        side_effects = [
            subprocess.TimeoutExpired(cmd=["alpha-cli"], timeout=600),
            _ok_result("recovered"),
        ]
        with patch("subprocess.run", side_effect=side_effects):
            runner.run_single_agent("alpha", "prompt", out)
        meta = json.loads(out.with_suffix(".meta.json").read_text(encoding="utf-8"))
        assert meta["retry_count"] == 1

    def test_exhausts_retries_then_raises(self, runner, tmp_path):
        """持续超时：max_retries=2 → 共 3 次尝试后抛错"""
        out = tmp_path / "alpha.md"
        timeout_exc = subprocess.TimeoutExpired(cmd=["alpha-cli"], timeout=600)
        with patch("subprocess.run", side_effect=timeout_exc) as m:
            with pytest.raises(RuntimeError, match="max retries exceeded"):
                runner.run_single_agent("alpha", "prompt", out)
        # 初次 + 2 次重试 = 3
        assert m.call_count == 3


# ---------- 失败 agent 追踪（Bug #3） ----------

class TestSuccessfulAgentTracking:
    def test_all_agents_initially_successful(self, runner):
        """初始：所有 agent 都在成功集合中"""
        assert runner.get_successful_agents() == {"alpha", "beta"}

    def test_failed_agent_removed_from_successful(self, runner, tmp_path):
        """beta 失败后从成功集合移除，alpha 保留"""
        def fake_run(cmd, **kwargs):
            if cmd[0] == "beta-cli":
                return _ok_result(returncode=1)  # beta 失败
            return _ok_result("ok")  # alpha 成功

        with patch("subprocess.run", side_effect=fake_run):
            reports = runner.run_agents("prompt", "research", tmp_path)

        assert "alpha" in reports
        assert "beta" not in reports
        assert runner.get_successful_agents() == {"alpha"}

    def test_failed_agent_excluded_next_round(self, runner, tmp_path):
        """beta 失败后，下一轮不再执行 beta"""
        def fail_beta(cmd, **kwargs):
            return _ok_result(returncode=1) if cmd[0] == "beta-cli" else _ok_result("ok")

        with patch("subprocess.run", side_effect=fail_beta):
            runner.run_agents("p1", "research", tmp_path / "r1")

        # 第二轮：beta 已被移除，只有 alpha 会被调用
        calls = []
        def track(cmd, **kwargs):
            calls.append(cmd[0])
            return _ok_result("ok")

        with patch("subprocess.run", side_effect=track):
            runner.run_agents("p2", "comparison", tmp_path / "r2")

        assert "beta-cli" not in calls
        assert "alpha-cli" in calls

    def test_reset_restores_all_agents(self, runner, tmp_path):
        """reset 后恢复所有 agent"""
        def fail_beta(cmd, **kwargs):
            return _ok_result(returncode=1) if cmd[0] == "beta-cli" else _ok_result("ok")
        with patch("subprocess.run", side_effect=fail_beta):
            runner.run_agents("p", "research", tmp_path)
        assert runner.get_successful_agents() == {"alpha"}

        runner.reset_successful_agents()
        assert runner.get_successful_agents() == {"alpha", "beta"}


# ---------- 输出路径规则 ----------

class TestOutputPath:
    def test_research_phase_no_suffix(self, runner, tmp_path):
        """research 阶段：<agent>.md"""
        p = runner._get_output_path("alpha", "research", tmp_path)
        assert p == tmp_path / "alpha.md"

    def test_other_phase_has_suffix(self, runner, tmp_path):
        """其它阶段：<agent>_<phase>.md"""
        p = runner._get_output_path("alpha", "comparison", tmp_path)
        assert p == tmp_path / "alpha_comparison.md"


# ---------- 并行 vs 串行 ----------

class TestParallelAndSerial:
    def test_serial_runs_all_agents(self, agents_config, tmp_path):
        """串行模式：所有 agent 都执行"""
        cfg = {"parallel": False, "timeout": 600, "max_retries": 0}
        runner = AgentRunner(agents_config, cfg, tmp_path)
        with patch("subprocess.run", return_value=_ok_result("ok")):
            reports = runner.run_agents("prompt", "research", tmp_path)
        assert set(reports.keys()) == {"alpha", "beta"}

    def test_parallel_runs_all_agents(self, runner, tmp_path):
        """并行模式：所有 agent 都执行"""
        with patch("subprocess.run", return_value=_ok_result("ok")):
            reports = runner.run_agents("prompt", "research", tmp_path)
        assert set(reports.keys()) == {"alpha", "beta"}

    def test_agent_filter_restricts_execution(self, runner, tmp_path):
        """agent_filter：只执行指定 agent"""
        with patch("subprocess.run", return_value=_ok_result("ok")):
            reports = runner.run_agents(
                "prompt", "research", tmp_path, agent_filter={"alpha"}
            )
        assert set(reports.keys()) == {"alpha"}

    def test_empty_runnable_returns_empty(self, runner, tmp_path):
        """无可执行 agent 时返回空字典，不报错"""
        with patch("subprocess.run", return_value=_ok_result("ok")):
            reports = runner.run_agents(
                "prompt", "research", tmp_path, agent_filter=set()
            )
        assert reports == {}

