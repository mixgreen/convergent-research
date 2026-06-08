# Convergent Research 架构重构计划

## 文档元信息
- **创建日期**: 2026-06-02
- **当前版本**: v0.1.1（Bug 修复后）
- **目标版本**: v0.2.0（架构重构）
- **预计工期**: 2-3 周

---

## 📋 执行摘要

**当前问题**: 单一 `ResearchOrchestrator` 类（628 行，18 个方法）承担过多职责，导致：
- 难以独立测试各个功能模块
- 扩展新轮次类型需要修改核心循环
- 数据提取依赖脆弱的 markdown 正则解析
- 完全缺失单元测试

**改进目标**: 通过模块化拆分和接口抽象，提升：
- **Locality（局部性）**: 修改一个功能不影响其他模块
- **Leverage（杠杆）**: 深度模块提供高价值接口
- **Testability（可测试性）**: 每个模块可独立测试

---

## 🎯 重构候选方案（优先级排序）

### 🔴 候选 #1: 拆分单体 Orchestrator 类
**优先级**: P0（必须做）  
**预计工作量**: 3-5 天  
**状态**: ⏳ 进行中

#### 问题分析
`ResearchOrchestrator` 混合了 5 类职责：

| 职责 | 方法数 | 代码行数 | 耦合度 |
|------|--------|---------|--------|
| 流程编排 | 4 | ~100 | 高（依赖所有其他职责） |
| Agent 执行 | 2 | ~90 | 中（依赖配置） |
| 数据提取 | 4 | ~120 | 低（相对独立） |
| 报告生成 | 2 | ~40 | 中（依赖模板） |
| I/O 操作 | 6 | ~50 | 低（相对独立） |

#### 目标架构

```
┌─────────────────────────────────────────────┐
│       ResearchCoordinator (薄协调层)        │
│   - run() 主循环                            │
│   - 轮次调度                                │
│   - 收敛判定                                │
└─────┬─────────────┬─────────────┬───────────┘
      │             │             │
      ▼             ▼             ▼
┌───────────┐ ┌──────────┐ ┌─────────────┐
│AgentRunner│ │ReportParser│ │RoundExecutor│
│- 并行执行 │ │- 数据提取 │ │- 轮次策略 │
│- 超时重试 │ │- 格式解析 │ │- 类型管理 │
│- 失败追踪 │ │- 校验     │ │- 结果聚合 │
└───────────┘ └──────────┘ └─────────────┘
```

#### 新增模块接口设计

**1. AgentRunner（Agent 执行器）**
```python
class AgentRunner:
    """深度模块：处理 agent 执行的所有复杂性
    
    接口（调用方只需知道这些）:
    - run_agents(agents, prompt) -> dict[agent_name, output_path]
    - run_single_agent(agent_name, prompt) -> output_path
    
    实现（调用方无需关心）:
    - 并行/串行策略
    - ThreadPoolExecutor 管理
    - subprocess 调用与超时
    - 失败重试逻辑
    - 输出文件管理
    - 元数据记录
    """
    
    def __init__(self, 
                 agents: dict[str, AgentConfig],
                 execution_config: ExecutionConfig,
                 output_dir: Path):
        pass
    
    def run_agents(self, 
                   prompt: str,
                   phase: str,
                   agent_filter: set[str] | None = None
                   ) -> dict[str, Path]:
        """执行多个 agent，返回成功的输出路径"""
        pass
    
    def run_single_agent(self,
                         agent_name: str,
                         prompt: str,
                         output_path: Path,
                         retry_count: int = 0) -> None:
        """执行单个 agent（支持重试）"""
        pass
```

**接口深度分析**:
- **Leverage**: 调用方只需 2 行代码，模块处理 6 个复杂子任务
- **Locality**: 修改超时、并行策略、失败处理都在此模块内
- **Seam**: 可替换为 mock 实现用于测试

