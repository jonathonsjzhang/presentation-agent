const state = {
  overview: null,
  learning: null,
  files: [],
  runs: [],
  selectedAgentId: null,
  selectedFile: null,
  activeFilter: "",
  activeTopView: "framework",
  activeView: "loop",
  agentTab: "overview",
  dirty: false,
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

function init() {
  bindActions();
  refreshAll();
}

function bindActions() {
  $("refreshButton").addEventListener("click", refreshAll);
  $("saveFileButton").addEventListener("click", saveCurrentFile);
  $("fileSearch").addEventListener("input", renderFiles);
  $("fileEditor").addEventListener("input", () => {
    if (!state.selectedFile) return;
    state.dirty = true;
    renderEditorMeta();
  });
  $("openAgentButton").addEventListener("click", () => setView("agent"));
  $("agentFilesButton").addEventListener("click", () => {
    focusAgentFiles(selectedAgent());
    setView("harness");
  });
  $("humanReviewForm").addEventListener("submit", submitHumanReview);

  document.querySelectorAll(".top-tab").forEach((button) => {
    button.addEventListener("click", () => setTopView(button.dataset.topView));
  });
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  bindInlineActions();
  document.querySelectorAll(".detail-tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.agentTab = button.dataset.agentTab;
      renderAgentTabs();
      renderAgentDetail();
    });
  });
  document.querySelectorAll(".filter-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeFilter = button.dataset.filter || "";
      $("fileSearch").value = "";
      renderFilterButtons();
      renderFiles();
    });
  });
}

async function refreshAll() {
  setStatus("Loading");
  try {
    const [overview, learning, filesResult, runsResult] = await Promise.all([
      api("/api/overview"),
      api("/api/learning"),
      api("/api/files"),
      api("/api/artifacts"),
    ]);
    state.overview = overview;
    state.learning = learning;
    state.files = (filesResult.files || []).filter(isHarnessFile);
    state.runs = runsResult.runs || overview.latest_runs || [];
    state.selectedAgentId ||= state.overview.agents[0]?.id;
    renderAll();
    setStatus("Ready", "ok");
  } catch (error) {
    state.overview = fallbackOverview();
    state.learning = fallbackLearning();
    state.files = [];
    state.runs = [];
    state.selectedAgentId ||= state.overview.agents[0]?.id;
    renderAll();
    setStatus("Static Preview");
    $("systemSubtitle").textContent = "静态框架页可直接浏览；启动本地服务后可编辑 harness 文件";
  }
}

function renderAll() {
  renderOverview();
  renderHealth();
  renderPipeline();
  renderLoopSteps();
  renderSelectedAgentSummary();
  renderAgentRail();
  renderAgentTabs();
  renderAgentDetail();
  renderLearning();
  renderFiles();
  renderRuns();
  renderEditorMeta();
}

function setView(view) {
  setTopView("cockpit");
  state.activeView = view || "loop";
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === state.activeView);
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("active-view", section.id === `${state.activeView}View`);
  });
}

function setTopView(view) {
  state.activeTopView = view || "framework";
  document.querySelectorAll(".top-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.topView === state.activeTopView);
  });
  document.querySelectorAll(".top-view").forEach((section) => {
    section.classList.toggle("active-top-view", section.id === `${state.activeTopView}TopView`);
  });
}

function renderOverview() {
  const pipeline = state.overview.pipeline || {};
  const mode = pipeline.mode || "human_triggered_sequential";
  const review = pipeline.human_review_required ? "human review required" : "human review optional";
  $("systemSubtitle").textContent = `${mode} · ${review}`;
  $("agentCount").textContent = `${state.overview.agents.length} agents`;
  $("loopStepCount").textContent = `${state.overview.loop_steps.length} steps`;
  $("runCount").textContent = `${state.runs.length} runs`;
}

function renderHealth() {
  const implemented = state.overview.agents.filter((agent) => statusLabel(agent) === "ready").length;
  const planned = state.overview.agents.length - implemented;
  const memoryFiles = state.files.filter((file) => file.path.startsWith("data/agents/")).length;
  const skillFiles = state.files.filter((file) => file.path.startsWith("skills/")).length;
  const capabilityPackages = state.overview.capabilities?.packages || [];
  const latest = state.runs[0]?.status || "no run";
  $("healthStrip").innerHTML = [
    healthItem("Runtime Ready", `${implemented}/${state.overview.agents.length}`, planned ? `${planned} planned` : "all ready"),
    healthItem("Skills", String(skillFiles), "rubrics / schemas / SOP"),
    healthItem("Capabilities", String(capabilityPackages.length), "6 core + 11 atomic"),
    healthItem("Memory", String(memoryFiles), "agent memory files"),
    healthItem("Latest Run", latest, state.runs[0]?.name || "waiting"),
  ].join("");
}

