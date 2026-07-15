from __future__ import annotations

import json
from typing import Any, Optional

from presentation_agent.capabilities.budget import estimate_tokens
from presentation_agent.llm.client import LLMClient
from presentation_agent.llm.types import LLMRequest
from presentation_agent.models import AgentSpec, Objection
from presentation_agent.skills.base import SkillContext


class GenericSkill:
    """Package-driven implementation for specialist Worker agents.

    The behavior of each Worker is defined by its skill package
    (SKILL.md + rubrics.json + schemas/), not by hand-written Python. This class
    reads the package out of the runtime context, composes a prompt, and asks
    the LLMClient to produce an artifact that satisfies the agent's output
    schema. Manager uses its own control-plane runtime because it emits
    dispatch/acceptance actions. Adding or changing a Worker means editing its package,
    never this file.

    A mock LLMClient lets the whole pipeline run offline; a cli/inline client
    swaps in real generation without any change here.
    """

    def __init__(self, skill_id: str, llm: Optional[LLMClient] = None) -> None:
        self.id = skill_id
        self.llm = llm
        self.last_prompt_budget: dict[str, int] = {}

    def generation_dimensions(self) -> list[str]:
        # Dimensions now come from the agent spec / memory, not a hard-coded list.
        return []

    def run(
        self,
        spec: AgentSpec,
        input_data: dict[str, Any],
        context: SkillContext,
        candidate_hint: Optional[str] = None,
    ) -> dict[str, Any]:
        request = self._build_request(
            spec, input_data, context, round_index=0, objections=None, candidate_hint=candidate_hint
        )
        artifact = self._invoke(request, spec)
        return self._stamp(artifact, spec)

    def revise(
        self,
        spec: AgentSpec,
        input_data: dict[str, Any],
        previous_artifact: dict[str, Any],
        objections: list[Objection],
        context: SkillContext,
    ) -> dict[str, Any]:
        request = self._build_request(
            spec,
            input_data,
            context,
            round_index=1,
            objections=objections,
            previous_artifact=previous_artifact,
        )
        artifact = self._invoke(request, spec)
        return self._stamp(artifact, spec)

    # -- prompt assembly -------------------------------------------------

    def _build_request(
        self,
        spec: AgentSpec,
        input_data: dict[str, Any],
        context: SkillContext,
        round_index: int,
        objections: Optional[list[Objection]],
        previous_artifact: Optional[dict[str, Any]] = None,
        candidate_hint: Optional[str] = None,
    ) -> LLMRequest:
        package = context.get("skill_package", {})
        instructions = package.get("instructions", "")
        markdown_output = (
            str(spec.output_contract.get("artifact_format") or "").lower()
            == "markdown"
        )
        schema = None if markdown_output else self._output_schema(package, spec)
        global_state = context.get("global_state", {})
        style_guidance = context.get("style_guidance", [])
        routing_policy = context.get("routing_policy", {})

        system = self._compose_system(spec, instructions)
        user = self._compose_user(
            spec,
            input_data,
            schema,
            global_state,
            style_guidance,
            routing_policy,
            objections,
            previous_artifact,
            candidate_hint,
            external_input_path=str(context.get("external_input_path") or ""),
        )
        request = LLMRequest(
            system=system,
            user=user,
            purpose="generate",
            schema=schema,
            schema_name=spec.output_schema,
            agent_id=spec.id,
            round_index=round_index,
            metadata={
                "response_format": "markdown" if markdown_output else "json",
                "canonical_filename": str(
                    spec.output_contract.get("canonical_filename") or ""
                ),
            },
        )
        self.last_prompt_budget = {
            "system_chars": len(system),
            "system_tokens_estimate": estimate_tokens(system),
            "user_chars": len(user),
            "user_tokens_estimate": estimate_tokens(user),
            "total_chars": len(system) + len(user),
            "total_tokens_estimate": estimate_tokens(system + user),
        }
        return request

    def _compose_system(self, spec: AgentSpec, instructions: str) -> str:
        if str(spec.output_contract.get("artifact_format") or "") == "markdown":
            output_rule = "直接产出一份完整 Markdown 文档，不要 JSON 外壳。"
        else:
            output_rule = f"产出符合 {spec.output_schema} 的单个 JSON 对象。"
        header = (
            f"你是汇报助手流水线中的 Agent「{spec.name}」(stage {spec.stage})。"
            "严格遵循下方 skill 说明书(SKILL.md)的角色、工作流和输出要求，"
            + output_rule
        )
        return f"{header}\n\n===== SKILL 说明书 =====\n{instructions}".strip()

    def _compose_user(
        self,
        spec: AgentSpec,
        input_data: dict[str, Any],
        schema: Optional[dict[str, Any]],
        global_state: dict[str, Any],
        style_guidance: list[str],
        routing_policy: dict[str, Any],
        objections: Optional[list[Objection]],
        previous_artifact: Optional[dict[str, Any]],
        candidate_hint: Optional[str] = None,
        external_input_path: str = "",
    ) -> str:
        blocks: list[str] = []
        if input_data.get("schema") == "worker_context.v1":
            blocks.extend(
                self._projected_context_blocks(
                    input_data,
                    external_input_path=external_input_path,
                )
            )
        else:
            blocks.append("## 本环节输入(上游 artifact 或原始 brief)")
            blocks.append(self._json_block(input_data))

        if candidate_hint:
            blocks.append("## 本候选的差异化要求(多候选并行，本次只走这一种角度)")
            blocks.append(candidate_hint)

        if global_state:
            blocks.append("## 全局 state(跨 agent 共享，禁止与之冲突)")
            blocks.append(self._json_block(global_state))

        if style_guidance:
            blocks.append("## 召回的历史经验(来自 memory，已按相关性筛选，只遵循这些)")
            blocks.append("\n".join(f"- {s}" for s in style_guidance))

        if routing_policy:
            blocks.append("## 本轮 routing policy(轻量执行策略)")
            blocks.append(self._json_block(routing_policy))

        if previous_artifact is not None:
            blocks.append("## 上一轮产物(需在此基础上返工)")
            blocks.append(self._json_block(previous_artifact))

        if objections:
            blocks.append("## 必须修复的审查异议(逐条解决，不得遗留)")
            blocks.append(
                "\n".join(
                    f"- [{o.severity}/{o.dimension}] {o.message}"
                    + (f" 证据/反馈: {o.evidence}" if o.evidence else "")
                    + (f" 修复建议: {o.suggestion}" if o.suggestion else "")
                    for o in objections
                )
            )

        if schema:
            blocks.append(f"## 输出 schema({spec.output_schema})，必须严格符合")
            blocks.append(self._json_block(schema))

        if str(spec.output_contract.get("artifact_format") or "") == "markdown":
            blocks.append(
                "## 输出要求\n"
                "- 直接输出完整 Markdown 正文，不要代码围栏，不要 JSON 外壳。\n"
                "- 严格使用 SKILL.md 的规范章节；信息缺失时在正文中透明说明。\n"
                "- 不要留 TODO 占位，不要在文档之外添加解释。"
            )
        else:
            blocks.append(
                "## 输出要求\n"
                f"- 只输出一个 ```json 代码块，内容为符合 {spec.output_schema} 的对象。\n"
                "- 不要任何解释、前言或结语。\n"
                "- 信息缺失时按 SKILL.md 透明说明，不要编造，也不要留 TODO 占位。"
            )
        return "\n\n".join(blocks)

    def _projected_context_blocks(
        self,
        input_data: dict[str, Any],
        *,
        external_input_path: str = "",
    ) -> list[str]:
        blocks = [
            "## 项目约束（report charter，优先级最高）",
            self._json_block(input_data.get("report_charter", {})),
            "## Manager 任务单",
            self._json_block(input_data.get("manager_task", {})),
        ]
        readiness = input_data.get("input_readiness", {})
        if readiness:
            blocks.extend([
                "## 输入完整性门禁",
                self._json_block(readiness),
            ])
        raw_brief = input_data.get("raw_brief", {})
        if raw_brief:
            blocks.extend([
                "## 原始 brief（已按本 Worker 投影）",
                self._json_block(raw_brief),
            ])
        if external_input_path:
            blocks.extend([
                "## 完整任务输入（必须读取）",
                (
                    f"完整、唯一的业务输入位于 `{external_input_path}`。"
                    "其中包含 evidence_catalog、evidence_assets、上游 artifact 和材料引用。"
                    "先读取该 JSON 的顶层索引，再按任务需要深入具体字段；"
                    "不要把整个文件复制到对话或输出中。"
                ),
            ])
        canonical_inputs = {
            key: input_data[key]
            for key in (
                "raw_materials",
                "evidence_catalog",
                "evidence_index",
                "evidence_assets",
                "material_resolution",
                "delivery_target",
            )
            if input_data.get(key) not in (None, "", [], {})
        }
        if canonical_inputs and not external_input_path:
            blocks.extend([
                "## v0.3 Canonical inputs（本环节正式输入）",
                self._json_block(canonical_inputs),
            ])
        inputs = input_data.get("inputs", {})
        if inputs and not external_input_path:
            blocks.extend([
                "## 命名空间化上游输入（保留来源，不得跨来源臆测）",
                self._json_block(inputs),
            ])
        signal = input_data.get("upstream_signal", {})
        if signal:
            blocks.extend([
                "## 必须继承或显式解释偏离的上游信号",
                self._json_block(signal),
            ])
        refs = input_data.get("material_refs", [])
        if refs:
            blocks.extend([
                "## 按需读取的材料引用",
                "若完成任务需要 omitted_fields 或 projected_fields 的完整内容，"
                "请读取对应 artifact_path；不要根据 preview 补写事实。",
                self._json_block(refs),
            ])
        return blocks

    # -- invocation ------------------------------------------------------

    def _invoke(self, request: LLMRequest, spec: AgentSpec) -> dict[str, Any]:
        if self.llm is None:
            raise RuntimeError(
                f"GenericSkill for {spec.id} has no LLMClient; loop must inject one "
                "(build_llm_client). Use the mock provider to run offline."
            )
        response = self.llm.complete(request)
        return response.data

    # -- helpers ---------------------------------------------------------

    def _output_schema(self, package: dict[str, Any], spec: AgentSpec) -> Optional[dict[str, Any]]:
        schemas = package.get("schemas", {})
        # schemas are keyed by file stem, e.g. "storyline.v2"
        return schemas.get(spec.output_schema)

    def _stamp(self, artifact: dict[str, Any], spec: AgentSpec) -> dict[str, Any]:
        """Guarantee identity fields regardless of whether the schema lists them."""
        if not isinstance(artifact, dict):
            return artifact
        artifact.setdefault("agent_id", spec.id)
        artifact.setdefault("schema", spec.output_schema)
        artifact["agent_id"] = spec.id
        artifact["schema"] = spec.output_schema
        return artifact

    @staticmethod
    def _json_block(data: Any) -> str:
        return "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```"