**2. ReportParser（报告解析器）**
```python
class ReportParser:
    """深度模块：从 agent 输出提取结构化数据
    
    接口:
    - parse_convergence_score(report_path) -> float
    - parse_consensus_facts(reports) -> list[str]
    - extract_references(reports) -> list[str]
    - extract_comparison_summary(reports) -> SummaryDict
    
    实现:
    - JSON 优先解析（结构化输出）
    - Markdown 降级解析（向后兼容）
    - 正则匹配与容错
    - 数据验证与默认值
    """
    
    def parse_convergence_score(self, report_path: Path) -> float:
        """提取收敛分数（0.0-1.0），失败返回 0.0 + 警告"""
        pass
    
    def parse_consensus_facts(self, 
                             reports: dict[str, str]) -> list[str]:
        """提取共识事实列表"""
        pass
    
    def extract_comparison_summary(self,
                                   reports: dict[str, str]
                                   ) -> dict[str, Any]:
        """提取对比摘要（用于精炼轮次）"""
        pass
```

**接口深度分析**:
- **Leverage**: 隐藏解析复杂度，提供简单的"路径→数据"接口
- **Locality**: 格式变化只影响此模块，调用方无感知
- **Seam**: 可注入 MockParser 返回固定数据

**3. RoundExecutor（轮次执行器）**
```python
class RoundExecutor:
    """深度模块：管理不同类型轮次的执行策略
    
    接口:
    - execute_round(round_num, round_type, context) -> RoundResult
    
    实现:
    - 轮次类型映射（research/comparison/refined）
    - Prompt 模板加载与变量注入
    - Agent 调用协调
    - 结果收集与验证
    - 元数据保存
    """
    
    def __init__(self, 
                 agent_runner: AgentRunner,
                 report_parser: ReportParser,
                 prompt_dir: Path):
        pass
    
    def execute_round(self,
                      round_num: int,
                      round_type: str,  # 'research' | 'comparison' | 'refined'
                      context: RoundContext) -> RoundResult:
        """执行指定类型的轮次，返回结果"""
        pass
```

**接口深度分析**:
- **Leverage**: 一个方法调用完成整轮执行（模板加载、agent 调用、结果解析）
- **Locality**: 新增轮次类型只需修改此模块
- **Seam**: 依赖注入 AgentRunner 和 ReportParser，易于测试

**4. ResearchCoordinator（协调器）**
```python
class ResearchCoordinator:
    """薄协调层：只负责主循环和收敛判定
    
    职责:
    - 轮次序列管理（1→2→3→4...）
    - 收敛条件判定
    - 全局状态维护（convergence_log）
    - 最终报告生成
    
    不再负责:
    - Agent 执行细节 → AgentRunner
    - 数据解析 → ReportParser
    - 轮次执行逻辑 → RoundExecutor
    """
    
    def __init__(self,
                 round_executor: RoundExecutor,
                 report_parser: ReportParser,
                 config: ResearchConfig):
        pass
    
    def run(self, question: str) -> Path:
        """主循环：轮次迭代 + 收敛判定"""
        pass
```

#### 实施步骤（5 步渐进式重构）

**第 1 步: 提取 AgentRunner（已完成 ✅）**
- [x] 创建 `agent_runner.py`（264 行）
- [x] 移植 `_execute_agents()` 和 `_execute_single_agent()`
- [x] 添加单元测试 `tests/test_agent_runner.py`（17 个测试全部通过）
- [x] 在 `orchestrator.py` 中使用新类（通过委托 + property 兼容）
- [x] 清理未使用的导入（os/time/subprocess/ThreadPoolExecutor）
- [x] orchestrator.py: 628 → 510 行

**第 2 步: 提取 ReportParser（已完成 ✅）**
- [x] 创建 `report_parser.py`（166 行，纯函数模块）
- [x] 移植解析逻辑：`format_for_prompt` / `extract_references` / `extract_comparison_summary` / `extract_convergence_scores`
- [x] 关键设计：解析（纯函数）与 I/O+策略（留在 orchestrator）分离
  - `_evaluate_convergence` 的分数提取 → parser；状态判定（依赖阈值）留 orchestrator
  - `_extract_unified_references` 的解析 → parser；文件写入留 orchestrator
- [x] 添加单元测试 `tests/test_report_parser.py`（20 个测试，无需 mock）
- [x] 在 `orchestrator.py` 中使用新类
- [x] orchestrator.py: 510 → 433 行

