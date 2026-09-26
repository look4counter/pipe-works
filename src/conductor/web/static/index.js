let displayedProcesses = [];
const MAX_LOG_LINES = 500;
const processes = [];
const latestStatistics = new Map();
let activeStatCount = null;

function updateStatTooltip(countElement) {
  let tooltip = document.querySelector("#stat-tooltip");
  if (!tooltip) {
    tooltip = document.createElement("div");
    tooltip.id = "stat-tooltip";
    tooltip.className = "stat-tooltip";
    tooltip.setAttribute("role", "tooltip");
    tooltip.hidden = true;
    document.body.append(tooltip);
  }

  tooltip.textContent = countElement.dataset.exactCount || "0";
  tooltip.hidden = false;
  const countRect = countElement.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  const left = Math.max(
    8,
    Math.min(countRect.left, window.innerWidth - tooltipRect.width - 8),
  );
  const above = countRect.top - tooltipRect.height - 8;
  const top = above >= 8
    ? above
    : Math.min(window.innerHeight - tooltipRect.height - 8, countRect.bottom + 8);
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${Math.max(8, top)}px`;
}

document.addEventListener("pointerover", (event) => {
  const countElement = event.target.closest?.(".stat-count");
  if (!countElement) return;
  activeStatCount = countElement;
  updateStatTooltip(countElement);
});

document.addEventListener("pointerout", (event) => {
  const countElement = event.target.closest?.(".stat-count");
  if (!countElement || countElement.contains(event.relatedTarget)) return;
  activeStatCount = null;
  const tooltip = document.querySelector("#stat-tooltip");
  if (tooltip) tooltip.hidden = true;
});

function escapeHtml(value) {
  return String(value).replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character],
  );
}

function toBoolean(value) {
  return value === true || value === 1 || value === "1";
}

function formatCount(value) {
  const count = Number(value || 0);
  if (count >= 1_000_000_000) {
    return `${(count / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 6 })}M`;
  }
  if (count >= 1_000_000) {
    return `${(count / 1_000).toLocaleString(undefined, { maximumFractionDigits: 3 })}K`;
  }
  return count.toLocaleString();
}

function formatExactCount(value) {
  return Number(value || 0).toLocaleString();
}

function normalizeProcess(process) {
  const statistics = process.statistics || {};

  return {
    source: process,
    name: process.name || process.process_id || process.id,
    description: process.description || "",
    pid: process.pid,
    gpu: process.gpu_id ?? process.gpuid ?? process.gpu ?? null,
    fps: process.fps ?? null,
    pipeType: process.pipe_type || "nvidia",
    metadataEnabled: toBoolean(process.metadata_enabled),
    inferenceEnabled: toBoolean(process.inference_enabled),
    postprocessEnabled: toBoolean(process.postprocess_enabled),
    frameType: process.inference_frame || process.frameType || "-",
    input: process.input || process.input_rtsp_url || "",
    inputState:
      process.inputState || process.input_state || process.desired_state,
    output: process.output || process.output_rtsp_url || "",
    outputState:
      process.outputState || process.output_state || process.desired_state,
    state: process.state === "running" ? "running" : "stopped",
    statistics: {
      received: statistics.received ?? process.received_frame_count ?? 0,
      sent: statistics.sent ?? process.sent_frame_count ?? 0,
      anomalous: statistics.anomalous ?? process.anomalous_frame_count ?? 0,
      inferenceFailed:
        statistics.inferenceFailed ??
        process.inference_failure_frame_count ??
        0,
      postprocessFailed:
        statistics.postprocessFailed ??
        process.postprocess_failure_frame_count ??
        0,
      average_ms: statistics.average_ms ?? null,
    },
    config: {
      pipeType: process.pipe_type,
      inputUrl: process.input_rtsp_url,
      inputTransport: process.input_rtsp_transport,
      outputUrl: process.output_rtsp_url,
      outputTransport: process.output_rtsp_transport,
      metadataEnabled: toBoolean(process.metadata_enabled),
      metadataModule: process.metadata_path,
      inferenceEnabled: toBoolean(process.inference_enabled),
      intervalFrames: process.inference_interval,
      inferenceModule: process.inference_path,
      postprocessEnabled: toBoolean(process.postprocess_enabled),
      postprocessModule: process.postprocess_path,
      logLevel: process.log_level || "INFO",
      desiredState: toBoolean(process.auto_start),
    },
  };
}

function restoreGpuId(process, setValue) {
  setValue("gpuid", process.gpu ?? 0);
}

function renderProcesses(processes) {
  const container = document.querySelector("#process-list");
  if (!container) return;
  displayedProcesses = processes.map(normalizeProcess);
  if (displayedProcesses.length === 0) {
    container.classList.add("is-empty");
    container.innerHTML =
      '<p class="empty-state">등록된 프로세스가 없습니다.</p>';
    return;
  }

  container.classList.remove("is-empty");
  container.innerHTML = displayedProcesses
    .map((process, index) => {
      const running = process.state === "running";
      const stateClass = running ? "is-running" : "is-stopped";
      const name = escapeHtml(process.name);
      const description = process.description.trim();
      const heading = description
        ? `${name} (${escapeHtml(description)})`
        : name;
      const details = process.pipeType.toUpperCase();
      const stageIcon = (label, stage, enabled, modulePath) =>
        `<button class="stage-icon${enabled ? " is-enabled" : ""}" type="button" data-module-stage="${stage}" data-process-id="${escapeHtml(process.source.process_id)}"${modulePath ? "" : " disabled"} title="${label}: ${enabled ? "enabled" : "disabled"}${modulePath ? " — click to open file" : " — no file configured"}" aria-label="${label}: ${enabled ? "enabled" : "disabled"}">${label}</button>`;
      const stageIcons = [
        stageIcon("Metadata", "metadata", process.metadataEnabled, process.config.metadataModule),
        stageIcon("Inference", "inference", process.inferenceEnabled, process.config.inferenceModule),
        stageIcon("PostProcess", "postprocess", process.postprocessEnabled, process.config.postprocessModule),
      ].join("");
      const deleteAction = `<button class="context-delete-button" type="button" role="menuitem" data-process-index="${index}">삭제</button>`;
      const actions = `<button class="move-button" type="button" draggable="true" aria-label="Move ${name}" title="Drag to reorder ${name}">&#x283F;</button><button class="start-button" type="button" data-process-index="${index}" title="Start ${name}">▶</button><button class="danger-button" type="button" data-process-index="${index}" title="Stop ${name}">■</button><div class="process-menu-container"><button class="more-button" type="button" data-process-index="${index}" aria-haspopup="menu" aria-expanded="false" title="${name} 메뉴">…</button><div class="process-context-menu" role="menu" hidden><button class="context-edit-button" type="button" role="menuitem" data-process-index="${index}">편집</button>${deleteAction}</div></div>`;
      const statistics = process.statistics || {};
      const count = (field) => `<span class="stat-count" data-exact-count="${formatExactCount(statistics[field])}">${formatCount(statistics[field])}</span>`;
      return `<article class="process-card ${stateClass}" data-process-id="${name}"><div class="process-identity"><span class="process-icon" aria-hidden="true">${running ? "\u25b6" : "\u25a0"}</span><div><h3>${heading}</h3><p><span class="pipe-type">${escapeHtml(details)}</span><span class="stage-icons">${stageIcons}</span></p></div></div><div class="process-route"><span class="endpoint ${process.inputState === "running" ? "is-running" : ""}">${escapeHtml(process.input)}</span><span aria-hidden="true">→</span><span class="endpoint ${process.outputState === "running" ? "is-running" : ""}">${escapeHtml(process.output)}</span></div><div class="process-actions">${actions}</div><dl class="process-statistics"><div><dt>수신</dt><dd data-stat="received">${count("received")}</dd></div><div><dt>송출</dt><dd data-stat="sent">${count("sent")}</dd></div><div class="warning"><dt>비정상</dt><dd data-stat="anomalous">${count("anomalous")}</dd></div><div class="failure"><dt>추론 실패</dt><dd data-stat="inferenceFailed">${count("inferenceFailed")}</dd></div><div class="failure"><dt>후처리 실패</dt><dd data-stat="postprocessFailed">${count("postprocessFailed")}</dd></div></dl></article>`;
    })
    .join("");

  container.querySelectorAll(".process-route").forEach((route, index) => {
    const average = document.createElement("span");
    average.className = "process-average";
    average.dataset.stat = "average_ms";
    average.textContent = formatAverageMs(
      displayedProcesses[index].statistics.average_ms,
    );
    route.append(average);
  });

  container.querySelectorAll(".process-context-menu").forEach((menu, index) => {
    const logButton = document.createElement("button");
    logButton.className = "context-log-button";
    logButton.type = "button";
    logButton.setAttribute("role", "menuitem");
    logButton.dataset.processIndex = String(index);
    logButton.textContent = "로그";
    menu.insertBefore(logButton, menu.querySelector(".context-delete-button"));

    const copyButton = document.createElement("button");
    copyButton.className = "context-copy-button";
    copyButton.type = "button";
    copyButton.setAttribute("role", "menuitem");
    copyButton.dataset.processIndex = String(index);
    copyButton.textContent = "복제";
    logButton.after(copyButton);
  });
}

