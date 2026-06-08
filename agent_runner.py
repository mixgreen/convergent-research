#!/usr/bin/env python3
"""
Agent Runner Module
负责执行 agent 的所有复杂性：并行管理、超时重试、失败追踪
"""

import os
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed


class AgentRunner:
    """深度模块：处理 agent 执行的所有复杂性

    接口（调用方只需知道这些）:
    - run_agents(prompt, phase, agent_filter) -> dict[agent_name, output_path]
    - run_single_agent(agent_name, prompt, output_path) -> None

    实现（调用方无需关心）:
    - 并行/串行策略
    - ThreadPoolExecutor 管理
    - subprocess 调用与超时
    - 失败重试逻辑
    - 输出文件管理
    - 元数据记录
    """

    def __init__(self,
                 agents: Dict[str, Dict],
                 exec_config: Dict,
                 output_dir: Path):
        """初始化 Agent 执行器

        Args:
            agents: agent 配置字典 {agent_name: {cli, prompt_flag, ...}}
            exec_config: 执行配置 {parallel, timeout, max_retries}
            output_dir: 输出根目录
        """
        self.agents = agents
        self.exec_config = exec_config
        self.output_dir = Path(output_dir)

        # 成功 agent 追踪（Bug #3 修复）
        self.successful_agents: Set[str] = set(self.agents.keys())

    def run_agents(self,
                   prompt: str,
                   phase: str,
                   output_dir: Path,
                   agent_filter: Optional[Set[str]] = None) -> Dict[str, Path]:
        """执行多个 agent，返回成功的输出路径

        Args:
            prompt: 要发送给 agent 的 prompt
            phase: 轮次阶段名称 ('research' | 'comparison' | 'refined')
            output_dir: 本轮输出目录
            agent_filter: 可选的 agent 过滤集合（只执行这些 agent）

        Returns:
            成功执行的 agent 输出路径字典 {agent_name: output_path}
        """
        reports = {}
        failed_agents = []

        # 确定要执行的 agent（成功列表 ∩ 过滤列表）
        agents_to_run = [
            a for a in self.agents.keys()
            if a in self.successful_agents and (agent_filter is None or a in agent_filter)
        ]
        total_agents = len(agents_to_run)

        if total_agents == 0:
            print("   ⚠️  没有可执行的 agent")
            return reports

        if self.exec_config['parallel']:
            # 并行执行
            print(f"   🚀 并行启动 {total_agents} 个 agent...")
            reports, failed_agents = self._run_parallel(
                agents_to_run, prompt, phase, output_dir
            )
        else:
            # 串行执行
            print(f"   🚀 串行执行 {total_agents} 个 agent...")
            reports, failed_agents = self._run_serial(
                agents_to_run, prompt, phase, output_dir
            )

        # Bug #3 修复：从成功列表中移除失败的 agent
        for agent in failed_agents:
            if agent in self.successful_agents:
                self.successful_agents.remove(agent)
                print(f"   ⚠️  {agent} 从后续轮次中移除")

        return reports

    def _run_parallel(self,
                      agents_to_run: list[str],
                      prompt: str,
                      phase: str,
                      output_dir: Path) -> tuple[Dict[str, Path], list[str]]:
        """并行执行 agent"""
        reports = {}
        failed_agents = []
        total_agents = len(agents_to_run)

        with ThreadPoolExecutor(max_workers=total_agents) as executor:
            futures = {}
            for agent_name in agents_to_run:
                output_path = self._get_output_path(agent_name, phase, output_dir)
                future = executor.submit(
                    self.run_single_agent, agent_name, prompt, output_path
                )
                futures[future] = (agent_name, output_path)

            completed = 0
            for future in as_completed(futures):
                agent_name, output_path = futures[future]
                completed += 1
                try:
                    future.result()
                    reports[agent_name] = output_path
                    print(f"   ✅ {agent_name} 完成 ({completed}/{total_agents})")
                except Exception as e:
                    failed_agents.append(agent_name)
                    print(f"   ❌ {agent_name} 失败 ({completed}/{total_agents}): {e}")

        return reports, failed_agents

    def _run_serial(self,
                    agents_to_run: list[str],
                    prompt: str,
                    phase: str,
                    output_dir: Path) -> tuple[Dict[str, Path], list[str]]:
        """串行执行 agent"""
        reports = {}
        failed_agents = []
        total_agents = len(agents_to_run)

        for idx, agent_name in enumerate(agents_to_run, 1):
            output_path = self._get_output_path(agent_name, phase, output_dir)
            try:
                self.run_single_agent(agent_name, prompt, output_path)
                reports[agent_name] = output_path
                print(f"   ✅ {agent_name} 完成 ({idx}/{total_agents})")
            except Exception as e:
                failed_agents.append(agent_name)
                print(f"   ❌ {agent_name} 失败 ({idx}/{total_agents}): {e}")

        return reports, failed_agents

    def _get_output_path(self, agent_name: str, phase: str, output_dir: Path) -> Path:
        """获取 agent 输出文件路径"""
        if phase == "research":
            return output_dir / f"{agent_name}.md"
        else:
            return output_dir / f"{agent_name}_{phase}.md"

    def run_single_agent(self,
                         agent_name: str,
                         prompt: str,
                         output_path: Path,
                         retry_count: int = 0) -> None:
        """执行单个 agent（支持超时重试）

        Args:
            agent_name: agent 名称
            prompt: prompt 文本
            output_path: 输出文件路径
            retry_count: 当前重试次数

        Raises:
            RuntimeError: 执行失败或超时重试次数耗尽
        """
        agent_config = self.agents[agent_name]
        cli = agent_config['cli']
        prompt_flag = agent_config.get('prompt_flag')

        # 构建命令
        if prompt_flag:
            cmd = [cli, prompt_flag, prompt]
        else:
            # codex exec 不需要 flag
            cmd = cli.split() + [prompt]

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.exec_config['timeout'],
                cwd=os.getcwd()  # 在当前工作目录执行，让 agent 能访问项目文件
            )

            elapsed = time.time() - start_time

            # 保存完整输出
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result.stdout)

            # 提取 token 信息（如果有）
            tokens = self._extract_token_info(result.stdout, result.stderr)

            # 保存执行元数据
            meta_path = output_path.with_suffix('.meta.json')
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'agent': agent_name,
                    'timestamp': datetime.now().isoformat(),
                    'elapsed_seconds': round(elapsed, 2),
                    'exit_code': result.returncode,
                    'tokens': tokens,
                    'retry_count': retry_count,
                    'stderr': result.stderr[:500] if result.stderr else None
                }, f, indent=2, ensure_ascii=False)

            if result.returncode != 0:
                raise RuntimeError(f"Exit code {result.returncode}")

        except subprocess.TimeoutExpired:
            # Bug #2 修复：超时后重试
            if retry_count < self.exec_config['max_retries']:
                print(f"   ⚠️  {agent_name} 超时，重试 {retry_count + 1}/{self.exec_config['max_retries']}")
                return self.run_single_agent(agent_name, prompt, output_path, retry_count + 1)
            else:
                raise RuntimeError(
                    f"Timeout after {self.exec_config['timeout']}s "
                    f"(max retries exceeded)"
                )
        except Exception as e:
            raise RuntimeError(f"Execution failed: {e}")

    def _extract_token_info(self, stdout: str, stderr: str) -> Optional[Dict]:
        """从输出中提取 token 信息（尽力而为）

        这是一个简单的启发式实现，未来可以改进为每个 agent 的专用解析器。
        """
        import re
        tokens = {}

        for line in (stdout + '\n' + stderr).split('\n'):
            if 'tokens' in line.lower() or 'token' in line.lower():
                numbers = re.findall(r'\d[\d,]*', line)
                if numbers:
                    tokens['raw'] = line.strip()
                    break

        return tokens if tokens else None

    def get_successful_agents(self) -> Set[str]:
        """获取当前成功的 agent 集合（用于外部查询）"""
        return self.successful_agents.copy()

    def reset_successful_agents(self) -> None:
        """重置成功 agent 列表为所有 agent（用于重新开始）"""
        self.successful_agents = set(self.agents.keys())
