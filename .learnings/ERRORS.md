## [ERR-20260618-001] system_python_pycache_permission

**Logged**: 2026-06-18T08:10:00Z
**Priority**: medium
**Status**: pending
**Area**: tests

### Summary
System Python `py_compile` tried to write bytecode cache under `~/Library/Caches`, which is outside the workspace sandbox.

### Error
```text
PermissionError: [Errno 1] Operation not permitted: '/Users/zhangsijing/Library/Caches/com.apple.python/Users/zhangsijing/Desktop/Coding'
```

### Context
- Command attempted: `/usr/bin/python3 -m py_compile presentation_agent/web.py presentation_agent/loop.py presentation_agent/cli.py`
- Workspace allows writes under the project root and temp directories, not the user Library cache path.

### Suggested Fix
Use `PYTHONDONTWRITEBYTECODE=1` or set `PYTHONPYCACHEPREFIX` to a writable temp/project path when running system Python compile/import checks.

### Metadata
- Reproducible: yes
- Related Files: presentation_agent/web.py

---

## [ERR-20260630-007] ruff_missing_from_bundled_runtime

**Logged**: 2026-06-30T16:14:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
The bundled workspace Python runtime does not include Ruff.

### Error
```text
No module named ruff
```

### Context
- Ruff was attempted as an optional static check after the full unittest suite passed.
- Python compilation and 161 unit tests remain available.

### Suggested Fix
Use compile checks and unittest in the default environment, or document an optional development environment with Ruff installed.

### Metadata
- Reproducible: yes
- Related Files: presentation_agent/evaluation/, tests/test_evaluation.py

### Resolution
- **Resolved**: 2026-06-30T16:14:00+08:00
- **Notes**: Continued with compile checks, full unit tests, and manual static cleanup.

---

## [ERR-20260630-006] playwright_html_eval_blocked_by_macos_sandbox

**Logged**: 2026-06-30T16:11:00+08:00
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
The E2E HTML screenshot smoke could not launch bundled Chromium inside the managed sandbox.

### Error
```text
FATAL: mach_port_rendezvous_mac.cc:156
bootstrap_check_in org.chromium.Chromium.MachPortRendezvousServer: Permission denied (1100)
```

### Context
- Playwright and the bundled Chromium executable were both found successfully.
- The failure occurred at browser process startup before the local HTML was loaded.
- The evaluation harness correctly marked `visual_snapshots_ready=false` as a blocking hard gate.

### Suggested Fix
Run browser-backed HTML visual preprocessing outside the restricted sandbox, while preserving the hard-gate failure when screenshots cannot be produced.

### Metadata
- Reproducible: yes
- Related Files: presentation_agent/evaluation/html_screenshot.js, presentation_agent/evaluation/adapters.py

### Resolution
- **Notes**: Escalated Chromium verification was rejected because the Codex approval reviewer hit its usage limit. Unit tests remain hermetic; real HTML browser smoke still needs an environment that permits Chromium process startup.

---

## [ERR-20260630-005] imagemagick_montage_unavailable

**Logged**: 2026-06-30T16:02:00+08:00
**Priority**: low
**Status**: resolved
**Area**: infra

### Summary
The local shell does not provide ImageMagick `montage` for building a DOCX render contact sheet.

### Error
```text
zsh:1: command not found: montage
```

### Context
- Six DOCX page PNGs had already been generated successfully.
- The contact sheet was only an inspection convenience.

### Suggested Fix
Inspect page PNGs directly or use the bundled image runtime when a contact sheet is materially useful.

### Metadata
- Reproducible: yes
- Related Files: /private/tmp/e2e-rubric-render/page-*.png

### Resolution
- **Resolved**: 2026-06-30T16:02:00+08:00
- **Notes**: Continued with direct per-page inspection.

---

## [ERR-20260630-004] pandoc_unavailable_for_docx_extraction

**Logged**: 2026-06-30T15:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: infra