function formatAverageMs(value) {
  return value === null || !Number.isFinite(Number(value))
    ? "— ms/F"
    : `${Number(value).toFixed(2)} ms/F`;
}

function updateProcessStatistics(process) {
  const card = [...document.querySelectorAll(".process-card")].find(
    (item) => item.dataset.processId === process.process_id,
  );
  if (!card) return;

  for (const [field, value] of Object.entries(process.statistics || {})) {
    const valueElement = card.querySelector(`[data-stat="${field}"]`);
    if (valueElement) {
      if (field === "average_ms") {
        valueElement.textContent = formatAverageMs(value);
      } else {
        const countElement = valueElement.querySelector(".stat-count");
        if (countElement) {
          countElement.textContent = formatCount(value);
          countElement.dataset.exactCount = formatExactCount(value);
          if (activeStatCount === countElement) {
            updateStatTooltip(countElement);
          }
        }
      }
    }
  }
}

function updateProcessState(process) {
  const card = [...document.querySelectorAll(".process-card")].find(
    (item) => item.dataset.processId === process.process_id,
  );
  if (!card) return;

  const running = process.state === "running";
  const stopped = !running;
  card.classList.toggle("is-running", running);
  card.classList.toggle("is-stopped", stopped);
  const icon = card.querySelector(".process-icon");
  if (icon) {
    icon.textContent = running ? "\u25b6" : "\u25a0";
    const label = running ? "Running" : "Stopped";
    icon.title = label;
    icon.setAttribute("aria-label", label);
  }
}

