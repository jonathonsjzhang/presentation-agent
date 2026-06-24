# Presentation Agent Infra

This repo is a loop-first scaffold for the 汇报助手 design in `汇报助手系统设计方案.md`.

Current scope:

- 7-agent pipeline is configured in `configs/agents.json`, including handoff, input/output contracts, loop policy, state boundaries, and harness status for each agent.
- Human-editable skill packages for all 7 agents live under `skills/<agent_id>/`.
- `storyline_design` is the first runnable sample agent.
- Each run follows: skill execution -> reviewer -> stop checker -> human review handoff.
- Each run writes `run_state.json` as the process spine for current step, round, objections, logged feedback, and next action.
- Agent state uses isolated cold `learning_log.jsonl` plus hot `memory.json` under `data/agents/<agent_id>/`.
- Each skill package includes `SKILL.md`, `rubrics.json`, and schema files. Runtime adapters are still incremental; today only `storyline_design` has a runnable scaffold adapter.
- LLM/sub-agent/connector behavior is intentionally stubbed behind interfaces so the infra can be tested before real skills are finalized.

## Run the sample loop

```bash
python -m presentation_agent.cli list-agents
python -m presentation_agent.cli run storyline_design --input examples/storyline_input.json
```

The command writes a run folder under `artifacts/` with:

- `artifact.json`: final structured output for the agent
- `review.json`: P0/P1 reviewer output
- `run_state.json`: step-by-step loop state and next action
- `loop_result.json`: machine-readable run summary
- `human_review.md`: the manual review checkpoint

## Record feedback into memory

```bash
python -m presentation_agent.cli feedback storyline_design \
  --dimension Wording \
  --problem "标题用了唯一" \
  --reason "绝对化表述容易被反例击穿" \
  --change "改成少数之一"
```

Then inspect hot memory:

```bash
python -m presentation_agent.cli show-memory storyline_design
```

For conversational human review, the host agent should record the user's raw
feedback sentence automatically while revising:

```bash
python -m presentation_agent.cli feedback-text storyline_design \
  --text "标题还是主题词，应该改成完整判断句并带出 so what" \
  --scene human_review_chat \
  --run-state artifacts/<run>/stage_3_storyline_design/run_state.json
```

This parses the feedback into dimension/problem/change, appends
`learning_log.jsonl`, updates `memory.json`, and attaches the log id to
`run_state.json`.

The learning loop also captures positive examples and version-comparison
lessons, so memory is not only a failure log:

```bash
python -m presentation_agent.cli success-memory storyline_design \
  --dimension Leadline \
  --pattern "战略负责人材料标题写成业务判断 + so what" \
  --why "更容易通过标题连读测试"

python -m presentation_agent.cli compare-reflect storyline_design \
  --before artifacts/<run>/v1.md \
  --after artifacts/<run>/final.md \
  --dimension Leadline \
  --lesson "后续标题从主题词升级为战略判断，并在结尾闭环 action"
```

At generation time the harness runs deterministic memory retrieval and routing:
it selects only the top relevant memory cards (`memory_retrieval_limit`,
default 6), then passes a short routing policy into the prompt for checklist
focus and review strictness.

## Memory dreaming

Memory is periodically consolidated. After every feedback write, the harness
checks `configs/agents.json -> state_policy.memory_dream_interval` and
`memory_soft_limit`; when either threshold is hit it runs deterministic
dreaming automatically:

- merge exact duplicate memory;
- clear orphan links;
- evict low-hit over-limit items;
- write `memory_summary.json`;
- write a timestamped `memory_dreams/dream_*.json` report;
- flag potential conflicts for human review.

Run it manually across all agents:

```bash
python -m presentation_agent.cli memory-dream --all --apply --reason scheduled_review
```

Promotion from hot memory into durable `rubrics.json` is still human-confirmed:

```bash
python -m presentation_agent.cli memory-maintain storyline_design --promote
python -m presentation_agent.cli memory-maintain storyline_design --promote --apply --ids M-001
```

## Start the interactive UI

For teammates on macOS, the easiest path is to double-click:

```text
打开汇报助手LoopCockpit.command
```

It starts the local web server and opens the cockpit automatically.

```bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m presentation_agent.web --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

The UI supports:

- Browsing the 7-agent pipeline and the single-agent loop steps.
- Running the implemented `storyline_design` loop with editable JSON input.
- Browsing and editing memory, skill packages, runtime skill adapters, config, docs, and example files.
- Inspecting generated artifacts and human review handoff files.
- Running simple command-console actions such as `run storyline_design`, `list agents`, `open data/agents/storyline_design/memory.json`, and `show memory storyline_design`.

## Next build targets

1. Replace deterministic reviewer with an LLM-backed sub-agent while keeping the same `ReviewReport` schema.
2. Expand `storyline_design` from scaffold generation to the real SOP.
3. Add connector interfaces for Excel/CSV/data-source intake inside skills.
4. Add richer LLM-assisted memory summarization on top of deterministic dreaming.
5. Add optional multi-candidate generation for storyline only.
6. Copy the same loop harness to the remaining six skills as their SOPs become concrete.