function healthItem(label, value, note) {
  return `
    <div class="health-item">
      <span>${label}</span>
      <strong>${value}</strong>
      <small>${note}</small>
    </div>
  `;
}

function renderPipeline() {
  const container = $("pipelineMap");
  container.innerHTML = "";
  state.overview.agents.forEach((agent) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `pipeline-node ${agent.id === state.selectedAgentId ? "active" : ""}`;
    button.innerHTML = `
      <span class="stage-number">${agent.stage}</span>
      <strong>${agent.name}</strong>
      <small>${agent.output_schema}</small>
    `;
    button.addEventListener("click", () => selectAgent(agent.id));
    container.appendChild(button);
  });
}

function renderLoopSteps() {
  const container = $("loopSteps");
  container.innerHTML = "";
  const learningSteps = [
    { id: "learning_capture", owner: "human + reviewer", description: "收集 sub-agent review 异议和人工 review 反馈，形成结构化学习事件" },
    { id: "memory_update", owner: "memory_store", description: "写入 learning_log，更新 hot memory；高频经验进入 rubric promotion 队列" },
  ];
  [...state.overview.loop_steps, ...learningSteps].forEach((step, index) => {
    const item = document.createElement("div");
    item.className = "loop-step";
    item.innerHTML = `
      <span class="loop-index">${index + 1}</span>
      <div>
        <strong>${step.id}</strong>
        <small>${step.owner}</small>
        <p>${step.description || ""}</p>
      </div>
    `;
    container.appendChild(item);
  });
}

function renderSelectedAgentSummary() {
  const agent = selectedAgent();
  if (!agent) return;
  $("selectedAgentTitle").textContent = `${agent.stage}. ${agent.name}`;
  $("selectedAgentSummary").innerHTML = `
    <p>${agent.description || ""}</p>
    <div class="handoff-strip">
      ${handoffPill(agent.previous_agent_id || "人发起 / 起点", "Input")}
      ${handoffPill(agent.output_contract?.primary_artifact || agent.output_schema, "Output")}
      ${handoffPill(agent.next_agent_id || "汇报交付", "Next")}
    </div>
    <div class="summary-grid">
      ${summaryBlock("输入关注", agent.input_contract?.input_preparation_focus || "读取上游产物与素材")}
      ${summaryBlock("放行标准", (agent.rubrics || []).slice(0, 2).join("；") || "通过 schema 与 P0 检查")}
      ${summaryBlock("Harness", `${agent.harness?.skill_package || "-"} · ${statusLabel(agent)}`)}
    </div>
  `;
}

function handoffPill(value, label) {
  return `
    <div class="handoff-pill">
      <span>${label}</span>
      <strong>${value}</strong>
    </div>
  `;
}

function summaryBlock(title, body) {
  return `
    <section class="summary-block">
      <h3>${title}</h3>
      <p>${body}</p>
    </section>
  `;
}

function renderAgentRail() {
  const rail = $("agentRail");
  rail.innerHTML = "";
  state.overview.agents.forEach((agent) => {
    const button = document.createElement("button");
    button.className = `agent-step ${agent.id === state.selectedAgentId ? "active" : ""}`;
    button.type = "button";
    button.innerHTML = `
      <span class="stage-number">${agent.stage}</span>
      <span class="agent-copy">
        <strong>${agent.name}</strong>
        <small>${agent.input_schema} -> ${agent.output_schema}</small>
      </span>
      <span class="agent-state">${statusLabel(agent)}</span>
    `;
    button.addEventListener("click", () => selectAgent(agent.id));
    rail.appendChild(button);
  });
}

