# SpawnAdapter 实现方案（下一步开发）

> 状态：实现方案（待用户确认后动手写代码）
> 关联：`docs/three_layer_agent_architecture.md`（架构规范）、`docs/manager_agent_development_plan.md`（Manager 落地）、`presentation_agent/manager.py`、`presentation_agent/step.py`
> 目标：把「Worker 在主对话同进程跑模型」升级为「可派生宿主原生独立上下文 sub-agent」，根治 README TODO #2 的上下文漂移，同时保持 85 项测试不退化。

---

## 0. 背景事实（基于当前代码勘探，非设计想象）

当前 Manager 驱动 Worker 的真实调用链：

```
ManagerOrchestrator.prepare()        manager.py:327  actor==worker
  └─ WorkerExecutor.prepare(task_dir)  manager.py:253   ← 唯一收口点（仅 5 行）
       └─ StepRunner(task_dir).prepare()  step.py:108   llm=None，不调模型
            └─ 写 handoff/instruction_gen.md  step.py:602  告知 output 路径
   ✋ 宿主主模型（Python 之外）读指令 → 自己跑 → 写 handoff/output_gen.json
host 再调 commit → _read_and_validate_output 读回校验 → artifact.json
```

三个已确认事实：

1. **Manager 这条新路全程 `llm=None`、零模型调用**，靠 handoff 文件交接（与 sub-agent 模式天然同构）。
2. **漂移根因**：InlineAdapter 注释明示「没有 API 能回调进宿主模型」，所以 7 个环节的「产出 JSON」全挤在宿主同一对话上下文里。
3. **`agents.json` 的 `clean_context_review_sub_agent` / `review_sub_agent` 仍是纯占位符**，无任何代码消费。
4. `llm/adapters`（cli/inline/mock）服务的是**老 `Pipeline` 路径**，Manager 新路不经过它们——所以本方案不复用 LLM adapter，而是**新增一层 spawn adapter**（粒度不同：前者是「单次 LLM 调用通道」，后者是「派生独立上下文 sub-agent」）。

---

## 1. 设计原则

| 原则 | 说明 |
|---|---|
| **唯一插入点** | 只在 `WorkerExecutor.prepare()`（manager.py:253）分流。状态机、`record_worker_completed`、acceptance loop 一律不动 |
| **零侵入回退** | 默认走 `inline`（= 现有行为）。不显式开启 native 时，行为与今天 100% 一致，85 项测试不受影响 |
| **终端无关契约** | 抽象出 `SpawnAdapter` 基类，WorkBuddy / Claude Code / Codex 各实现一个子类。新增终端只加一个子类 + 一行注册 |
| **产物契约不变** | 无论哪种 adapter，最终都必须落出与今天相同的 `artifact.json` + handoff 文件，Manager 验收逻辑无感 |
| **深度=1 不变量** | Codex 限制 sub-agent 深度=1。worker 内部禁止再下派子 agent；L3 reviewer 由 Manager 层派，不由 worker 自派 |

---

## 2. 新增模块：`presentation_agent/spawn.py`

### 2.1 能力契约（终端无关）

```python
# presentation_agent/spawn.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SpawnRole = Literal["worker", "reviewer"]
SpawnMode = Literal["foreground", "background"]


@dataclass
class SpawnRequest:
    """Manager 装配好的、自包含的派生请求。"""
    task_dir: Path                 # run_dir/tasks/<task_id>_<agent_id>
    agent_id: str                  # 环节 id，如 argument_synthesis
    role: SpawnRole                # worker(可写) / reviewer(只读)
    instruction_path: Path         # handoff/instruction_*.md（StepRunner 已生成）
    input_path: Path               # task_dir/input.json
    output_path: Path              # 期望子 agent 写回的 artifact 路径
    mode: SpawnMode = "foreground"


@dataclass
class SpawnResult:
    """子 agent 执行后的回传结果（Manager 据此验收）。"""
    status: Literal["dispatched", "completed", "failed"]
    artifact_path: Path | None     # 子 agent 写回的产物
    detail: dict[str, Any]         # 透传宿主返回的元信息


class SpawnAdapter(ABC):
    """终端无关的 sub-agent 派生契约。一个终端一个实现。"""

    kind: str = "base"

    @abstractmethod
    def spawn(self, request: SpawnRequest) -> SpawnResult:
        """派生一个独立上下文 sub-agent 执行 request，回传 SpawnResult。"""
        ...
```