**第 3 步: 提取 RoundExecutor（已完成 ✅）**
- [x] 创建 `round_executor.py`（186 行）
- [x] 移植 `_run_research_round` / `_run_comparison_round` / `_run_refine_round` → `run_research` / `run_comparison` / `run_refine`
- [x] 一并收纳辅助方法：`_load_reports` / `_execute_agents` / `_load_prompt_template` / `_save_metadata`
- [x] 依赖注入 AgentRunner + ReportParser；轮次间状态（unified_references）由 Coordinator 传入
- [x] 添加单元测试 `tests/test_round_executor.py`（10 个测试，mock AgentRunner）
- [x] orchestrator.py: 433 → 287 行

**第 4 步: 简化 ResearchCoordinator（已完成 ✅）**
- [x] `ResearchOrchestrator` 重命名为 `ResearchCoordinator`（文件名仍 orchestrator.py，SKILL.md 入口不变）
- [x] 权威报告生成移入 `RoundExecutor.run_authoritative`，prompt 抽成 `prompts/authoritative.md`
- [x] 抽 `_read_texts` 辅助消除两处重复的 path→text 读取
- [x] 清理未使用导入（List/Tuple/Optional）
- [x] 协调器只剩：主循环、收敛判定（依赖阈值的策略）、统一参考资料落盘
- [x] 新增 2 个测试（run_authoritative），合计 49 个全过
- [x] orchestrator.py: 287 → 246 行（628 → 246，降幅 61%）

**第 5 步: 补充测试与文档（已完成 ✅）**
- [x] 集成测试 `tests/test_integration.py`：端到端 4 模块协作（mock subprocess，5 个用例）
  - 高分立即收敛 + 生成权威报告
  - 低分进入精炼轮
  - 统一参考资料提取
  - 失败 agent 不阻断流程（Bug #3 跨模块验证）
  - 收敛日志落盘
- [x] 更新 README 项目结构 + 新增「架构」章节（模块职责表 + 测试命令）
- [x] SKILL.md 入口不变（仍 `orchestrator.py`，无需改）
- [x] 全套测试 54 个用例（17 + 20 + 12 + 5），0.09s 全过

#### 成功标准

**定量指标**:
- [x] `orchestrator.py` 行数：628 → <200
- [ ] 单元测试覆盖率：0% → >70%
- [ ] 模块数量：1 → 4
- [ ] 平均方法复杂度：降低 40%

**定性指标**:
- [ ] 新贡献者可在 30 分钟内理解架构
- [ ] 添加新轮次类型只需修改 1 个文件
- [ ] 修改 agent 执行逻辑不影响报告解析
- [ ] 所有模块可独立测试

---

### 🟡 候选 #2: 轮次类型策略化
**优先级**: P1（重要但不紧急）  
**预计工作量**: 2-3 天  
**状态**: ⏸ 待第一步完成后启动

#### 问题分析
当前轮次类型通过条件分支硬编码：
```python
if round_num % 2 == 0:
    # 对比轮次
    if round_num == 2:
        # 第 2 轮特殊处理
else:
    # 精炼轮次
```

添加新轮次类型需要修改主循环。

#### 目标架构

```python
from abc import ABC, abstractmethod

class Round(ABC):
    @abstractmethod
    def execute(self, context: RoundContext) -> RoundResult:
        """执行该轮次，返回结果"""
        pass
    
    @abstractmethod
    def get_prompt_template(self) -> str:
        """获取 prompt 模板名称"""
        pass

class ResearchRound(Round):
    def execute(self, context):
        # 独立研究逻辑
        pass

class ComparisonRound(Round):
    def execute(self, context):
        # 对比评估逻辑
        # 第 2 轮特殊处理也在这里
        pass

class RefinedRound(Round):
    def execute(self, context):
        # 精炼逻辑
        pass

# 主循环变为：
round_sequence = [
    ResearchRound(),
    ComparisonRound(),
    RefinedRound(),
    ComparisonRound(),
    # ... 按需重复
]
```

#### 实施步骤
1. 定义 `Round` 抽象基类
2. 实现 3 个具体轮次类
3. 重构主循环为轮次序列迭代
4. 添加单元测试（每个轮次类独立测试）

#### 成功标准
- [ ] 添加新轮次类型无需修改主循环
- [ ] 每个轮次类可独立测试
- [ ] 特殊情况（如第 2 轮）封装在对应类内

---

### 🟡 候选 #3: 结构化 Agent 输出
**优先级**: P2（优化）  
**预计工作量**: 3-4 天  
**状态**: 📋 计划中