function renderLearning() {
  renderReviewAgentOptions();
  const learning = state.learning || fallbackLearning();
  $("learningTotals").innerHTML = [
    healthItem("Hot Memory", String(learning.totals?.memory_items || 0), "used in generation/review"),
    healthItem("Learning Logs", String(learning.totals?.learning_logs || 0), "cold feedback records"),
    healthItem("Events", String(learning.totals?.learning_events || 0), "feedback / success / comparison"),
    healthItem("Promotion Queue", String(learning.totals?.promotion_candidates || 0), "ready for rubrics"),
  ].join("");
  const counts = learning.event_counts || {};
  $("eventCounts").innerHTML = Object.keys(counts).length
    ? Object.entries(counts).map(([name, count]) => `<span><strong>${name}</strong>${count}</span>`).join("")
    : `<span><strong>waiting</strong>no learning events yet</span>`;
  $("globalStateViewer").textContent = JSON.stringify(learning.global_state || {}, null, 2);

  const memoryList = $("memoryAgentList");
  memoryList.innerHTML = "";
  const agents = learning.agents || [];
  if (!agents.length) {
    memoryList.innerHTML = `<div class="empty-state">还没有 memory 数据</div>`;
  } else {
    agents.forEach((agent) => {
      const item = document.createElement("article");
      item.className = "memory-agent-card";
      const candidates = agent.promotion_candidates || [];
      item.innerHTML = `
        <div class="memory-agent-head">
          <div>
            <strong>${agent.stage}. ${agent.name}</strong>
            <span>${agent.id}</span>
          </div>
          <div class="memory-counts">
            <b>${agent.memory_count || 0}</b><small>memory</small>
            <b>${agent.learning_log_count || 0}</b><small>logs</small>
            <b>${candidates.length}</b><small>promote</small>
          </div>
        </div>
        <div class="memory-dimensions">${(agent.memory_dimensions || []).map((dim) => `<span>${dim}</span>`).join("")}</div>
        <div class="memory-dimensions">${(agent.recent_memory || []).map((memory) => `<span>${memory.owner || `core.${agent.id}`} · ${Object.entries(memory.applies_to || {}).map(([key, values]) => `${key}:${(values || []).join("|")}`).join(" ")}</span>`).join("")}</div>
        <div class="promotion-list">
          ${candidates.slice(0, 3).map((candidate) => `
            <button class="promotion-item" data-agent="${agent.id}" data-memory-id="${candidate.id}" type="button">
              <span>${candidate.id} · hits=${candidate.hit_count}</span>
              <span>${candidate.owner || "core"} · ${candidate.promotion_target || ""}</span>
              <strong>${candidate.suggestion}</strong>
            </button>
          `).join("") || "<p>暂无可升级 memory</p>"}
        </div>
      `;
      item.querySelectorAll(".promotion-item").forEach((button) => {
        button.addEventListener("click", () => promoteMemory(button.dataset.agent, button.dataset.memoryId));
      });
      memoryList.appendChild(item);
    });
  }

  const recent = $("recentLearningList");
  recent.innerHTML = "";
  const logs = learning.recent_logs || [];
  if (!logs.length) {
    recent.innerHTML = `<div class="empty-state">还没有 learning log</div>`;
  } else {
    logs.slice(0, 12).forEach((log) => {
      const item = document.createElement("article");
      item.className = "learning-log-row";
      item.innerHTML = `
        <span>${log.date || "-"}</span>
        <strong>${log.agent_id || "-"} · ${log.dimension || "-"}</strong>
        <p>${log.problem || ""}</p>
        <small>${log.change || ""}</small>
      `;
      recent.appendChild(item);
    });
  }
}

function renderReviewAgentOptions() {
  const select = $("reviewAgent");
  const currentValue = select.value || state.selectedAgentId;
  select.innerHTML = (state.overview?.agents || [])
    .map((agent) => `<option value="${agent.id}">${agent.stage}. ${agent.name}</option>`)
    .join("");
  select.value = currentValue || state.selectedAgentId || select.options[0]?.value || "";
}

function renderAgentTabs() {
  document.querySelectorAll(".detail-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.agentTab === state.agentTab);
  });
}

function renderAgentDetail() {
  const agent = selectedAgent();
  if (!agent) return;
  $("agentTitle").textContent = agent.name;
  $("agentStage").textContent = `Stage ${agent.stage} · ${agent.id}`;

  const renderers = {
    overview: renderAgentOverview,
    contract: renderAgentContract,
    state: renderAgentState,
    harness: renderAgentHarness,
    rubrics: renderAgentRubrics,
  };
  $("agentDetail").innerHTML = (renderers[state.agentTab] || renderAgentOverview)(agent);
}

