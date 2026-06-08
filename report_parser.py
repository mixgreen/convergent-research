#!/usr/bin/env python3
"""
Report Parser Module
纯解析模块：从 agent 输出的 markdown 文本中提取结构化数据。

设计原则：
- 纯函数，text in / structured-data out
- 无文件 I/O、无状态、不依赖配置
- 所有方法都可以用一段字符串直接测试（接口即测试面）

注意：当前依赖 markdown 章节标题做启发式解析（脆弱点）。
未来若 agent 改为输出结构化 JSON（候选 #3），可在此模块内
增加 JSON 优先、markdown 降级的解析路径，调用方无感知。
"""

import re
from typing import Dict, List


class ReportParser:
    """纯解析器：把 agent 报告文本解析为结构化数据。

    接口（调用方只需知道这些）:
    - format_for_prompt(reports)        -> str        拼接报告供 prompt 使用
    - extract_references(reports)       -> list[str]  统一参考资料
    - extract_comparison_summary(...)   -> dict        对比摘要（精炼轮用）
    - extract_convergence_scores(...)   -> list[float] 各 agent 收敛自评分

    全部为 staticmethod —— 无状态、无副作用，便于独立测试。
    """

    # 参考资料章节的多种标题写法
    _REFERENCE_MARKERS = [
        "## 5. 统一参考资料清单",
        "## 统一参考资料清单",
        "## 5. 参考资料",
        "## 参考资料",
    ]

    # 列表项中应被过滤的分隔符
    _SEPARATORS = {"--", "---", "..."}

    @staticmethod
    def format_for_prompt(reports: Dict[str, str]) -> str:
        """把多个 agent 的报告拼接为 prompt 片段

        Args:
            reports: {agent_name: report_text}

        Returns:
            形如 "### Agent: x\n\n<text>\n\n---\n" 的拼接字符串
        """
        formatted = []
        for agent_name, content in reports.items():
            formatted.append(f"### Agent: {agent_name}\n\n{content}\n\n---\n")
        return "\n".join(formatted)

    @classmethod
    def extract_references(cls, reports: Dict[str, str]) -> List[str]:
        """从所有对比报告中提取并去重统一参考资料清单

        Args:
            reports: {agent_name: comparison_report_text}

        Returns:
            去重并排序后的参考资料列表（可能为空）
        """
        all_refs = set()
        for content in reports.values():
            section = cls._find_section(content, cls._REFERENCE_MARKERS)
            if not section:
                continue
            for line in section.split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("*"):
                    ref = line[1:].strip()
                    if ref and ref not in cls._SEPARATORS:
                        all_refs.add(ref)
        return sorted(all_refs)

    @staticmethod
    def extract_comparison_summary(reports: Dict[str, str]) -> Dict:
        """从对比报告中提取摘要（Bug #1：替代塞入完整报告）

        Args:
            reports: {agent_name: comparison_report_text}

        Returns:
            {
              'consensus_facts': str,          # 共识事实章节
              'supplementary_angles': str,     # 补充角度章节
              'errors_to_fix': {agent: str},   # 每个 agent 的针对性反馈
            }
        """
        summary = {
            "consensus_facts": "",
            "supplementary_angles": "",
            "errors_to_fix": {},
        }

        if not reports:
            return summary

        # 共识与补充角度：从任一报告提取（各报告内容应一致）
        first_report = next(iter(reports.values()))
        summary["consensus_facts"] = ReportParser._section_after(
            first_report, "## 2. 已达成共识的事实"
        )
        summary["supplementary_angles"] = ReportParser._section_after(
            first_report, "## 4. 补充角度"
        )

        # 每个 agent 的针对性反馈：扫描所有报告的"分歧点分析"章节
        for agent_name in reports.keys():
            feedback = []
            for report in reports.values():
                section = ReportParser._section_after(report, "## 3. 分歧点分析")
                if not section:
                    continue
                for para in section.split("\n\n"):
                    if agent_name in para:
                        feedback.append(para.strip())
            summary["errors_to_fix"][agent_name] = (
                "\n\n".join(feedback) if feedback else "（无明确错误指出）"
            )

        return summary

    @staticmethod
    def extract_convergence_scores(reports: Dict[str, str]) -> List[float]:
        """从每份对比报告提取收敛自评分（0.0-1.0）

        Args:
            reports: {agent_name: comparison_report_text}

        Returns:
            提取到的分数列表（找不到的 agent 跳过，不计入）
        """
        scores = []
        for content in reports.values():
            for line in content.split("\n"):
                if "收敛分数" in line or "convergence" in line.lower():
                    match = re.search(r"0\.\d+|1\.0", line)
                    if match:
                        scores.append(float(match.group()))
                        break
        return scores

    # ---------- 内部辅助 ----------

    @staticmethod
    def _find_section(content: str, markers: List[str]) -> str:
        """按多个候选标题查找章节，返回到下一个 '##' 之前的内容"""
        for marker in markers:
            if marker in content:
                section = content.split(marker)[1]
                return section.split("##")[0]
        return ""

    @staticmethod
    def _section_after(content: str, marker: str) -> str:
        """提取单个标题之后、到下一个 '##' 之前的内容（strip 后）"""
        if marker in content:
            section = content.split(marker)[1]
            return section.split("##")[0].strip()
        return ""