### 2.2 三个内置实现

```python
class InlineSpawnAdapter(SpawnAdapter):
    """默认实现 = 现有行为。不派生任何东西，原样返回 StepRunner 指令包。
    宿主主模型（当前对话）自己读指令、写 handoff/output。保证零回退风险。"""
    kind = "inline"

    def spawn(self, request: SpawnRequest) -> SpawnResult:
        # 不做任何派生：指令包已由 StepRunner.prepare() 写好，
        # 控制权交还宿主，等待 host 调 commit。
        return SpawnResult(status="dispatched", artifact_path=None, detail={})


class WorkBuddySpawnAdapter(SpawnAdapter):
    """WorkBuddy 宿主：由宿主 Agent 用 Agent 工具派生。
    Python 侧不能直接调 Agent 工具（那是宿主能力），因此这里产出一份
    『派生指令清单』(spawn_request.json) 写入 task_dir，
    宿主 SKILL.md 的调度规则读取它并执行真正的 Agent 工具派生。"""
    kind = "workbuddy"

    def spawn(self, request: SpawnRequest) -> SpawnResult:
        spec = {
            "host": "workbuddy",
            "subagent_type": "general-purpose" if request.role == "worker" else "Explore",
            "agent_id": request.agent_id,
            "role": request.role,
            "instruction_path": str(request.instruction_path),
            "input_path": str(request.input_path),
            "output_path": str(request.output_path),
            "mode": request.mode,
            "invariants": {"max_depth": 1, "write_scope": str(request.task_dir)},
        }
        spawn_file = request.task_dir / "spawn_request.json"
        write_json(spawn_file, spec)
        return SpawnResult(
            status="dispatched",
            artifact_path=None,
            detail={"spawn_request": str(spawn_file), "executor": "host_agent_tool"},
        )


class CLISpawnAdapter(SpawnAdapter):
    """Claude Code / Codex 宿主：通过 headless CLI 真 spawn 一个隔离进程。
    复用 llm/adapters/cli.py 的 subprocess 思路，但这里派的是『带独立上下文的
    sub-agent 会话』而非一次性 LLM 调用。命令模板由 configs 提供。"""
    kind = "cli"

    def __init__(self, command: list[str]) -> None:
        self.command = command  # 如 ["claude", "-p"] 或 ["codex", "exec"]

    def spawn(self, request: SpawnRequest) -> SpawnResult:
        # 详见 §5 第二阶段。第一阶段不实现，仅占位。
        raise NotImplementedError("CLISpawnAdapter 在第二阶段实现")
```

### 2.3 工厂

```python
def build_spawn_adapter(root: Path) -> SpawnAdapter:
    """读 configs/agents.json 的 orchestration.spawn 配置选 adapter。
    缺省 = inline（零回退风险）。"""
    config = read_json(root / "configs" / "agents.json", default={})
    spawn_cfg = config.get("orchestration", {}).get("spawn", {})
    kind = spawn_cfg.get("adapter", "inline")
    if kind == "inline":
        return InlineSpawnAdapter()
    if kind == "workbuddy":
        return WorkBuddySpawnAdapter()
    if kind == "cli":
        return CLISpawnAdapter(spawn_cfg.get("command", []))
    raise StepError(f"未知 spawn adapter: {kind}")
```

---

## 3. 改动点：`WorkerExecutor`（manager.py）

### 3.1 构造函数注入 adapter（manager.py:158）

```diff
 def __init__(self, root: Path, run_dir: Path, data_root: Path) -> None:
     self.root = root
     self.run_dir = run_dir
     self.data_root = data_root
+    self.spawn_adapter = build_spawn_adapter(root)   # 缺省 inline
     config = read_json(root / "configs" / "agents.json", default={})
     ...
```

### 3.2 prepare 分流（manager.py:253，核心改动）

```diff
 def prepare(self, task_dir: Path) -> dict[str, Any]:
     instruction = StepRunner(
         self.root, task_dir, data_root=self.data_root
     ).prepare()
     instruction["actor"] = "worker"
+
+    # spawn 分流：inline 时与今天完全一致；native 时产出派生请求。
+    if self.spawn_adapter.kind != "inline":
+        request = self._build_spawn_request(task_dir, instruction)
+        result = self.spawn_adapter.spawn(request)
+        instruction["spawn"] = {
+            "adapter": self.spawn_adapter.kind,
+            "status": result.status,
+            "detail": result.detail,
+        }
     return instruction
```