function renderAgentOverview(agent) {
  return `
    <div class="detail-hero">
      <p>${agent.description || ""}</p>
      <div class="handoff-line">
        <span>${agent.previous_agent_id || "起点"}</span>
        <strong>${agent.id}</strong>
        <span>${agent.next_agent_id || "完成"}</span>
      </div>
    </div>
    <div class="detail-grid">
      ${detailCard("Primary Output", [agent.output_contract?.primary_artifact || agent.output_schema])}
      ${detailCard("Accepted Formats", agent.input_contract?.accepted_material_formats || [])}
      ${detailCard("Memory Dimensions", agent.memory_dimensions || [])}
      ${detailCard("Implementation", [agent.harness?.implementation_status || "defined"])}
    </div>
  `;
}

function renderAgentContract(agent) {
  return `
    <div class="detail-grid two-col">
      ${detailCard("Required Inputs", agent.input_contract?.required_inputs || [])}
      ${detailCard("Optional Inputs", agent.input_contract?.optional_inputs || [])}
      ${detailCard("Required Handoff Fields", agent.output_contract?.required_handoff_fields || [])}
      ${detailCard("Downstream Use", [agent.output_contract?.downstream_use || "由下一环节读取 primary artifact"])}
    </div>
  `;
}

function renderAgentState(agent) {
  return `
    <div class="detail-grid two-col">
      ${detailCard("Global Reads", agent.state?.global_reads || [])}
      ${detailCard("Global Writes", agent.state?.global_writes || [])}
      ${detailCard("Memory Scope", [agent.state?.agent_memory_scope || "-"])}
      ${detailCard("Generation Memory", agent.state?.generation_memory_dimensions || [])}
    </div>
  `;
}

function renderAgentHarness(agent) {
  const capabilityPackages = (state.overview.capabilities?.packages || [])
    .filter((item) => (item.applies_to || []).includes(agent.id))
    .map((item) => item.id);
  return `
    <div class="detail-grid two-col">
      ${detailCard("Skill Package", [agent.harness?.skill_package || "-"])}
      ${detailCard("Runtime Adapter", [agent.harness?.runtime_adapter || "-"])}
      ${detailCard("Review Policy", [agent.harness?.review_policy || "-"])}
      ${detailCard("Connectors", agent.harness?.connectors || [])}
      ${detailCard("Composable Capabilities", capabilityPackages)}
    </div>
  `;
}

function renderAgentRubrics(agent) {
  return `
    <div class="rubric-list">
      ${(agent.rubrics || []).map((item, index) => `
        <section class="rubric-item">
          <span>${index + 1}</span>
          <p>${item}</p>
        </section>
      `).join("")}
    </div>
  `;
}

function detailCard(title, rows) {
  const values = Array.isArray(rows) && rows.length ? rows : ["-"];
  return `
    <section class="detail-card">
      <h3>${title}</h3>
      <div>
        ${values.map((row) => `<p>${row}</p>`).join("")}
      </div>
    </section>
  `;
}

function renderRuns() {
  const list = $("runList");
  $("runCount").textContent = `${state.runs.length} runs`;
  list.innerHTML = "";
  if (!state.runs.length) {
    list.innerHTML = `<div class="empty-state">还没有可浏览的运行记录</div>`;
    return;
  }
  state.runs.slice(0, 12).forEach((run) => {
    const item = document.createElement("article");
    item.className = "run-card";
    item.innerHTML = `
      <div>
        <strong>${run.name}</strong>
        <span>${run.agent_id || "pipeline"} · ${run.status || "unknown"}</span>
        <span>${run.context_mode || "legacy_flat"} · ${run.legacy_skill ? "legacy" : "compiled"} · ${(run.selected_capabilities || []).join(" + ")}</span>
      </div>
      <div class="run-actions">
        ${run.artifact ? `<button data-path="${run.artifact}" type="button">artifact</button>` : ""}
        ${run.review ? `<button data-path="${run.review}" type="button">review</button>` : ""}
        ${run.run_state ? `<button data-path="${run.run_state}" type="button">state</button>` : ""}
        ${run.human_review ? `<button data-path="${run.human_review}" type="button">human</button>` : ""}
      </div>
    `;
    item.querySelectorAll("button[data-path]").forEach((button) => {
      button.addEventListener("click", () => {
        openFile(button.dataset.path);
        setView("harness");
      });
    });
    item.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      if (run.run_state) {
        $("reviewRunState").value = run.run_state;
        $("reviewAgent").value = run.agent_id || state.selectedAgentId || "";
        setView("learning");
      }
    });
    list.appendChild(item);
  });
}