function setProcessState(processId, state) {
  if (state !== "running" && state !== "stopped") return;
  const process = processes.find((item) => item.process_id === processId);
  if (!process || process.state === state) return;

  process.state = state;
  updateProcessState(process);
}

document.addEventListener("DOMContentLoaded", () => {
  const dialog = document.querySelector("#add-process-dialog");
  const form = document.querySelector("#add-process-form");
  const openButton = document.querySelector("#open-add-process");
  const dialogTitle = document.querySelector("#dialog-title");
  const submitButton = document.querySelector("#dialog-submit");
  const nameInput = form?.elements.namedItem("name");
  const formError = document.querySelector("#process-form-error");
  const actionDialog = document.querySelector("#action-confirm-dialog");
  const actionDialogTitle = document.querySelector("#action-confirm-title");
  const actionProcessName = document.querySelector("#action-process-name");
  const actionConfirmMessage = document.querySelector(
    "#action-confirm-message",
  );
  const duplicateDialog = document.querySelector("#duplicate-confirm-dialog");
  const duplicateSourceName = document.querySelector("#duplicate-source-name");
  const duplicateProcessIdInput = document.querySelector(
    "#duplicate-process-id",
  );
  const duplicateProcessError = document.querySelector("#duplicate-process-error");
  const confirmDuplicateButton = document.querySelector(
    "#confirm-process-duplicate",
  );
  const cancelDuplicateButton = document.querySelector(
    "#cancel-process-duplicate",
  );
  const actionProcessError = document.querySelector("#action-process-error");
  const confirmActionButton = document.querySelector("#confirm-process-action");
  const cancelActionButton = document.querySelector("#cancel-process-action");
  const logDialog = document.querySelector("#process-log-dialog");
  const logDialogTitle = document.querySelector("#process-log-title");
  const logProcessName = document.querySelector("#process-log-process-name");
  const logOutput = document.querySelector("#process-log-output");
  const closeLogButton = document.querySelector("#close-process-logs");
  let saving = false;
  let pendingProcessAction = null;
  let pendingDuplicateProcess = null;
  let logLines = [];
  let logSocket = null;
  let activeLogProcessId = null;
  function syncStageRequired() {
    const bypass = form.elements.namedItem("pipe_type").value === "bypass";
    ["metadata", "inference", "postprocess"].forEach((stage) => {
      const enabled = form.elements.namedItem(`${stage}_enabled`);
      enabled.disabled = bypass;
      if (bypass) enabled.checked = false;
      form.elements.namedItem(`${stage}_path`).required = !bypass && enabled.checked;
    });
  }
  ["metadata_enabled", "inference_enabled", "postprocess_enabled"].forEach((name) => {
    form?.elements.namedItem(name).addEventListener("change", syncStageRequired);
  });
  form?.elements.namedItem("pipe_type").addEventListener("change", syncStageRequired);
  const closeButtons = document.querySelectorAll(
    "#close-add-process, #cancel-add-process",
  );

  function setValue(name, value) {
    const field = form?.elements.namedItem(name);
    if (field && value !== undefined) field.value = value;
  }

  function setChecked(name, checked) {
    const field = form?.elements.namedItem(name);
    if (field) field.checked = checked;
  }

  function showAddDialog() {
    form?.reset();
    formError.textContent = "";
    syncStageRequired();
    dialogTitle.textContent = "Add Process";
    nameInput.readOnly = false;
    document.querySelectorAll(".module-current").forEach((hint) => {
      hint.hidden = true;
    });
    dialog?.showModal();
  }

  function showEditDialog(process) {
    formError.textContent = "";
    const config = {
      inputTransport: "tcp",
      jitterBuffer: 30,
      outputTransport: "tcp",
      inferenceEnabled: true,
      inputFormat: "native",
      metadataEnabled: true,
      metadataModule: "",
      inferenceModule: "examples/timestamp.py",
      postprocessEnabled: true,
      postprocessModule: "examples/postprocess.py",
      desiredState: false,
      logLevel: "INFO",
      ...process.config,
    };
    dialogTitle.textContent = "Edit Process";
    submitButton.textContent = "저장";
    setValue("name", process.name);
    setValue("description", process.description);
    nameInput.readOnly = true;
    setChecked("auto_start", config.desiredState);
    setValue("input_rtsp_url", config.inputUrl || process.input);
    setValue("input_rtsp_transport", config.inputTransport || "tcp");
    setValue("output_rtsp_url", config.outputUrl || `rtsp://${process.output}`);
    setValue("output_rtsp_transport", config.outputTransport || "tcp");
    setChecked("inference_enabled", config.inferenceEnabled ?? true);
    restoreGpuId(process, setValue);
    setValue("fps", process.fps);
    setValue("log_level", config.logLevel || "INFO");
    setValue("pipe_type", process.config.pipeType || "nvidia");
    setValue("inference_interval", config.intervalFrames ?? "");
    setValue("inference_frame", process.frameType === "-" ? "pytorch" : process.frameType);
    setChecked("metadata_enabled", config.metadataEnabled ?? true);
    setValue("metadata_path", config.metadataModule);
    setValue("inference_path", config.inferenceModule);
    setChecked("postprocess_enabled", config.postprocessEnabled ?? true);
    setValue("postprocess_path", config.postprocessModule);
    syncStageRequired();
    dialog?.showModal();
  }

  function closeProcessMenus(except = null) {
    document.querySelectorAll(".process-context-menu").forEach((menu) => {
      if (menu === except) return;
      menu.hidden = true;
      menu.parentElement
        ?.querySelector(".more-button")
        ?.setAttribute("aria-expanded", "false");
    });
  }

  function appendLog(event) {
    if (!logOutput) return;
    const timestamp = event.created_at
      ? new Date(event.created_at * 1000).toLocaleTimeString()
      : new Date().toLocaleTimeString();
    const exception = event.exception ? `\n${event.exception}` : "";
    logLines.push(
      `[${timestamp}] [${event.level || "INFO"}] [${event.logger || "stream"}] ${event.message || ""}${exception}`,
    );
    if (logLines.length > MAX_LOG_LINES) {
      logLines.splice(0, logLines.length - MAX_LOG_LINES);
    }
    logOutput.textContent = `${logLines.join("\n")}\n`;
    logOutput.scrollTop = logOutput.scrollHeight;
  }

  function closeLogDialog() {
    activeLogProcessId = null;
    if (logSocket) {
      logSocket.close();
      logSocket = null;
    }
  }

  function connectStatisticsSocket() {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(
      `${scheme}//${window.location.host}/ws/process-stats`,
    );
    socket.addEventListener("message", (event) => {
      try {
        const update = JSON.parse(event.data);
        if (
          typeof update.process_id !== "string" ||
          !update.statistics ||
          typeof update.statistics !== "object"
        ) {
          return;
        }
        latestStatistics.set(update.process_id, update.statistics);
        const process = processes.find(
          (item) => item.process_id === update.process_id,
        );
        if (process) {
          process.statistics = update.statistics;
          updateProcessStatistics(update);
        }
      } catch (error) {
        console.error("프로세스 통계 메시지를 해석하지 못했습니다.", error);
      }
    });
    socket.addEventListener("close", () => {
      window.setTimeout(connectStatisticsSocket, 2000);
    });
    socket.addEventListener("error", () => socket.close());
  }

  function connectProcessStatusSocket() {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(
      `${scheme}//${window.location.host}/ws/process-status`,
    );
    socket.addEventListener("message", (event) => {
      try {
        const update = JSON.parse(event.data);
        if (!Array.isArray(update.processes)) return;

        const states = new Map(
          update.processes
            .filter(
              (item) =>
                typeof item.process_id === "string" &&
                (item.state === "running" || item.state === "stopped"),
            )
            .map((item) => [item.process_id, item.state]),
        );
        states.forEach((state, processId) => setProcessState(processId, state));
      } catch (error) {
        console.error("프로세스 상태 메시지를 해석하지 못했습니다.", error);
      }
    });
    socket.addEventListener("close", () => {
      window.setTimeout(connectProcessStatusSocket, 2000);
    });
    socket.addEventListener("error", () => socket.close());
  }

  function connectProcessLogSocket(processId) {
    if (!logDialog?.open || activeLogProcessId !== processId) return;
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(
      `${scheme}//${window.location.host}/ws/process-logs?process_id=${encodeURIComponent(processId)}`,
    );
    logSocket = socket;
    socket.addEventListener("message", (event) => {
      try {
        const update = JSON.parse(event.data);
        if (update.process_id !== activeLogProcessId) return;
        if (Array.isArray(update.events)) {
          logLines = [];
          logOutput.textContent = "";
          update.events.forEach(appendLog);
        } else if (update.event) {
          appendLog(update.event);
        }
      } catch (error) {
        console.error("프로세스 로그 메시지를 해석하지 못했습니다.", error);
      }
    });
    socket.addEventListener("close", () => {
      if (logSocket === socket) logSocket = null;
      if (logDialog?.open && activeLogProcessId === processId) {
        window.setTimeout(() => connectProcessLogSocket(processId), 2000);
      }
    });
    socket.addEventListener("error", () => socket.close());
  }

  function showLogDialog(process) {
    logDialogTitle.textContent = "Logs";
    logProcessName.textContent = process.name;
    logLines = [];
    logDialog?.showModal();
    activeLogProcessId = process.name;
    connectProcessLogSocket(process.name);
  }

  async function deleteProcess(process) {
    const response = await fetch(
      `/api/processes?process_id=${encodeURIComponent(process.name)}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `삭제에 실패했습니다. (${response.status})`);
    }
    await refreshProcesses();
  }

  async function duplicateProcess(process, requestedProcessId) {
    const processId = requestedProcessId.trim();
    if (!processId) {
      throw new Error("복제할 Process ID를 입력해 주세요.");
    }

    const listResponse = await fetch("/api/processes");
    if (!listResponse.ok) {
      throw new Error(`프로세스 목록을 불러오지 못했습니다. (${listResponse.status})`);
    }
    const savedProcesses = await listResponse.json();
    const processIds = new Set(
      savedProcesses.map((savedProcess) => savedProcess.process_id),
    );
    if (processIds.has(processId)) {
      throw new Error(`이미 사용 중인 Process ID입니다: ${processId}`);
    }

    const payload = { ...process.source, process_id: processId };
    if (payload.gpu_id !== undefined) {
      payload.gpuid = payload.gpu_id;
      delete payload.gpu_id;
    }
    const response = await fetch("/api/processes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `복제에 실패했습니다. (${response.status})`);
    }
    await refreshProcesses();
  }

  async function startProcess(process) {
    const response = await fetch(
      `/api/processes/start?process_id=${encodeURIComponent(process.name)}`,
      { method: "POST" },
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `시작에 실패했습니다. (${response.status})`);
    }
    const result = await response.json();
    setProcessState(result.process_id, result.state);
  }

  async function stopProcess(process) {
    const response = await fetch(
      `/api/processes/stop?process_id=${encodeURIComponent(process.name)}`,
      { method: "POST" },
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `정지에 실패했습니다. (${response.status})`);
    }
    const result = await response.json();
    setProcessState(result.process_id, result.state);
  }

  function showActionDialog(process, action) {
    const labels = {
      start: { title: "프로세스 시작", message: "시작하시겠습니까?", button: "시작" },
      stop: { title: "프로세스 정지", message: "정지하시겠습니까?", button: "정지" },
      delete: { title: "프로세스 삭제", message: "삭제하시겠습니까?", button: "삭제" },
    };
    const label = labels[action];
    pendingProcessAction = { process, action };
    actionDialogTitle.textContent = label.title;
    actionProcessName.textContent = process.name;
    actionConfirmMessage.textContent = label.message;
    confirmActionButton.textContent = label.button;
    confirmActionButton.classList.toggle("delete-confirm-button", action === "delete");
    actionProcessError.textContent = "";
    confirmActionButton.disabled = false;
    actionDialog.showModal();
  }

  function showDuplicateDialog(process) {
    pendingDuplicateProcess = process;
    duplicateSourceName.textContent = process.name;
    duplicateProcessIdInput.value = "";
    duplicateProcessError.textContent = "";
    confirmDuplicateButton.disabled = false;
    duplicateDialog.showModal();
    duplicateProcessIdInput.focus();
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (saving) return;
    formError.textContent = "";
    const editing = nameInput.readOnly;
    const process = Object.fromEntries(new FormData(form));
    for (const name of [
      "auto_start",
      "metadata_enabled",
      "inference_enabled",
      "postprocess_enabled",
    ]) {
      process[name] = form.elements.namedItem(name).checked;
    }
    if (process.pipe_type === "bypass") {
      process.metadata_enabled = false;
      process.inference_enabled = false;
      process.postprocess_enabled = false;
    }
    for (const name of ["gpuid", "fps", "inference_interval"]) {
      process[name] = process[name] ? Number(process[name]) : null;
    }
    const processId = process.name;
    process.process_id = processId;
    delete process.name;
    saving = true;
    submitButton.disabled = true;
    openButton.disabled = true;
    try {
      const url = editing
        ? `/api/processes?process_id=${encodeURIComponent(processId)}`
        : "/api/processes";
      const response = await fetch(url, {
        method: editing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(process),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const detail = Array.isArray(body.detail)
          ? body.detail.map((item) => `${item.loc.join(".")}: ${item.msg}`).join("\n")
          : body.detail;
        throw new Error(detail || `저장에 실패했습니다. (${response.status})`);
      }
      await response.json();
      dialog.close();
      await refreshProcesses();
    } catch (error) {
      formError.textContent = error.message;
    } finally {
      saving = false;
      submitButton.disabled = false;
      openButton.disabled = false;
    }
  });

  openButton?.addEventListener("click", showAddDialog);
  closeButtons.forEach((button) => {
    button.addEventListener("click", () => dialog?.close());
  });

  const processList = document.querySelector("#process-list");
  let draggedCard = null;
  let orderBeforeDrag = [];

  function clearProcessDragState() {
    draggedCard?.classList.remove("is-dragging");
    processList?.querySelectorAll(".is-drop-target").forEach((card) => {
      card.classList.remove("is-drop-target");
    });
    draggedCard = null;
    orderBeforeDrag = [];
  }

  processList?.addEventListener("dragstart", (event) => {
    const handle = event.target.closest(".move-button");
    if (!handle) {
      event.preventDefault();
      return;
    }

    draggedCard = handle.closest(".process-card");
    if (!draggedCard) return;
    orderBeforeDrag = [...processList.querySelectorAll(".process-card")].map(
      (card) => card.dataset.processId,
    );
    draggedCard.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", draggedCard.dataset.processId);
  });

  processList?.addEventListener("dragover", (event) => {
    if (!draggedCard) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    const target = event.target.closest(".process-card");
    if (!target || target === draggedCard) return;

    processList.querySelectorAll(".is-drop-target").forEach((card) => {
      card.classList.remove("is-drop-target");
    });
    target.classList.add("is-drop-target");

    const bounds = target.getBoundingClientRect();
    const insertAfter = event.clientX > bounds.left + bounds.width / 2;
    const reference = insertAfter ? target.nextElementSibling : target;
    if (reference !== draggedCard) {
      processList.insertBefore(draggedCard, reference);
    }
  });

  processList?.addEventListener("drop", async (event) => {
    if (!draggedCard) return;
    event.preventDefault();
    const processIds = [...processList.querySelectorAll(".process-card")].map(
      (card) => card.dataset.processId,
    );
    const orderChanged = processIds.some(
      (processId, index) => processId !== orderBeforeDrag[index],
    );
    clearProcessDragState();
    if (!orderChanged) return;

    try {
      const response = await fetch("/api/processes/order", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ process_ids: processIds }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Could not save process order (${response.status}).`);
      }
      await refreshProcesses();
    } catch (error) {
      await refreshProcesses();
      window.alert(error.message);
    }
  });

  processList?.addEventListener("dragend", clearProcessDragState);

  document
    .querySelector("#process-list")
    ?.addEventListener("click", async (event) => {
      const moduleBadge = event.target.closest(".stage-icon[data-module-stage]");
      if (moduleBadge && !moduleBadge.disabled) {
        try {
          const query = new URLSearchParams({
            process_id: moduleBadge.dataset.processId,
            stage: moduleBadge.dataset.moduleStage,
          });
          const response = await fetch(`/api/processes/open-module?${query}`, {
            method: "POST",
          });
          if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            throw new Error(body.detail || `Could not open module (${response.status}).`);
          }
        } catch (error) {
          window.alert(error.message);
        }
        return;
      }

      const startButton = event.target.closest(".start-button");
      if (startButton) {
        showActionDialog(
          displayedProcesses[Number(startButton.dataset.processIndex)],
          "start",
        );
        return;
      }

      const stopButton = event.target.closest(".danger-button");
      if (stopButton) {
        showActionDialog(
          displayedProcesses[Number(stopButton.dataset.processIndex)],
          "stop",
        );
        return;
      }

      const moreButton = event.target.closest(".more-button");
      if (moreButton) {
        const menu = moreButton.parentElement.querySelector(
          ".process-context-menu",
        );
        const willOpen = menu.hidden;
        closeProcessMenus(menu);
        menu.hidden = !willOpen;
        moreButton.setAttribute("aria-expanded", String(willOpen));
        return;
      }

      const editButton = event.target.closest(".context-edit-button");
      if (editButton) {
        if (saving) return;
        closeProcessMenus();
        showEditDialog(
          displayedProcesses[Number(editButton.dataset.processIndex)],
        );
        return;
      }

      const logButton = event.target.closest(".context-log-button");
      if (logButton) {
        const process = displayedProcesses[Number(logButton.dataset.processIndex)];
        closeProcessMenus();
        showLogDialog(process);
        return;
      }

      const deleteButton = event.target.closest(".context-delete-button");
      if (deleteButton) {
        const process =
          displayedProcesses[Number(deleteButton.dataset.processIndex)];
        closeProcessMenus();
        showActionDialog(process, "delete");
        return;
      }

      const copyButton = event.target.closest(".context-copy-button");
      if (copyButton) {
        const process =
          displayedProcesses[Number(copyButton.dataset.processIndex)];
        closeProcessMenus();
        showDuplicateDialog(process);
      }
    });

  confirmActionButton?.addEventListener("click", async () => {
    if (!pendingProcessAction || confirmActionButton.disabled) return;
    confirmActionButton.disabled = true;
    actionProcessError.textContent = "";
    try {
      if (pendingProcessAction.action === "start") {
        await startProcess(pendingProcessAction.process);
      } else if (pendingProcessAction.action === "stop") {
        await stopProcess(pendingProcessAction.process);
      } else if (pendingProcessAction.action === "delete") {
        await deleteProcess(pendingProcessAction.process);
      }
      actionDialog.close();
    } catch (error) {
      actionProcessError.textContent = error.message;
      confirmActionButton.disabled = false;
    }
  });

  cancelActionButton?.addEventListener("click", () => actionDialog.close());
  confirmDuplicateButton?.addEventListener("click", async () => {
    if (!pendingDuplicateProcess || confirmDuplicateButton.disabled) return;
    confirmDuplicateButton.disabled = true;
    duplicateProcessError.textContent = "";
    try {
      await duplicateProcess(
        pendingDuplicateProcess,
        duplicateProcessIdInput.value,
      );
      duplicateDialog.close();
    } catch (error) {
      duplicateProcessError.textContent = error.message;
      confirmDuplicateButton.disabled = false;
    }
  });
  cancelDuplicateButton?.addEventListener("click", () => duplicateDialog.close());
  duplicateDialog?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      confirmDuplicateButton.click();
    }
  });
  duplicateDialog?.addEventListener("close", () => {
    pendingDuplicateProcess = null;
    duplicateProcessError.textContent = "";
  });
  closeLogButton?.addEventListener("click", () => logDialog?.close());
  logDialog?.addEventListener("close", closeLogDialog);
  actionDialog?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      confirmActionButton.click();
    } else if (event.key === "Escape") {
      event.preventDefault();
      actionDialog.close();
    }
  });
  actionDialog?.addEventListener("close", () => {
    pendingProcessAction = null;
    actionProcessError.textContent = "";
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".process-menu-container")) {
      closeProcessMenus();
    }
  });

  async function refreshProcesses() {
    try {
      const response = await fetch("/api/processes");
      if (!response.ok) {
        throw new Error(`process API failed: ${response.status}`);
      }
      const loadedProcesses = await response.json();
      loadedProcesses.forEach((process) => {
        const statistics = latestStatistics.get(process.process_id);
        if (statistics) process.statistics = statistics;
      });
      processes.splice(
        0,
        processes.length,
        ...(Array.isArray(loadedProcesses) ? loadedProcesses : []),
      );
      renderProcesses(processes);
    } catch (error) {
      console.error("프로세스 목록을 불러오지 못했습니다.", error);
      renderProcesses([]);
    }
  }

  refreshProcesses();
  connectStatisticsSocket();
  connectProcessStatusSocket();
});
