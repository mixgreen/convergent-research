#!/usr/bin/env python3
"""
Convergent Research Orchestrator
多智能体迭代研究编排器，支持动态收敛检测
"""

import os
import sys
import json
import yaml
import subprocess
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed


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
        reports_r1 = self._run_research_round(round_num, question)

        # 开始迭代循环
        while round_num < self.conv_config['max_rounds']:
            round_num += 1

            # 偶数轮：对比评估
            if round_num % 2 == 0:
                print(f"\n{'='*60}")
                print(f"第 {round_num} 轮：对比评估")
                print(f"{'='*60}")

                prev_round = round_num - 1
                prev_reports = self._load_reports(prev_round)

                comparison_reports = self._run_comparison_round(
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

                comparison_reports = self._load_reports(comparison_round)
                prev_research_reports = self._load_reports(prev_research_round)

                refined_reports = self._run_refine_round(
                    round_num, question,
                    prev_research_reports, comparison_reports
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

    def _run_research_round(self, round_num: int, question: str) -> Dict[str, Path]:
        """执行研究轮次"""
        round_dir = self.output_dir / f"round_{round_num:02d}" / "research"
        round_dir.mkdir(parents=True, exist_ok=True)

        # 加载 prompt 模板
        prompt_template = self._load_prompt_template("round_research.md")
        prompt = prompt_template.format(question=question)

        # 执行所有 agent
        reports = self._execute_agents(round_dir, prompt, "research")

        return reports

    def _run_comparison_round(self, round_num: int, question: str,
                             prev_reports: Dict[str, str]) -> Dict[str, Path]:
        """执行对比评估轮次"""
        round_dir = self.output_dir / f"round_{round_num:02d}" / "comparison"
        round_dir.mkdir(parents=True, exist_ok=True)

        # 加载 prompt 模板
        prompt_template = self._load_prompt_template("round_comparison.md")

        # 格式化上一轮的报告
        reports_text = self._format_reports_for_prompt(prev_reports)

        prompt = prompt_template.format(
            round_num=round_num,
            num_agents=len(prev_reports),
            question=question,
            reports=reports_text
        )

        # 执行所有 agent
        reports = self._execute_agents(round_dir, prompt, "comparison")

        return reports

    def _run_refine_round(self, round_num: int, question: str,
                         prev_research_reports: Dict[str, str],
                         comparison_reports: Dict[str, str]) -> Dict[str, Path]:
        """执行精炼轮次"""
        round_dir = self.output_dir / f"round_{round_num:02d}" / "refined"
        round_dir.mkdir(parents=True, exist_ok=True)

        # 加载 prompt 模板
        prompt_template = self._load_prompt_template("round_refine.md")

        # 为每个 agent 生成个性化 prompt（包含它自己上一轮的报告）
        reports = {}

        for agent_name in self.agents.keys():
            your_prev_report = prev_research_reports.get(agent_name, "（未找到你的上一轮报告）")
            comparison_text = self._format_reports_for_prompt(comparison_reports)

            prompt = prompt_template.format(
                round_num=round_num,
                prev_research_round=round_num - 2,
                question=question,
                your_previous_report=your_prev_report,
                comparison_reports=comparison_text,
                unified_references=self.unified_references or "（尚未提取）"
            )

            # 单独执行该 agent
            output_path = round_dir / f"{agent_name}_refined.md"
            self._execute_single_agent(agent_name, prompt, output_path)
            reports[agent_name] = output_path

        # 保存元数据
        self._save_metadata(round_dir.parent, round_num, "refined",
                           list(reports.values()))

        return reports

    def _execute_agents(self, output_dir: Path, prompt: str,
                       phase: str) -> Dict[str, Path]:
        """并行或串行执行所有 agent"""
        reports = {}
        total_agents = len(self.agents)

        if self.exec_config['parallel']:
            # 并行执行
            print(f"   🚀 并行启动 {total_agents} 个 agent...")
            with ThreadPoolExecutor(max_workers=total_agents) as executor:
                futures = {}
                for agent_name in self.agents.keys():
                    output_path = output_dir / f"{agent_name}_{phase}.md" if phase != "research" else output_dir / f"{agent_name}.md"
                    future = executor.submit(
                        self._execute_single_agent, agent_name, prompt, output_path
                    )
                    futures[future] = (agent_name, output_path)

                completed = 0
                for future in as_completed(futures):
                    agent_name, output_path = futures[future]
                    try:
                        future.result()
                        reports[agent_name] = output_path
                        completed += 1
                        print(f"   ✅ {agent_name} 完成 ({completed}/{total_agents})")
                    except Exception as e:
                        completed += 1
                        print(f"   ❌ {agent_name} 失败 ({completed}/{total_agents}): {e}")
        else:
            # 串行执行
            for idx, agent_name in enumerate(self.agents.keys(), 1):
                output_path = output_dir / f"{agent_name}_{phase}.md" if phase != "research" else output_dir / f"{agent_name}.md"
                try:
                    self._execute_single_agent(agent_name, prompt, output_path)
                    reports[agent_name] = output_path
                    print(f"   ✅ {agent_name} 完成 ({idx}/{total_agents})")
                except Exception as e:
                    print(f"   ❌ {agent_name} 失败 ({idx}/{total_agents}): {e}")

        # 保存元数据
        self._save_metadata(output_dir.parent,
                           int(output_dir.parent.name.split('_')[1]),
                           phase, list(reports.values()))

        return reports

    def _execute_single_agent(self, agent_name: str, prompt: str,
                             output_path: Path) -> None:
        """执行单个 agent"""
        agent_config = self.agents[agent_name]
        cli = agent_config['cli']
        prompt_flag = agent_config['prompt_flag']

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

            # 保存完整输出（包括元数据）
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
                    'stderr': result.stderr[:500] if result.stderr else None  # 只保留前 500 字符
                }, f, indent=2, ensure_ascii=False)

            if result.returncode != 0:
                raise RuntimeError(f"Exit code {result.returncode}")

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Timeout after {self.exec_config['timeout']}s")
        except Exception as e:
            raise RuntimeError(f"Execution failed: {e}")

    def _extract_token_info(self, stdout: str, stderr: str) -> Optional[Dict]:
        """从输出中提取 token 信息（尽力而为）"""
        # TODO: 针对不同 agent 的输出格式解析 token 信息
        # codex: "tokens used\n18,906"
        # 其他 agent 可能在 stderr 或特定格式中
        tokens = {}

        # 简单示例：查找 "tokens used" 行
        for line in (stdout + '\n' + stderr).split('\n'):
            if 'tokens' in line.lower() or 'token' in line.lower():
                # 尝试提取数字
                import re
                numbers = re.findall(r'\d[\d,]*', line)
                if numbers:
                    tokens['raw'] = line.strip()
                    break

        return tokens if tokens else None

    def _load_reports(self, round_num: int) -> Dict[str, str]:
        """加载指定轮次的所有报告内容"""
        round_dir = self.output_dir / f"round_{round_num:02d}"
        reports = {}

        # 确定子目录（research / comparison / refined）
        if (round_dir / "research").exists():
            subdir = round_dir / "research"
        elif (round_dir / "comparison").exists():
            subdir = round_dir / "comparison"
        elif (round_dir / "refined").exists():
            subdir = round_dir / "refined"
        else:
            return reports

        for agent_name in self.agents.keys():
            # 尝试多种文件名模式
            patterns = [
                f"{agent_name}.md",
                f"{agent_name}_*.md"
            ]

            for pattern in patterns:
                files = list(subdir.glob(pattern))
                if files:
                    with open(files[0], 'r', encoding='utf-8') as f:
                        reports[agent_name] = f.read()
                    break

        return reports

    def _format_reports_for_prompt(self, reports: Dict[str, str]) -> str:
        """格式化报告用于 prompt"""
        formatted = []
        for agent_name, content in reports.items():
            formatted.append(f"### Agent: {agent_name}\n\n{content}\n\n---\n")
        return "\n".join(formatted)

    def _extract_unified_references(self, comparison_reports: Dict[str, Path]) -> None:
        """从第一次对比报告中提取统一参考资料"""
        print("   📚 提取统一参考资料...")

        # 读取所有对比报告
        all_refs = set()
        for report_path in comparison_reports.values():
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 尝试多种章节标题格式
                section_markers = [
                    "## 5. 统一参考资料清单",
                    "## 统一参考资料清单",
                    "## 5. 参考资料",
                    "## 参考资料"
                ]

                section = None
                for marker in section_markers:
                    if marker in content:
                        section = content.split(marker)[1]
                        section = section.split("##")[0]  # 到下一个章节为止
                        break

                if section:
                    # 提取列表项
                    for line in section.split('\n'):
                        line = line.strip()
                        if line.startswith('-') or line.startswith('*'):
                            ref = line[1:].strip()
                            # 过滤掉空行和分隔符
                            if ref and ref not in ['--', '---', '...']:
                                all_refs.add(ref)

        # 保存统一参考资料
        refs_path = self.output_dir / "round_02" / "unified_references.md"
        with open(refs_path, 'w', encoding='utf-8') as f:
            f.write("# 统一参考资料清单\n\n")
            f.write("（从第 2 轮对比报告中提取，供后续轮次使用）\n\n")
            if all_refs:
                for ref in sorted(all_refs):
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
        """评估收敛度"""
        print("   🔍 评估收敛度...")

        # 读取所有对比报告的"收敛度自评"章节
        scores = []
        for agent_name, report_path in comparison_reports.items():
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 查找 "收敛分数" 行
                for line in content.split('\n'):
                    if '收敛分数' in line or 'convergence' in line.lower():
                        # 尝试提取 0.0-1.0 的数字
                        import re
                        match = re.search(r'0\.\d+|1\.0', line)
                        if match:
                            scores.append(float(match.group()))
                            break

        # 计算平均分数
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # 判断状态
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

    def _save_metadata(self, round_dir: Path, round_num: int,
                      phase: str, report_paths: List[Path]) -> None:
        """保存轮次元数据"""
        meta_path = round_dir / "metadata.json"

        # 汇总所有 agent 的 token 信息
        agents_meta = {}
        for report_path in report_paths:
            meta_file = report_path.with_suffix('.meta.json')
            if meta_file.exists():
                with open(meta_file, 'r', encoding='utf-8') as f:
                    agents_meta[report_path.stem] = json.load(f)

        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump({
                'round': round_num,
                'phase': phase,
                'timestamp': datetime.now().isoformat(),
                'agents': agents_meta
            }, f, indent=2, ensure_ascii=False)

    def _generate_authoritative_report(self, question: str) -> Path:
        """生成最终权威报告"""
        auth_dir = self.output_dir / "authoritative"
        auth_dir.mkdir(exist_ok=True)

        # 找到最后一轮的报告
        last_round = max([
            int(d.name.split('_')[1])
            for d in self.output_dir.glob("round_*")
        ])

        final_reports = self._load_reports(last_round)

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

{self._format_reports_for_prompt(final_reports)}

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
        self._execute_single_agent(judge_agent, prompt, output_path)

        return output_path

    def _load_prompt_template(self, filename: str) -> str:
        """加载 prompt 模板"""
        template_path = self.config_path.parent.parent / "prompts" / filename
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()


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