function renderFiles() {
  const list = $("fileList");
  const query = $("fileSearch").value.trim().toLowerCase();
  const files = state.files.filter((file) => {
    const path = file.path.toLowerCase();
    return (!state.activeFilter || file.path.startsWith(state.activeFilter)) && (!query || path.includes(query));
  });
  $("fileCount").textContent = `${files.length} files`;
  list.innerHTML = "";
  if (!files.length) {
    list.innerHTML = `<div class="empty-state">没有匹配的 harness 文件</div>`;
    return;
  }
  files.forEach((file) => {
    const item = document.createElement("button");
    item.className = `file-row ${state.selectedFile === file.path ? "active" : ""}`;
    item.type = "button";
    item.innerHTML = `
      <span class="file-kind">${kindLabel(file.kind)}</span>
      <span class="file-copy">
        <strong>${shortPath(file.path)}</strong>
        <small>${file.path}</small>
      </span>
      <span class="file-mode">${file.editable ? "edit" : "read"}</span>
    `;
    item.addEventListener("click", () => openFile(file.path));
    list.appendChild(item);
  });
}

function renderFilterButtons() {
  document.querySelectorAll(".filter-button").forEach((item) => {
    item.classList.toggle("active", item.dataset.filter === state.activeFilter);
  });
}

function renderEditorMeta() {
  if (!state.selectedFile) {
    $("fileMeta").textContent = "select a file";
    return;
  }
  const file = state.files.find((item) => item.path === state.selectedFile);
  const mode = file?.editable ? "editable" : "read only";
  $("fileMeta").textContent = state.dirty ? `${mode} · unsaved` : mode;
}

function isHarnessFile(file) {
  const path = file.path || "";
  if (path.split("/").some((part) => part.startsWith("."))) return false;
  return (
    path.startsWith("configs/") ||
    path.startsWith("data/") ||
    path.startsWith("docs/") ||
    path.startsWith("skills/") ||
    path.startsWith("presentation_agent/") ||
    path === "README.md" ||
    path === "pyproject.toml"
  );
}

async function openFile(path) {
  if (!path) return;
  try {
    const file = await api(`/api/file?path=${encodeURIComponent(path)}`);
    state.selectedFile = file.path;
    state.dirty = false;
    $("currentFile").textContent = file.path;
    $("fileEditor").value = file.content;
    $("fileEditor").readOnly = !file.editable;
    $("saveFileButton").disabled = !file.editable;
    renderEditorMeta();
    renderFiles();
  } catch (error) {
    $("currentFile").textContent = error.message;
    $("fileEditor").value = "";
    $("fileEditor").readOnly = true;
    $("saveFileButton").disabled = true;
    showToast(error.message, "bad");
  }
}

async function saveCurrentFile() {
  if (!state.selectedFile) return;
  setStatus("Saving");
  try {
    await api("/api/file", {
      method: "POST",
      body: JSON.stringify({ path: state.selectedFile, content: $("fileEditor").value }),
    });
    state.dirty = false;
    await refreshAll();
    await openFile(state.selectedFile);
    setStatus("Saved", "ok");
    showToast("文件已保存", "ok");
  } catch (error) {
    setStatus("Save failed", "bad");
    showToast(error.message, "bad");
  }
}

async function submitHumanReview(event) {
  event.preventDefault();
  const feedback = {
    dimension: $("feedbackDimension").value.trim(),
    problem: $("feedbackProblem").value.trim(),
    reason: $("feedbackReason").value.trim(),
    change: $("feedbackChange").value.trim(),
  };
  const hasFeedback = feedback.dimension || feedback.problem || feedback.reason || feedback.change;
  setStatus("Recording");
  try {
    const result = await api("/api/human-review", {
      method: "POST",
      body: JSON.stringify({
        run_state_path: $("reviewRunState").value.trim(),
        agent_id: $("reviewAgent").value,
        decision: $("reviewDecision").value,
        notes: $("reviewNotes").value.trim(),
        feedback: hasFeedback ? feedback : {},
      }),
    });
    state.learning = result.learning;
    await refreshAll();
    setStatus("Recorded", "ok");
    showToast("人工 review 已记录，memory 已更新", "ok");
  } catch (error) {
    setStatus("Record failed", "bad");
    showToast(error.message, "bad");
  }
}

async function promoteMemory(agentId, memoryId) {
  if (!agentId || !memoryId) return;
  setStatus("Promoting");
  try {
    const result = await api("/api/memory/promote", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, item_ids: [memoryId] }),
    });
    state.learning = result.learning;
    renderLearning();
    setStatus("Promoted", "ok");
    showToast(`${memoryId} 已升级到 rubrics`, "ok");
  } catch (error) {
    setStatus("Promote failed", "bad");
    showToast(error.message, "bad");
  }
}

