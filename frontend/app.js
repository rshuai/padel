const state = {
  entities: [],
};

function getApiKey() {
  return document.getElementById("apiKey").value.trim();
}

function getEngagementId() {
  return document.getElementById("engagementId").value.trim();
}

function setEngagementId(value) {
  document.getElementById("engagementId").value = value;
}

function requireEngagement() {
  const id = getEngagementId();
  if (!id) {
    throw new Error("Set or create an engagement ID first.");
  }
  return id;
}

async function api(path, options = {}) {
  const headers = options.headers ? { ...options.headers } : {};
  const apiKey = getApiKey();
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }

  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, { ...options, headers });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : JSON.stringify(payload);
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return payload;
}

function setPre(id, value) {
  document.getElementById(id).textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function renderEntities(rows) {
  state.entities = rows;
  const tbody = document.getElementById("entitiesTable");
  tbody.innerHTML = "";

  rows.forEach((entity) => {
    const tr = document.createElement("tr");
    tr.dataset.id = entity.id;
    tr.innerHTML = `
      <td>${entity.id}</td>
      <td>${entity.name}</td>
      <td><input class="entity-currency" value="${entity.functional_currency || ""}" maxlength="3" /></td>
      <td><input class="entity-ownership" type="number" min="0" max="1" step="0.0001" value="${entity.ownership_pct || 1}" /></td>
      <td>
        <select class="entity-nci">
          <option value="false" ${entity.has_nci ? "" : "selected"}>No</option>
          <option value="true" ${entity.has_nci ? "selected" : ""}>Yes</option>
        </select>
      </td>
      <td>
        <select class="entity-scope">
          <option value="true" ${entity.include_in_scope ? "selected" : ""}>Yes</option>
          <option value="false" ${entity.include_in_scope ? "" : "selected"}>No</option>
        </select>
      </td>
      <td><input class="entity-ic" value="${entity.intercompany_identifier || ""}" /></td>
    `;
    tbody.appendChild(tr);
  });

  const uploadEntity = document.getElementById("uploadEntity");
  const overrideEntity = document.getElementById("overrideEntity");
  uploadEntity.innerHTML = "";
  overrideEntity.innerHTML = "";

  rows.forEach((entity) => {
    const optA = document.createElement("option");
    optA.value = entity.id;
    optA.textContent = `${entity.name} (${entity.functional_currency || "N/A"})`;
    uploadEntity.appendChild(optA);

    const optB = document.createElement("option");
    optB.value = entity.id;
    optB.textContent = entity.name;
    overrideEntity.appendChild(optB);
  });
}

function collectClarificationEntities() {
  const rows = [...document.querySelectorAll("#entitiesTable tr")];
  return rows.map((row) => {
    const entityId = row.dataset.id;
    return {
      entity_id: entityId,
      functional_currency: row.querySelector(".entity-currency").value.trim().toUpperCase(),
      ownership_pct: Number(row.querySelector(".entity-ownership").value),
      has_nci: row.querySelector(".entity-nci").value === "true",
      include_in_scope: row.querySelector(".entity-scope").value === "true",
      intercompany_identifier: row.querySelector(".entity-ic").value.trim() || null,
    };
  });
}

async function refreshEntities() {
  const engagementId = requireEngagement();
  const rows = await api(`/api/engagements/${engagementId}/entities`);
  renderEntities(rows);
}

async function refreshFxList() {
  const engagementId = requireEngagement();
  const rows = await api(`/api/engagements/${engagementId}/fx`);

  const tbody = document.getElementById("fxTable");
  tbody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.entity_name}</td>
      <td>${row.base_currency}/${row.quote_currency}</td>
      <td>${row.rate_type}</td>
      <td>${row.rate_date}</td>
      <td>${row.rate}</td>
      <td>${row.source}</td>
      <td>${row.methodology}</td>
      <td>${row.missing_days}</td>
      <td>${row.is_override ? "Y" : "N"}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function refreshOutputs() {
  const engagementId = requireEngagement();
  const rows = await api(`/api/engagements/${engagementId}/artifacts`);

  const list = document.getElementById("outputsList");
  list.innerHTML = "";
  rows.forEach((row) => {
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.href = `/api/artifacts/${row.id}/download`;
    link.textContent = `${row.artifact_type} (${row.id})`;
    link.target = "_blank";
    li.appendChild(link);
    list.appendChild(li);
  });
}

async function refreshExceptions() {
  const engagementId = requireEngagement();
  const rows = await api(`/api/engagements/${engagementId}/exceptions`);

  const tbody = document.getElementById("exceptionsTable");
  tbody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.severity}</td>
      <td>${row.blocking ? "Yes" : "No"}</td>
      <td>${row.category}</td>
      <td>${row.message}</td>
      <td>${row.entity_id || ""}</td>
      <td>${row.account_code || ""}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function onCreateEngagement() {
  const name = document.getElementById("engagementName").value.trim();
  if (!name) {
    throw new Error("Engagement name is required.");
  }
  const result = await api("/api/engagements", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  setEngagementId(result.id);
  setPre("engagementResult", result);
}

async function onAddEntity() {
  const engagementId = requireEngagement();
  const body = {
    name: document.getElementById("entityName").value.trim(),
    functional_currency: document.getElementById("entityCurrency").value.trim().toUpperCase(),
    ownership_pct: Number(document.getElementById("entityOwnership").value),
    has_nci: document.getElementById("entityHasNci").value === "true",
    include_in_scope: document.getElementById("entityScope").value === "true",
    intercompany_identifier: document.getElementById("entityIcIdentifier").value.trim() || null,
  };

  if (!body.name || !body.functional_currency) {
    throw new Error("Entity name and functional currency are required.");
  }

  await api(`/api/engagements/${engagementId}/entities`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  await refreshEntities();
}

async function onUpload() {
  const engagementId = requireEngagement();
  const fileType = document.getElementById("uploadType").value;
  const entityId = document.getElementById("uploadEntity").value;
  const file = document.getElementById("uploadFile").files[0];
  if (!file) {
    throw new Error("Select a file to upload.");
  }

  const params = new URLSearchParams({ file_type: fileType });
  if (fileType === "ENTITY_TB" || fileType === "ENTITY_GL") {
    if (!entityId) {
      throw new Error("Entity is required for TB/GL uploads.");
    }
    params.append("entity_id", entityId);
  }

  const form = new FormData();
  form.append("file", file);
  const result = await api(`/api/engagements/${engagementId}/uploads?${params.toString()}`, {
    method: "POST",
    body: form,
  });
  setPre("uploadResult", result);
}

async function onSubmitClarification() {
  const engagementId = requireEngagement();
  const entities = collectClarificationEntities();
  if (!entities.length) {
    throw new Error("Add at least one entity before clarification.");
  }

  const body = {
    reporting_period_start: document.getElementById("periodStart").value,
    reporting_period_end: document.getElementById("periodEnd").value,
    presentation_currency: document.getElementById("presentationCurrency").value.trim().toUpperCase(),
    average_method: document.getElementById("averageMethod").value,
    intercompany_method: document.getElementById("intercompanyMethod").value,
    entities,
  };

  if (!body.reporting_period_start || !body.reporting_period_end) {
    throw new Error("Reporting period start and end are required.");
  }

  const result = await api(`/api/engagements/${engagementId}/clarification`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  setPre("clarificationResult", result);
}

async function onCheckClarification() {
  const engagementId = requireEngagement();
  const result = await api(`/api/engagements/${engagementId}/clarification/status`);
  setPre("clarificationResult", result);
}

async function onRetrieveFx() {
  const engagementId = requireEngagement();
  await api(`/api/engagements/${engagementId}/fx/retrieve`, { method: "POST" });
  await refreshFxList();
}

async function onSubmitOverride() {
  const engagementId = requireEngagement();
  const body = {
    entity_id: document.getElementById("overrideEntity").value,
    rate_type: document.getElementById("overrideType").value,
    rate_date: document.getElementById("overrideDate").value,
    rate: Number(document.getElementById("overrideRate").value),
    note: document.getElementById("overrideNote").value.trim() || null,
  };

  if (!body.entity_id || !body.rate_date || !body.rate) {
    throw new Error("Entity, date, and rate are required for FX override.");
  }

  await api(`/api/engagements/${engagementId}/fx/override`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  await refreshFxList();
}

async function onRunProcess() {
  const engagementId = requireEngagement();
  const result = await api(`/api/engagements/${engagementId}/process`, { method: "POST" });
  setPre("processResult", result);
  await refreshOutputs();
  await refreshExceptions();
}

function bind(id, fn, target = "click") {
  const el = document.getElementById(id);
  el.addEventListener(target, async () => {
    try {
      await fn();
    } catch (err) {
      alert(err.message || String(err));
    }
  });
}

bind("createEngagementBtn", onCreateEngagement);
bind("addEntityBtn", onAddEntity);
bind("refreshEntitiesBtn", refreshEntities);
bind("uploadBtn", onUpload);
bind("submitClarificationBtn", onSubmitClarification);
bind("checkClarificationBtn", onCheckClarification);
bind("retrieveFxBtn", onRetrieveFx);
bind("submitOverrideBtn", onSubmitOverride);
bind("runProcessBtn", onRunProcess);
bind("refreshOutputsBtn", refreshOutputs);
bind("refreshExceptionsBtn", refreshExceptions);

window.addEventListener("load", () => {
  document.getElementById("uploadType").addEventListener("change", (event) => {
    const value = event.target.value;
    const entitySelect = document.getElementById("uploadEntity");
    const required = value === "ENTITY_TB" || value === "ENTITY_GL";
    entitySelect.disabled = !required;
  });
});
