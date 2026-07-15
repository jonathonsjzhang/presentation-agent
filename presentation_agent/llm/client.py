from __future__ import annotations

from presentation_agent.llm.schema import extract_json, validate
from presentation_agent.llm.types import (
    LLMAdapter,
    LLMRequest,
    LLMResponse,
    SchemaValidationError,
)


class LLMClient:
    """The single place in the harness that turns a request into structured data.

    maker (generate) / checker (review) / stop_check all depend only on this.
    The client owns the cross-cutting guarantees so every adapter inherits them:
      - JSON extraction from free-form text
      - schema validation against the skill package schema
      - one automatic retry with a corrective hint on parse/validation failure
    """

    def __init__(self, adapter: LLMAdapter, max_retries: int = 1) -> None:
        self.adapter = adapter
        self.max_retries = max(0, max_retries)

    @property
    def provider(self) -> str:
        return getattr(self.adapter, "kind", "unknown")

    def complete(self, request: LLMRequest) -> LLMResponse:
        attempts = 0
        last_error: Exception | None = None
        last_raw = ""
        current = request

        while attempts <= self.max_retries:
            attempts += 1
            raw = self.adapter.generate(current)
            last_raw = raw
            if request.metadata.get("response_format") == "markdown":
                markdown = str(raw or "").strip()
                if markdown:
                    return LLMResponse(
                        data={"content_markdown": markdown},
                        raw_text=raw,
                        provider=self.provider,
                        purpose=request.purpose,
                        attempts=attempts,
                        usage={"attempts": attempts},
                    )
                last_error = ValueError("empty Markdown output")
                current = self._with_hint(
                    request, "上次输出为空；请输出完整 Markdown 文档。"
                )
                continue
            try:
                data = extract_json(raw)
            except ValueError as exc:
                last_error = exc
                current = self._with_hint(request, f"上次输出无法解析为 JSON：{exc}")
                continue

            if request.schema:
                errors = validate(data, request.schema)
                if errors:
                    last_error = SchemaValidationError(errors)
                    current = self._with_hint(
                        request,
                        "上次输出不符合 schema，请修正以下问题：\n- " + "\n- ".join(errors),
                    )
                    continue

            return LLMResponse(
                data=data,
                raw_text=raw,
                provider=self.provider,
                purpose=request.purpose,
                attempts=attempts,
                usage={"attempts": attempts},
            )

        if isinstance(last_error, SchemaValidationError):
            raise last_error
        raise SchemaValidationError(
            [f"model output unusable after {attempts} attempt(s): {last_error}", f"raw={last_raw[:200]}"]
        )

    @staticmethod
    def _with_hint(request: LLMRequest, hint: str) -> LLMRequest:
        markdown = request.metadata.get("response_format") == "markdown"
        return LLMRequest(
            system=request.system,
            user=(
                f"{request.user}\n\n[修正提示] {hint}\n请直接输出完整 Markdown 正文。"
                if markdown
                else f"{request.user}\n\n[修正提示] {hint}\n请只输出一个 ```json 代码块，不要任何解释。"
            ),
            purpose=request.purpose,
            schema=request.schema,
            schema_name=request.schema_name,
            agent_id=request.agent_id,
            round_index=request.round_index,
            metadata=request.metadata,
        )