function selectAgent(agentId) {
  state.selectedAgentId = agentId;
  renderPipeline();
  renderSelectedAgentSummary();
  renderAgentRail();
  renderAgentDetail();
}

function focusAgentFiles(agent) {
  if (!agent) return;
  state.activeFilter = agent.harness?.skill_package || `skills/${agent.id}`;
  $("fileSearch").value = agent.id;
  renderFilterButtons();
  renderFiles();
}

function selectedAgent() {
  return state.overview?.agents.find((agent) => agent.id === state.selectedAgentId);
}

function statusLabel(agent) {
  const status = agent.harness?.implementation_status || "";
  if (status.includes("available")) return "ready";
  if (status.includes("pending")) return "planned";
  return "defined";
}

function setStatus(text, tone = "neutral") {
  const status = $("serverStatus");
  status.textContent = text;
  status.dataset.tone = tone;
}

function showToast(message, tone = "neutral") {
  const toast = $("toast");
  toast.textContent = message;
  toast.dataset.tone = tone;
  toast.classList.add("visible");
  window.setTimeout(() => toast.classList.remove("visible"), 2200);
}

function shortPath(path) {
  const parts = path.split("/");
  if (parts.length <= 3) return path;
  return `${parts[0]}/.../${parts.slice(-2).join("/")}`;
}

function kindLabel(kind) {
  return {
    markdown: "MD",
    json: "JSON",
    python: "PY",
    text: "TXT",
    file: "FILE",
  }[kind] || String(kind || "FILE").slice(0, 4).toUpperCase();
}

function fallbackOverview() {
  const stages = [
    ["manager", "汇报项目 Manager", "manager_context.v1", "manager_decision.v1", "定义任务、规划、派发 Worker、验收与返工"],
    ["analysis", "分析", "report_charter.v2", "analysis.v1", "形成发现、so what、反证、替代解释和置信度"],
    ["storyline", "故事线", "analysis.v1", "storyline.v3", "形成 Executive Summary、message pyramid 与章节结构"],
    ["report", "报告产出", "storyline.v3", "report.v1", "生成完整、可独立阅读的战略分析报告"],
    ["qa_preparation", "Q&A 梳理", "report.v1", "report.v1", "在报告末尾追加听众可能提出的深度问题"],
    ["format", "可视化", "report.v1", "formatted_material.v2", "默认生成精装文档，再按用户选择转译 PPT / HTML"],
  ];
  return {
    pipeline: {
      mode: "manager_controlled",
      human_review_required: true,
    },
    state_policy: {
      memory_soft_limit: 30,
    },
    loop_steps: [
      { id: "planning", owner: "manager", description: "Manager 定义 report charter 和执行计划" },
      { id: "dispatch", owner: "manager", description: "Manager 下发带验收标准的 task packet" },
      { id: "workflow", owner: "skill", description: "skill 读取 schema、global state、memory 和输入素材" },
      { id: "review", owner: "review_sub_agent", description: "干净上下文审查产物，输出 P0/P1 异议" },
      { id: "acceptance", owner: "manager", description: "Manager 决定 dispatch、revise、ask_human 或 complete" },
    ],
    agents: stages.map((stage, index) => ({
      id: stage[0],
      name: stage[1],
      stage: index + 1,
      input_schema: stage[2],
      output_schema: stage[3],
      description: stage[4],
      previous_agent_id: index === 0 ? null : stages[index - 1][0],
      next_agent_id: index === stages.length - 1 ? null : stages[index + 1][0],
      input_contract: {
        required_inputs: index === 0 ? ["raw brief", "Worker capabilities"] : ["Manager task packet"],
        optional_inputs: ["补充素材", "历史参考"],
        accepted_material_formats: ["json", "doc", "docx", "xlsx", "csv"],
        input_preparation_focus: "围绕当前环节的输入契约整理素材",
      },
      output_contract: {
        primary_artifact: stage[3],
        required_handoff_fields: ["schema", "agent_id", "核心字段"],
        downstream_use: "下游 Agent 读取并继续加工",
      },
      memory_dimensions: ["受众适配", "结构", "证据", "表达"],
      state: {
        agent_memory_scope: `${stage[0]}_only`,
        global_reads: index === 0 ? [] : ["report_charter", "target_action"],
        global_writes: index === 0 ? ["report_charter", "execution_plan"] : [],
        generation_memory_dimensions: ["结构", "表达"],
      },
      harness: {
        skill_package: `skills/${stage[0]}`,
        runtime_adapter: "generic_llm_skill_runtime",
        review_policy: "schema_validation + rubric_p0 + llm_p1",
        connectors: ["doc", "docx", "xlsx", "csv"],
        implementation_status: index === 2 ? "sample_runtime_available" : "skill_package_ready_runtime_pending",
      },
      rubrics: ["按 schema 交接", "清除 P0 后进入人工 review", "反馈沉淀到本环节 memory"],
    })),
    latest_runs: [],
  };
}