> 关键：inline 分支**一行不变**，所以默认行为 = 今天。只有显式配置 native adapter 才进入新逻辑。这是「85 项测试不退化」的机制保证。

### 3.3 新增私有方法 `_build_spawn_request`

```python
def _build_spawn_request(self, task_dir: Path, instruction: dict) -> SpawnRequest:
    agent_id = instruction.get("agent_id") or read_json(
        task_dir / "run_state.json", default={}
    ).get("agent_id", "")
    role = "reviewer" if instruction.get("step", "").startswith("review") else "worker"
    return SpawnRequest(
        task_dir=task_dir,
        agent_id=agent_id,
        role=role,
        instruction_path=Path(instruction.get("instruction_path", "")),
        input_path=task_dir / "input.json",
        output_path=task_dir / "artifact.json",
        mode="foreground",
    )
```

---

## 4. 配置：`configs/agents.json` 新增 orchestration.spawn

```diff
 {
   "pipeline": { ... },
+  "orchestration": {
+    "spawn": {
+      "adapter": "inline",          // inline | workbuddy | cli
+      "command": [],                 // cli adapter 用，如 ["claude","-p"]
+      "invariants": { "max_depth": 1 }
+    }
+  },
   "agents": [ ... ]
}
```

默认 `inline` → 不改任何现状。切 native 只需改这一处。

---

## 5. 分阶段落地（与你已选「先出方案」对齐）

### 阶段一（本方案，①SpawnAdapter 骨架）
- 新增 `spawn.py`：契约 + InlineSpawnAdapter + WorkBuddySpawnAdapter（产 spawn_request.json）+ 工厂。
- 改 `WorkerExecutor`：构造注入 + prepare 分流 + `_build_spawn_request`。
- 改 `agents.json`：加 `orchestration.spawn`（默认 inline）。
- 测试：①新增 `tests/test_spawn_adapter.py`（inline 行为等价、workbuddy 产 spawn_request.json、工厂选择）；②跑全量回归确认 85 项不退化。
- **不碰** StepRunner、不碰老 Pipeline、不碰 acceptance loop。

### 阶段二（②真 sub-agent 端到端验证）
- 在 WorkBuddy 宿主上：用 `Agent` 工具消费 `spawn_request.json`，真派一个环节的 worker→reviewer 闭环，验证回写协议。
- 这是**唯一需要和 Manager 同事对接的缝**：约定子 agent 写回 `artifact.json` 的路径与格式 = 今天 commit 读的格式（已对齐，零改动）。
- 实现 `CLISpawnAdapter`（Claude/Codex headless）。

### 阶段三（③三终端 agent 文件派生）
- `agents.json` 单一事实源 → 生成 `.claude/agents/*.md`、codex、workbuddy 三套定义 + 方言映射表。
- 把 reviewer 占位符（`clean_context_review_sub_agent`）兑现为真定义。

---

## 6. 风险与对接清单

| 项 | 说明 | 行动 |
|---|---|---|
| 回退风险 | 默认 inline = 现状，无风险 | 阶段一不改默认值 |
| 与同事接口 | 子 agent 回写 `artifact.json` 格式 | 已与现有 commit 读取格式一致，无需改动；阶段二确认一次 |
| 深度=1 | worker 不能自派子 agent | 写入 spawn_request.json 的 invariants，并在 SKILL.md 调度规则中强制 |
| 写作用域 | worker 写操作限 task_dir 内 | invariants.write_scope = task_dir，宿主侧约束 |
| Python 不能直调 Agent 工具 | WorkBuddy 的 Agent 工具是宿主能力 | adapter 产出 spawn_request.json，由宿主 SKILL.md 执行真正派生 |

---

## 7. 一句话总结

下一步 = 在 `WorkerExecutor.prepare`（manager.py:253）加一层 `SpawnAdapter` 分流。默认 inline 保证零回退，native 时产出自包含派生请求交宿主执行。这是把三层架构从「配置声明」变成「运行时兑现」的地基，且对 Manager 控制面零侵入。