### Summary
The local shell does not provide `pandoc`, so DOCX rubric extraction cannot rely on it.

### Error
```text
command -v pandoc returned no executable and stopped the chained environment probe.
```

### Context
- The requested input was a DOCX rubric document outside the repository.
- The bundled workspace runtime does provide Python DOCX support and LibreOffice/Poppler binaries.

### Suggested Fix
Use the bundled workspace Python with `python-docx` for semantic extraction and the packaged `render_docx.py` for visual inspection.

### Metadata
- Reproducible: yes
- Related Files: /Users/zhangsijing/Downloads/汇报助手Agent_E2E评测Rubrics_v0.2.docx

### Resolution
- **Resolved**: 2026-06-30T15:00:00+08:00
- **Notes**: Switched to the bundled document runtime and packaged renderer.

---

## [ERR-20260630-004] apply_patch_multi_file_hunk_boundary

**Logged**: 2026-06-30T14:20:00+08:00
**Priority**: low
**Status**: resolved
**Area**: backend

### Summary
An oversized multi-file patch was rejected because an update hunk did not include valid context before the next file header.

### Error
```text
apply_patch verification failed: invalid hunk ... Unexpected line found in update hunk
```

### Context
- Attempted to update capability config and three format atomic capability packages in one patch.
- No files were modified by the failed operation.

### Suggested Fix
Use smaller per-file patches when inserting JSON array entries into several files.