function fallbackLearning() {
  return {
    global_state: {},
    state_policy: {
      memory_soft_limit: 30,
      rubric_promotion_threshold: 3,
    },
    totals: {
      memory_items: 0,
      learning_logs: 0,
      learning_events: 0,
      promotion_candidates: 0,
    },
    event_counts: {},
    recent_events: [],
    agents: [],
    recent_logs: [],
  };
}

// ---- Inline single-step pipeline controller --------------------------------

const inline = {
  runName: null,
  stageView: null,
  pipeline: null,
};

function bindInlineActions() {
  $("inlineInitForm").addEventListener("submit", (event) => {
    event.preventDefault();
    inlineInit();
  });
  $("inlinePrepareButton").addEventListener("click", inlinePrepare);
  $("inlineWriteOutputButton").addEventListener("click", inlineWriteOutput);
  $("inlineCommitButton").addEventListener("click", inlineCommit);
  $("inlineAdvanceButton").addEventListener("click", inlineAdvance);
}

async function inlineInit() {
  const runName = ($("inlineRunName").value || "ui_inline").trim();
  const inputPath = ($("inlineInputPath").value || "examples/raw_brief.json").trim();
  try {
    const res = await api("/api/step/init", {
      method: "POST",
      body: JSON.stringify({ run_name: runName, input_path: inputPath }),
    });
    inline.runName = res.run_name;
    inline.pipeline = res.pipeline;
    await inlineRefresh();
    showToast("流水线已初始化", "positive");
  } catch (err) {
    showToast(`初始化失败：${err.message}`, "negative");
  }
}

async function inlineRefresh() {
  if (!inline.runName) return;
  try {
    const res = await api(`/api/step/status?run_name=${encodeURIComponent(inline.runName)}`);
    inline.pipeline = res.pipeline;
    inline.stageView = res.stage;
    renderInline();
  } catch (err) {
    showToast(`刷新失败：${err.message}`, "negative");
  }
}

async function inlinePrepare() {
  if (!inline.runName) return;
  try {
    const res = await api("/api/step/prepare", {
      method: "POST",
      body: JSON.stringify({ run_name: inline.runName }),
    });
    inline.stageView = res.stage;
    renderInline();
    showToast(`已生成 ${res.result.step || ""} 指令`, "positive");
  } catch (err) {
    showToast(`prepare 失败：${err.message}`, "negative");
  }
}

async function inlineWriteOutput() {
  if (!inline.runName) return;
  const text = $("inlineOutput").value.trim();
  if (!text) {
    showToast("请先粘贴宿主模型产物 JSON", "negative");
    return;
  }
  try {
    await api("/api/step/output", {
      method: "POST",
      body: JSON.stringify({ run_name: inline.runName, output_json: text }),
    });
    await inlineRefresh();
    showToast("产物已写入 handoff", "positive");
  } catch (err) {
    showToast(`写入失败：${err.message}`, "negative");
  }
}

async function inlineCommit() {
  if (!inline.runName) return;
  try {
    const res = await api("/api/step/commit", {
      method: "POST",
      body: JSON.stringify({ run_name: inline.runName }),
    });
    inline.stageView = res.stage;
    const present = res.result && res.result.present_to_user;
    if (present) {
      $("inlinePresent").textContent = typeof present === "string"
        ? present
        : JSON.stringify(present, null, 2);
    }
    renderInline();
    showToast("commit 完成", "positive");
  } catch (err) {
    showToast(`commit 失败：${err.message}`, "negative");
  }
}

async function inlineAdvance() {
  if (!inline.runName) return;
  try {
    const res = await api("/api/step/advance", {
      method: "POST",
      body: JSON.stringify({ run_name: inline.runName }),
    });
    inline.pipeline = res.pipeline;
    $("inlineOutput").value = "";
    $("inlinePresent").textContent = "commit 后显示产物摘要 + 审查结论 + 记忆更新。";
    await inlineRefresh();
    showToast("已进入下一环节", "positive");
  } catch (err) {
    showToast(`advance 失败：${err.message}`, "negative");
  }
}