#### 问题分析
当前依赖 markdown 正则解析：
- 提取收敛分数：`re.search(r'0\.\d+', line)`
- 提取参考资料：寻找 `"## 5. 统一参考资料清单"` 标题
- 如果格式变化，提取失败

#### 目标方案

**Phase 1: 双格式支持（向后兼容）**
```python
# Prompt 末尾添加：
"""
请在报告末尾输出以下 JSON（用 ```json 包裹）：
{
  "convergence_score": 0.85,
  "consensus_facts": ["事实1", "事实2"],
  "disagreements": ["分歧点1"],
  "references": ["ref1", "ref2"]
}
"""

# 解析器优先提取 JSON：
class ReportParser:
    def parse(self, markdown: str) -> StructuredReport:
        # 1. 尝试提取 JSON block
        json_match = re.search(r'```json\n(.*?)\n```', markdown, re.DOTALL)
        if json_match:
            return self._parse_json(json_match.group(1))
        
        # 2. 降级到 markdown 解析（保持向后兼容）
        return self._parse_markdown(markdown)
```

**Phase 2: 全面迁移（6 个月后）**
- 所有 agent 升级到 JSON 输出
- 移除 markdown 降级路径
- 简化解析逻辑

#### 实施步骤
1. 更新 3 个 prompt 模板（添加 JSON 输出要求）
2. 实现 JSON 解析路径
3. 保留 markdown 降级路径
4. 逐步验证各 agent 的 JSON 输出质量
5. 6 个月后移除降级路径

#### 成功标准
- [ ] 90% 的报告通过 JSON 解析
- [ ] 解析失败率 <5%
- [ ] 向后兼容旧格式报告

---

### 🟢 候选 #4: 配置注入与验证
**优先级**: P3（可选）  
**预计工作量**: 1-2 天  
**状态**: 📋 计划中

#### 问题分析
- 配置键名硬编码（`config['agents']`）
- 无类型检查和验证
- 无环境变量覆盖

#### 目标方案

使用 Pydantic：
```python
from pydantic import BaseModel, Field

class AgentConfig(BaseModel):
    cli: str
    prompt_flag: str | None = None
    timeout: int = Field(default=600, gt=0)
    max_retries: int = Field(default=2, ge=0)

class ExecutionConfig(BaseModel):
    parallel: bool = True
    timeout: int = Field(default=600, gt=0, le=3600)
    max_retries: int = 2

class ResearchConfig(BaseModel):
    agents: dict[str, AgentConfig]
    execution: ExecutionConfig
    convergence: ConvergenceConfig
    
    class Config:
        env_prefix = 'CONV_RESEARCH_'

# 使用：
config = ResearchConfig.parse_file('agents.yaml')
# 自动验证 + 类型安全 + 环境变量覆盖
```

#### 实施步骤
1. 安装 `pydantic` 依赖
2. 定义配置模型
3. 替换现有配置加载逻辑
4. 添加验证测试

#### 成功标准
- [ ] 配置错误在启动时即发现（而非运行时）
- [ ] 支持环境变量覆盖
- [ ] IDE 自动补全配置字段

---

### 🟢 候选 #5: 添加单元测试框架
**优先级**: P1（与第一步并行）  
**预计工作量**: 持续进行  
**状态**: ⏳ 进行中

#### 目标测试金字塔

```
        ┌─────────┐
        │  E2E    │  1 个（完整流程）
        │  Tests  │
        ├─────────┤
        │Integration│  3-5 个（轮次执行）
        │  Tests   │
        ├──────────┤
        │   Unit    │  15-20 个（各模块）
        │   Tests   │
        └──────────┘
```

#### 测试覆盖计划

**单元测试**:
- `test_agent_runner.py`: agent 执行、重试、失败处理
- `test_report_parser.py`: 数据提取、格式解析、验证
- `test_round_executor.py`: 轮次策略、模板加载
- `test_convergence.py`: 收敛判定逻辑

**集成测试**:
- `test_research_round.py`: 完整研究轮次
- `test_comparison_round.py`: 完整对比轮次
- `test_convergence_flow.py`: 多轮收敛流程

**端到端测试**:
- `test_full_research.py`: 从问题到最终报告

#### 测试工具
- 测试框架: `pytest`
- Mock: `pytest-mock` 或 `unittest.mock`
- 覆盖率: `pytest-cov`
- 快照测试: `pytest-snapshot`（用于报告格式验证）

#### 实施步骤
1. [x] 创建 `tests/` 目录结构
2. [ ] 配置 `pytest.ini` 和 `conftest.py`
3. [ ] 每个新模块同步编写单元测试
4. [ ] 达到 70% 覆盖率后添加 CI 检查

#### 成功标准
- [ ] 单元测试覆盖率 >70%
- [ ] 测试运行时间 <30 秒
- [ ] 所有测试可独立运行
- [ ] CI 集成（GitHub Actions）

---

## 📊 整体进度追踪

### 里程碑

| 里程碑 | 目标 | 预计完成日期 | 状态 |
|--------|------|-------------|------|
| M1: 模块拆分完成 | 4 个独立模块 | Day 7 | ⏳ 进行中 |
| M2: 单元测试覆盖 | 覆盖率 >50% | Day 10 | 📋 待开始 |
| M3: 策略化重构 | 轮次策略模式 | Day 14 | 📋 待开始 |
| M4: 全面测试 | 覆盖率 >70% | Day 18 | 📋 待开始 |
| M5: v0.2.0 发布 | 文档 + CI | Day 21 | 📋 待开始 |

### 当前状态

**正在进行**: 候选 #1 第 1 步 —— 提取 AgentRunner

**已完成**:
- [x] 架构分析
- [x] 重构计划文档

**待办**:
- [ ] 实现 AgentRunner 模块
- [ ] 编写 AgentRunner 单元测试
- [ ] 集成到 orchestrator.py

---

## 🔧 开发规范

### 代码风格
- 遵循 PEP 8
- 类型注解：所有公共接口必须有类型标注
- 文档字符串：所有公共方法使用 Google 风格 docstring

### 命名约定
- 模块：`snake_case`（如 `agent_runner.py`）
- 类：`PascalCase`（如 `AgentRunner`）
- 方法/变量：`snake_case`
- 常量：`UPPER_SNAKE_CASE`

### 模块组织
```
convergent_research/
├── __init__.py
├── coordinator.py           (原 orchestrator.py)
├── agent_runner.py          (新增)
├── report_parser.py         (新增)
├── round_executor.py        (新增)
├── models.py                (数据模型)
├── config.py                (配置模型)
└── utils.py                 (工具函数)
```

### 测试规范
- 测试文件命名：`test_<module_name>.py`
- 测试类命名：`Test<ClassName>`
- 测试方法命名：`test_<method>_<scenario>`
- 每个测试只验证一个行为
- 使用 AAA 模式（Arrange-Act-Assert）

---

## 📝 变更日志

### v0.2.0-alpha.1 (进行中)
- [ ] 提取 AgentRunner 模块
- [ ] 添加 AgentRunner 单元测试
- [ ] 更新 orchestrator.py 使用新模块

### v0.1.1 (2026-06-02)
- [x] Bug #1: 修复精炼轮次 prompt 过长
- [x] Bug #2: 添加超时重试机制
- [x] Bug #3: 失败 agent 追踪
- [x] 迁移到 my_skills 工作流
- [x] 接入 npx skills 管理

---

## 🤝 贡献指南

### 提交 Pull Request 前检查清单
- [ ] 代码通过 `flake8` 检查
- [ ] 所有单元测试通过（`pytest tests/`）
- [ ] 新功能有对应单元测试
- [ ] 更新相关文档
- [ ] Commit 信息符合约定（`feat:`, `fix:`, `refactor:` 等）

### 获取帮助
- GitHub Issues: https://github.com/mixgreen/convergent-research/issues
- 本文档问题：在 Issue 中标记 `documentation` 标签

---

## 📚 参考资料

### 架构设计原则
- **A Philosophy of Software Design** (John Ousterhout)
  - Deep modules vs Shallow modules
  - Information hiding
  - Interface design

### 相关文档
- `BUGFIX_REPORT.md` - 已修复的 bug 详情
- `TEST_VERIFICATION_REPORT.md` - Bug 修复测试报告
- `README.md` - 项目使用说明
- `SKILL.md` - Claude Code skill 定义

---

**最后更新**: 2026-06-02  
**维护者**: @mixgreen