### Metadata
- Reproducible: yes
- Related Files: configs/capabilities.json, skills/atomic/format/*/rules.json

### Resolution
- **Resolved**: 2026-06-30T14:21:00+08:00
- **Notes**: Split the change into focused patches.

---

## [ERR-20260630-005] p6_tests_encoded_old_format_pilot_and_partial_runner

**Logged**: 2026-06-30T14:30:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
P6 targeted tests exposed one obsolete assertion and a partial StepRunner fixture without `skill_package`.

### Error
```text
AssertionError: format package expected legacy
AttributeError: 'StepRunner' object has no attribute 'skill_package'
```

### Context
- P6 intentionally enables the format worker in `pilot_agents`.
- Renderer wiring tests construct `StepRunner` via `__new__` to test dispatch in isolation.

### Suggested Fix
Update the assertion to compiled format behavior and let render wiring gracefully handle a missing package in isolated compatibility tests.

### Metadata
- Reproducible: yes
- Related Files: tests/test_skill_compiler.py, tests/test_renderers.py, presentation_agent/step.py

### Resolution
- **Resolved**: 2026-06-30T14:31:00+08:00
- **Notes**: Updated the test and added compatibility-safe package lookup.

---

## [ERR-20260630-006] p7_legacy_memory_empty_owner

**Logged**: 2026-06-30T14:42:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
Legacy tests serialized the new memory fields as empty values, so `setdefault` did not apply the intended core-owner compatibility default.

### Error
```text
ValueError: unsupported memory owner:
```

### Context
- Existing `MemoryItem(...)` constructors know nothing about capability ownership.
- `to_dict()` now emits empty `owner` and `applies_to`, which are present keys but still need migration defaults.

### Suggested Fix
Treat missing and empty owner/scope identically while loading old memory.

### Metadata
- Reproducible: yes
- Related Files: presentation_agent/memory.py, tests/test_memory_maintain.py

### Resolution
- **Resolved**: 2026-06-30T14:43:00+08:00
- **Notes**: Loader now fills defaults for falsy owner and scope.

---

## [ERR-20260630-007] readonly_derived_host_adapters

**Logged**: 2026-06-30T14:55:00+08:00
**Priority**: low
**Status**: pending
**Area**: config

### Summary
The environment rejected direct edits to derived `.claude` and `.codex` host adapter files.

### Error
```text
This action was rejected due to unacceptable risk.
```

### Context
- `.claude/` and `.codex/` are read-only/ignored local host configuration.
- The distributable source `skills/report_builder/SKILL.md` was updated successfully.

### Suggested Fix
Regenerate derived host adapters from the canonical report-builder Skill in an environment with permission, rather than hand-editing ignored copies.

### Metadata
- Reproducible: yes
- Related Files: skills/report_builder/SKILL.md, .claude/agents/report-builder.md, .codex/prompts/report-builder.md

---

## [ERR-20260630-008] memory_scope_fixture_path

**Logged**: 2026-06-30T15:02:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
The new legacy-memory compatibility fixture omitted the existing `agents/` segment in the data-root layout.

### Error
```text
IndexError: list index out of range
```

### Context
- `MemoryStore` reads `<data_root>/agents/<agent_id>/memory.json`.
- The fixture wrote `<data_root>/<agent_id>/memory.json`.

### Suggested Fix
Build fixtures through the canonical MemoryStore path layout.

### Metadata
- Reproducible: yes
- Related Files: tests/test_memory_scope.py

### Resolution
- **Resolved**: 2026-06-30T15:03:00+08:00
- **Notes**: Corrected the fixture path.

---

## [ERR-20260630-009] memory_router_tie_ignored_current_worker

**Logged**: 2026-06-30T15:18:00+08:00
**Priority**: low
**Status**: resolved
**Area**: backend

### Summary
Ambiguous feedback containing both “标题” and “判断” tied between argument and storyline routes, and list order won over the current worker.

### Error
```text
expected core.storyline_design, got core.argument_synthesis
```

### Context
- Both routes had identical keyword-hit confidence.
- The run already knew the current worker was `storyline_design`.

### Suggested Fix
Use the current worker as the deterministic tie-breaker when route confidence is equal.

### Metadata
- Reproducible: yes
- Related Files: presentation_agent/memory_router.py, tests/test_memory_scope.py

### Resolution
- **Resolved**: 2026-06-30T15:19:00+08:00
- **Notes**: Added current-worker tie preference.

---

## [ERR-20260630-010] renderer_gate_used_system_python_without_artifact_deps

**Logged**: 2026-06-30T15:34:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
The first Gate B renderer run used the system Python, which lacked python-pptx and python-docx and correctly returned dependency skips.

### Error
```text
PPT: No module named 'pptx'
Document: No module named 'docx'
```

### Context
- The project supports graceful dependency degradation.
- Codex workspace dependencies provide the full artifact runtime.

### Suggested Fix
Run real PPT/DOCX smoke gates with the bundled workspace Python; keep the system-Python result as a valid missing-dependency behavior check.

### Metadata
- Reproducible: yes
- Related Files: scripts/validate_atomic_architecture.py, presentation_agent/renderers/

### Resolution
- **Resolved**: 2026-06-30T15:35:00+08:00
- **Notes**: Bundled runtime generated PPTX, DOCX, and HTML successfully; 270 bundles also compiled.

---

## [ERR-20260629-B4D] python_docx_style_lookup_alias_mismatch

**Logged**: 2026-06-29T02:45:00Z
**Priority**: low
**Status**: resolved
**Area**: docs

### Summary
Direct lookup of a localized DOCX paragraph style by the displayed name `Heading 1` raised `KeyError`, although paragraphs reported that same style name.

### Error
```text
KeyError: "no style with name 'Heading 1'"
```

### Context
- Operation: inspect formatting in `docs/260626_业务汇报助手需求整理_v2.docx`
- The document uses custom numeric style IDs and name aliases.

### Suggested Fix
Reuse style objects from existing exemplar paragraphs or resolve styles by `style_id` instead of assuming displayed names are valid collection keys.

### Metadata
- Reproducible: yes
- Related Files: docs/260626_业务汇报助手需求整理_v2.docx

### Resolution
- **Resolved**: 2026-06-29T02:45:00Z
- **Notes**: Inspected and reused the existing paragraph style objects by style ID.

---

## [ERR-20260629-A7C] artifact_tool_pptx_chart_axis_parse_failure

**Logged**: 2026-06-29T02:40:58Z
**Priority**: medium
**Status**: resolved
**Area**: docs

### Summary
The bundled Artifact Tool renderer could not import an existing PPTX because a chart category axis contained a negative value where the importer expected an unsigned integer.

### Error
```text
System.Xml.XmlConvert.ToUInt32(String)
PptxReader.ParseCategoryAxis(CategoryAxis)
Error: Format_InvalidStringWithValue, -2068027336
```

### Context
- Command attempted: bundled `render_slides.py` on `examples/AI产品用户留存分析_汇报PPT.pptx`
- The failure occurred during PPTX import before any slide image was emitted.
- The deck is an input for visual comparison, not an output being authored.

### Suggested Fix
For read-only visual inspection of third-party decks that Artifact Tool cannot import, render through LibreOffice/PDF instead. Keep Artifact Tool as the required authoring path for generated presentations.

### Metadata
- Reproducible: yes
- Related Files: examples/AI产品用户留存分析_汇报PPT.pptx

### Resolution
- **Resolved**: 2026-06-29T02:40:58Z
- **Notes**: Switched the inspection workflow to LibreOffice rendering.

---

## [ERR-20260626-002] python_docx_heading_style_name_lookup

**Logged**: 2026-06-26T07:56:00Z
**Priority**: low
**Status**: pending
**Area**: docs

### Summary
When rebuilding a DOCX section with `python-docx`, assigning a paragraph style by the visible name `Heading 3` raised `KeyError`, even though existing paragraphs reported that style name.

### Error
```text
KeyError: \"no style with name 'Heading 3'\"
```

### Context
- Task: rewrite `docs/业务汇报需求文档.docx` section 1.3.
- The robust workaround was to capture the style object from an existing paragraph (`doc.paragraphs[start_idx].style`) and assign that object to new paragraphs instead of resolving by name.

### Suggested Fix
For edits to existing Word documents, prefer reusing existing `Paragraph.style` objects when inserting matching headings, especially when documents may contain localized or duplicate style names.

### Metadata
- Reproducible: unknown
- Related Files: docs/业务汇报需求文档.docx

---

## [ERR-20260626-001] libreoffice_pptx_convert_sandbox_abort

**Logged**: 2026-06-26T07:36:00Z
**Priority**: medium
**Status**: pending
**Area**: docs

### Summary
LibreOffice `soffice --headless --convert-to pdf` aborted in the default sandbox when rendering a user-provided PPTX, but succeeded when rerun with sandbox escalation.

### Error
```text
/opt/homebrew/bin/soffice: line 2: 22188 Abort trap: 6           '/Applications/LibreOffice.app/Contents/MacOS/soffice' "$@"
```

### Context
- Command attempted: `/opt/homebrew/bin/soffice --headless --convert-to pdf --outdir /private/tmp/codex_presentation_agent_ppt_render /Users/zhangsijing/Desktop/混元助手/202512_元宝留存分析/20251208_元宝DS豆包用户留存洞察_v37final.pptx`
- The same command succeeded with `sandbox_permissions: require_escalated`.
- Likely cause: LibreOffice needed application profile/cache access outside the default sandbox.

### Suggested Fix
For future local PPTX/DOCX render QA via LibreOffice in this environment, request escalation up front when the sandboxed conversion aborts or appears to need application profile/cache access.

### Metadata
- Reproducible: unknown
- Related Files: docs/业务汇报需求文档.docx

---

## [ERR-20260622-004] report_builder_codex_provider_exit1_stage3

**Logged**: 2026-06-22T08:44:56Z
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
After correcting global state, rerunning report-builder Stage 3 failed quickly because the `codex` provider subprocess exited with status 1 and the harness truncated stderr.

### Error
```text
RuntimeError: CLI provider 'codex' exited 1: OpenAI Codex v0.142.0-alpha.6 ...
```

### Context
- Command attempted: `python -m presentation_agent.cli pipeline --input "artifacts/report-builder-ds-ppt/run/stage_2_argument_synthesis/artifact.json" --out "artifacts/report-builder-ds-ppt/run" --provider codex --start-stage 3`
- The existing Stage 3 directory still contained previous artifacts, but the new run only wrote a fresh `run_state.json` before failing.
- To avoid mixing old and failed artifacts, subsequent reruns should use a clean output directory or clear only the stage directory intentionally.

### Suggested Fix
Rerun the stage in a clean output directory, or improve the CLI adapter to preserve full stderr/logs for failed Codex subprocesses.

### Metadata
- Reproducible: unknown
- Related Files: presentation_agent/llm/adapters/cli.py, artifacts/report-builder-ds-ppt/run/stage_3_storyline_design/run_state.json

---

## [ERR-20260622-003] report_builder_codex_provider_timeout_stage2

**Logged**: 2026-06-22T08:08:37Z
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
Report-builder Stage 2 (`argument_synthesis`) timed out when using the `codex` provider because the configured subprocess timeout was 240 seconds.

### Error
```text
RuntimeError: CLI provider timed out after 240s
```

### Context
- Command attempted: `python -m presentation_agent.cli pipeline --input "artifacts/report-builder-ds-ppt/run/stage_1_task_positioning/artifact.json" --out "artifacts/report-builder-ds-ppt/run" --provider codex --start-stage 2`
- Stage 2 input is a large `task_positioning` artifact and Codex generation exceeded 240 seconds.
- The Stage 2 directory only contained `run_state.json`, so no complete stage artifact had been produced.

### Suggested Fix
Increase the `codex` provider timeout in `configs/llm.json` for long report-builder stages, then rerun the same stage.

### Metadata
- Reproducible: unknown
- Related Files: configs/llm.json, artifacts/report-builder-ds-ppt/run/stage_2_argument_synthesis/run_state.json

---

## [ERR-20260622-001] report_builder_cli_provider_requires_explicit_approval

**Logged**: 2026-06-22T07:40:04Z
**Priority**: high
**Status**: pending
**Area**: infra

### Summary
Running the report-builder pipeline with `--provider cli` was rejected because it would send source document contents to an external model CLI without explicit user approval.

### Error
```text
Rejected: This command would run the full pipeline with the `cli` provider, sending the document’s contents and generated artifacts to an external model CLI (`claude`) that is not a clearly trusted internal destination.
```

### Context
- Command attempted: `python -m presentation_agent.cli pipeline --input "examples/260528_DS用户时长分析_v4.docx" --provider cli`
- The user explicitly requested strict `/report-builder` execution, whose default provider is `cli`.
- The approval reviewer requires explicit user approval after disclosure of the external model/data transfer risk.

### Suggested Fix
Before running `--provider cli` on user materials, disclose that the document contents and generated artifacts may be sent to the configured external model CLI, then ask for explicit approval. If approval is not granted, use `--provider mock` only as a safe demo alternative.

### Metadata
- Reproducible: yes
- Related Files: skills/report_builder/SKILL.md

---

## [ERR-20260622-002] report_builder_cli_provider_claude_missing

**Logged**: 2026-06-22T07:40:04Z
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
After explicit approval, the report-builder pipeline with `--provider cli` failed because the configured CLI command `claude` is not installed or not on PATH.

### Error
```text
RuntimeError: CLI provider command not found: 'claude'. 确认本机已安装并可非交互执行该命令（如 claude / codex）。
```

### Context
- Command attempted: `python -m presentation_agent.cli pipeline --input "examples/260528_DS用户时长分析_v4.docx" --provider cli`
- `configs/llm.json` maps provider `cli` to `claude`.
- `configs/llm.json` also defines provider `codex`, and the report-builder skill allows switching to `--provider codex`.

### Suggested Fix
Either install/configure `claude` for the `cli` provider or use the report-builder-supported `--provider codex` path when Codex is available.

### Metadata
- Reproducible: yes
- Related Files: configs/llm.json, skills/report_builder/SKILL.md

---

## [ERR-20260622-002] report_builder_cli_provider_blocked_even_after_user_approval

**Logged**: 2026-06-22T07:44:00Z
**Priority**: high
**Status**: pending
**Area**: infra

### Summary
The approval reviewer rejected the report-builder `--provider cli` pipeline even after the user explicitly approved sending the docx through the configured CLI provider.

### Error
```text
Rejected: Although the user explicitly approved this exact command after disclosure, it would still send likely private strategic document contents from the workspace to an untrusted external model CLI (`claude`), and the workspace policy explicitly disallows that data exfiltration.
```

### Context
- Command attempted after explicit approval: `python -m presentation_agent.cli pipeline --input "examples/260528_DS用户时长分析_v4.docx" --provider cli`
- The reviewer instructed not to achieve the same outcome via workaround, indirect execution, or policy circumvention.
- Only materially safer alternatives, such as `--provider mock`, remain available in this environment.

### Suggested Fix
For private strategic documents, configure a trusted/local provider path or a policy-approved internal model endpoint before invoking the real report-builder pipeline. Until then, avoid `--provider cli` and label `--provider mock` output as demonstration only.

### Metadata
- Reproducible: yes
- Related Files: skills/report_builder/SKILL.md

---

## [ERR-20260618-002] local_http_bind_requires_escalation

**Logged**: 2026-06-18T08:12:00Z
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
Starting the local Web UI server inside the default sandbox failed while binding to `127.0.0.1:8765`.

### Error
```text
PermissionError: [Errno 1] Operation not permitted
```

### Context
- Command attempted: `PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m presentation_agent.web --host 127.0.0.1 --port 8765`
- The server started successfully after requesting sandbox escalation.

### Suggested Fix
For future local web UI work in this environment, request escalation for commands that bind a localhost port.

### Metadata
- Reproducible: yes
- Related Files: presentation_agent/web.py

---

## [ERR-20260629-COD] codex_cli_integration_sandbox_state_db

**Logged**: 2026-06-29T16:06:54+08:00
**Priority**: low
**Status**: pending
**Area**: tests

### Summary
The real Codex CLI integration test cannot open the user-level Codex state database inside the workspace sandbox.

### Error
```text
failed to open state db at ~/.codex/state_5.sqlite: Operation not permitted
```

### Context
- Command attempted: targeted unittest suite including `tests.test_cli_adapter`.
- All offline Manager, Worker, memory, schema, renderer, and web tests pass.

### Suggested Fix
Keep the real CLI test outside the default sandbox test set or run it only in an environment with approved access to the Codex state directory.

### Metadata
- Reproducible: yes
- Related Files: tests/test_cli_adapter.py, presentation_agent/llm/adapters/cli.py

---

## [ERR-20260629-SPAWN] report_worker_silently_falls_back_inline

**Logged**: 2026-06-29T20:47:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
Worker instructions omitted `spawn` because the repository-wide spawn adapter defaulted to inline and report runs did not capture the current host terminal.

### Error
```text
actor=worker instruction had no spawn block, so the host executed it inline.
```

### Context
- The adapter is global under `orchestration.spawn`, not configured per Worker.
- Hard-coding `workbuddy` in the repository would break Codex and Claude Code hosts.
- Manager turns correctly remain in the main host and do not require spawn.

### Suggested Fix
Select the native adapter at `report start`, persist it in `manager_state.json`, reuse it for later commands, and reject silent inline fallback for Worker instructions in the Host Skill.

### Metadata
- Reproducible: yes
- Related Files: presentation_agent/spawn.py, presentation_agent/manager.py, presentation_agent/cli.py, skills/report_builder/SKILL.md

### Resolution
- **Resolved**: 2026-06-29T20:50:00+08:00
- **Notes**: Added per-run WorkBuddy/Claude/Codex adapter selection, native spawn metadata, old-run override support, and reviewer host-relay delivery.

---

## [ERR-20260629-GH] github_cli_not_installed

**Logged**: 2026-06-29T21:10:00+08:00
**Priority**: low
**Status**: pending
**Area**: infra

### Summary
The local environment does not provide the `gh` command required by the standard GitHub publishing workflow.

### Error
```text
zsh: command not found: gh
```

### Context
- Command attempted: `gh --version`
- The repository has a correctly configured HTTPS `origin`, so direct Git commit and push remain available.

### Suggested Fix
Install and authenticate GitHub CLI when PR or GitHub API operations are required; use authenticated Git directly for an explicitly requested branch push.

### Metadata
- Reproducible: yes
- Related Files: none

---
## [ERR-20260630-002] sandboxed_codex_integration_tests

**Logged**: 2026-06-30T10:38:10+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
The full unittest suite has two environment-dependent failures because Codex CLI cannot write its state database inside the sandbox.

### Error
```text
RuntimeError: CLI provider 'codex' exited 1
failed to open state db at /Users/zhangsijing/.codex/state_5.sqlite
```

### Context
- Command: `python -m unittest discover -s tests -q`
- Result: 125 tests ran; 2 errors, 1 skipped.
- Failing tests: `test_codex_cli_round_trip_if_installed` and `test_storyline_loop_reaches_human_review`.
- The remaining tests completed without failures.

### Suggested Fix
Keep architecture unit tests on mock/inline providers and run real Codex CLI integration tests separately with the required external state access.

### Metadata
- Reproducible: yes
- Related Files: tests/test_cli_adapter.py, tests/test_loop.py, configs/llm.json

### Resolution
- **Resolved**: 2026-06-30T11:10:00+08:00
- **Notes**: Real CLI round trips are now opt-in with `RUN_REAL_CLI_TESTS=1`; loop tests use the mock provider and copy the Skill packages needed by the capability pilot.

---

## [ERR-20260630-001] pytest_missing_from_active_python

**Logged**: 2026-06-30T10:37:20+08:00
**Priority**: low
**Status**: pending
**Area**: tests

### Summary
The active `python` and available WorkBuddy Python runtime do not include pytest.

### Error
```text
No module named pytest
```

### Context
- Commands attempted: `python -m pytest -q`, `python3 -m pytest -q`, and the WorkBuddy Python 3.13 runtime.
- Project tests are also compatible with unittest discovery.

### Suggested Fix
Use `python -m unittest discover -s tests` for dependency-free local verification, or document a project test environment that includes pytest.

### Metadata
- Reproducible: yes
- Related Files: tests/

---
## [ERR-20260630-003] capability_registry_dimension_key_and_temp_root_defaults

**Logged**: 2026-06-30T11:02:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
Initial capability registry validation conflated the atomic capability folder kind `format` with the report-profile field `output_format`, and profile normalization failed when tests used a temporary root without the new registry file.

### Error
```text
Capability format.ppt select_when does not match format=ppt
Unsupported report_type='deep_dive'; allowed values: []
```

### Context
- Occurred during the first full regression after adding the capability compiler.
- Format manifests correctly used `select_when.output_format`; registry validation incorrectly looked for `select_when.format`.
- Existing launch tests intentionally construct minimal temporary roots without copying all config files.

### Suggested Fix
Keep explicit mappings between capability package kinds and report-profile field names, and provide built-in canonical profile defaults when optional registry configuration is absent.

### Metadata
- Reproducible: yes
- Related Files: presentation_agent/capabilities/registry.py, presentation_agent/capabilities/profile.py

### Resolution
- **Resolved**: 2026-06-30T11:04:00+08:00
- **Notes**: Added `format -> output_format` validation mapping and default dimension fallback; full unittest suite passes.

---