function renderInline() {
  const stage = inline.stageView || {};
  const step = stage.current_step || "uninitialized";

  // pill + stages
  $("inlineStatusPill").textContent = inline.runName ? inline.runName : "未启动";
  renderInlineStages();

  // step title / badge
  const stepLabel = {
    init: "待 prepare 生成指令",
    awaiting_gen_output: "等待写入生成产物",
    gen_completed: "生成完成，待 prepare 审查",
    review_completed: "审查完成",
    awaiting_revise_output: "等待写入返工产物",
    done: "本环节已完成",
    uninitialized: "未初始化",
  }[step] || step;
  const agentName = stage.agent_name ? `${stage.agent_name} · ` : "";
  $("inlineStepTitle").textContent = `${agentName}${stepLabel}`;
  $("inlineStepBadge").textContent = step;

  // instruction + output
  $("inlineInstruction").textContent = stage.instruction_text || "prepare 后这里显示指令。";
  if (typeof stage.output_text === "string" && document.activeElement !== $("inlineOutput")) {
    $("inlineOutput").value = stage.output_text;
  }

  // review
  renderInlineReview(stage.review);
  // rendered deliverables
  renderInlineRendered(stage.rendered_files);

  // button enablement
  const has = !!inline.runName;
  const awaitingOutput = step === "awaiting_gen_output" || step === "awaiting_revise_output";
  const canPrepare = has && (step === "init" || step === "gen_completed" || step === "review_completed");
  const canCommit = has && awaitingOutput;
  const canAdvance = has && step === "done" && !inlineIsLastStage();
  $("inlinePrepareButton").disabled = !canPrepare;
  $("inlineCommitButton").disabled = !canCommit;
  $("inlineWriteOutputButton").disabled = !awaitingOutput;
  $("inlineAdvanceButton").disabled = !canAdvance;
}

function renderInlineStages() {
  const host = $("inlineStages");
  const stages = (inline.pipeline && inline.pipeline.stages) || [];
  if (!stages.length) {
    host.innerHTML = '<p class="muted">初始化后显示 5 个 worker 进度。</p>';
    return;
  }
  const current = inline.pipeline.current_stage || 1;
  host.innerHTML = stages.map((s) => {
    const isCurrent = s.index === current;
    const done = s.status && s.status.includes("review");
    const cls = isCurrent ? "current" : done ? "done" : "pending";
    return `<div class="inline-stage ${cls}"><span class="idx">${s.index}</span>`
      + `<span class="nm">${escapeHtml(s.agent_name || s.agent_id)}</span>`
      + `<span class="st">${escapeHtml(s.status || "pending")}</span></div>`;
  }).join("");
}

function renderInlineReview(review) {
  const host = $("inlineReview");
  if (!review) {
    host.textContent = "尚无审查结果。";
    return;
  }
  const p0 = review.p0 || [];
  const p1 = review.p1 || [];
  const block = (label, items, tone) => {
    if (!items.length) return `<div class="rev-line ${tone}">${label}: 0</div>`;
    const lis = items.map((o) =>
      `<li><code>${escapeHtml(o.id || o.rubric_id || "")}</code> ${escapeHtml(o.message || "")}</li>`
    ).join("");
    return `<div class="rev-line ${tone}">${label}: ${items.length}</div><ul class="rev-list">${lis}</ul>`;
  };
  host.innerHTML = `<div class="rev-summary">reviewer: ${escapeHtml(review.reviewer || "-")}</div>`
    + block("P0", p0, p0.length ? "bad" : "good")
    + block("P1", p1, "warn");
}

function renderInlineRendered(files) {
  const host = $("inlineRendered");
  if (!files || !files.length) {
    host.textContent = "尚无渲染产物（report 出内容文档、format 出可视化版本）。";
    return;
  }
  host.innerHTML = files.map((f) =>
    `<div class="rendered-file"><span class="kind">${escapeHtml((f.kind || "").toUpperCase())}</span>`
    + `<span class="nm">${escapeHtml(f.name)}</span>`
    + `<span class="sz">${(f.size / 1024).toFixed(1)} KB</span>`
    + `<code class="pth">${escapeHtml(f.path)}</code></div>`
  ).join("");
}

function inlineIsLastStage() {
  const stages = (inline.pipeline && inline.pipeline.stages) || [];
  const current = (inline.pipeline && inline.pipeline.current_stage) || 1;
  return current >= stages.length;
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

init();
