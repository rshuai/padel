const STORAGE_KEY = "simple_writer_document_v1";
const AUTOSAVE_DELAY_MS = 450;
const READING_SPEED_WPM = 225;

const editor = document.getElementById("editor");
const docTitle = document.getElementById("docTitle");
const saveStatus = document.getElementById("saveStatus");
const wordCountEl = document.getElementById("wordCount");
const charCountEl = document.getElementById("charCount");
const readingTimeEl = document.getElementById("readingTime");
const blockFormat = document.getElementById("blockFormat");

const importFileInput = document.getElementById("importFile");
const commandButtons = [...document.querySelectorAll("[data-cmd]")];

let autosaveTimer = null;

function getDefaultDocument() {
  return {
    title: "Untitled document",
    content: "",
    savedAt: null,
  };
}

function setStatus(message, mode = "ready") {
  saveStatus.textContent = message;
  saveStatus.classList.toggle("saving", mode === "saving");
}

function formatClockTime(dateValue) {
  if (!dateValue) {
    return "";
  }
  return new Date(dateValue).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function saveLocalNow() {
  try {
    const payload = {
      title: docTitle.value.trim() || "Untitled document",
      content: editor.innerHTML,
      savedAt: new Date().toISOString(),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    setStatus(`Saved ${formatClockTime(payload.savedAt)}`);
  } catch (error) {
    setStatus("Unable to save locally");
  }
}

function queueAutosave() {
  setStatus("Saving...", "saving");
  if (autosaveTimer) {
    clearTimeout(autosaveTimer);
  }
  autosaveTimer = setTimeout(saveLocalNow, AUTOSAVE_DELAY_MS);
}

function updateStats() {
  const text = editor.innerText.replace(/\u00a0/g, " ").trim();
  const words = text ? text.split(/\s+/).length : 0;
  const characters = editor.innerText.replace(/\u00a0/g, " ").length;
  const minutes = words === 0 ? 0 : Math.max(1, Math.ceil(words / READING_SPEED_WPM));

  wordCountEl.textContent = String(words);
  charCountEl.textContent = String(characters);
  readingTimeEl.textContent = `${minutes} min read`;
}

function toFileSafeName(name) {
  const safe = (name || "untitled-document")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
  return safe || "untitled-document";
}

function triggerDownload(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function plainTextToHtml(text) {
  const blocks = text.replace(/\r\n?/g, "\n").split(/\n\n+/);
  const html = blocks
    .map((block) => {
      const clean = escapeHtml(block).replace(/\n/g, "<br>");
      return `<p>${clean || "<br>"}</p>`;
    })
    .join("");
  return html || "<p></p>";
}

function sanitizeImportedHtml(rawHtml) {
  const parser = new DOMParser();
  const parsed = parser.parseFromString(rawHtml, "text/html");

  parsed.querySelectorAll("script,style,iframe,object,embed,link,meta").forEach((node) => node.remove());
  parsed.querySelectorAll("*").forEach((element) => {
    [...element.attributes].forEach((attribute) => {
      const name = attribute.name.toLowerCase();
      if (name.startsWith("on") || name === "style") {
        element.removeAttribute(attribute.name);
      }
    });
  });

  return parsed.body.innerHTML.trim() || "<p></p>";
}

function runCommand(command, value = null) {
  editor.focus();
  document.execCommand(command, false, value);
  updateStats();
  syncToolbarState();
  queueAutosave();
}

function runFormatBlock(tagName) {
  editor.focus();
  const primary = document.execCommand("formatBlock", false, tagName);
  if (!primary) {
    document.execCommand("formatBlock", false, `<${tagName}>`);
  }
  updateStats();
  syncToolbarState();
  queueAutosave();
}

function clearFormatting() {
  editor.focus();
  document.execCommand("removeFormat", false, null);
  document.execCommand("unlink", false, null);
  updateStats();
  syncToolbarState();
  queueAutosave();
}

function findCurrentBlockTag() {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) {
    return "p";
  }

  let node = selection.anchorNode;
  if (!node) {
    return "p";
  }

  if (node.nodeType === Node.TEXT_NODE) {
    node = node.parentNode;
  }

  while (node && node !== editor) {
    if (node.nodeType === Node.ELEMENT_NODE) {
      const tag = node.tagName.toLowerCase();
      if (["p", "h1", "h2", "blockquote", "pre"].includes(tag)) {
        return tag;
      }
    }
    node = node.parentNode;
  }

  return "p";
}

function syncToolbarState() {
  const activeCommands = [
    "bold",
    "italic",
    "underline",
    "strikeThrough",
    "insertUnorderedList",
    "insertOrderedList",
    "justifyLeft",
    "justifyCenter",
    "justifyRight",
  ];

  activeCommands.forEach((command) => {
    const button = document.querySelector(`[data-cmd=\"${command}\"]`);
    if (!button) {
      return;
    }

    const isActive = Boolean(document.queryCommandState(command));
    button.classList.toggle("is-active", isActive);
  });

  blockFormat.value = findCurrentBlockTag();
}

function loadSavedDocument() {
  const fallback = getDefaultDocument();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      docTitle.value = fallback.title;
      editor.innerHTML = fallback.content;
      setStatus("Ready");
      return;
    }

    const parsed = JSON.parse(raw);
    docTitle.value = parsed.title || fallback.title;
    editor.innerHTML = parsed.content ?? fallback.content;
    setStatus(parsed.savedAt ? `Restored ${formatClockTime(parsed.savedAt)}` : "Restored draft");
  } catch (error) {
    docTitle.value = fallback.title;
    editor.innerHTML = fallback.content;
    setStatus("Ready");
  }
}

function isSelectionInsideEditor() {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) {
    return false;
  }

  const anchor = selection.anchorNode;
  return Boolean(anchor) && (anchor === editor || editor.contains(anchor));
}

function bindCoreEvents() {
  commandButtons.forEach((button) => {
    button.addEventListener("mousedown", (event) => event.preventDefault());
    button.addEventListener("click", () => {
      runCommand(button.dataset.cmd);
    });
  });

  document.querySelector("[data-action=\"clear-format\"]").addEventListener("mousedown", (event) => {
    event.preventDefault();
  });
  document.querySelector("[data-action=\"clear-format\"]").addEventListener("click", clearFormatting);

  blockFormat.addEventListener("change", () => runFormatBlock(blockFormat.value));

  editor.addEventListener("input", () => {
    updateStats();
    queueAutosave();
  });

  editor.addEventListener("keyup", syncToolbarState);
  editor.addEventListener("mouseup", syncToolbarState);

  editor.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveLocalNow();
    }
  });

  docTitle.addEventListener("input", queueAutosave);

  document.addEventListener("selectionchange", () => {
    if (isSelectionInsideEditor()) {
      syncToolbarState();
    }
  });

  document.getElementById("newDocBtn").addEventListener("click", () => {
    const proceed = window.confirm("Start a new document? Your current draft will be replaced.");
    if (!proceed) {
      return;
    }

    const initial = getDefaultDocument();
    docTitle.value = initial.title;
    editor.innerHTML = initial.content;
    updateStats();
    syncToolbarState();
    queueAutosave();
  });

  document.getElementById("openBtn").addEventListener("click", () => {
    importFileInput.click();
  });

  importFileInput.addEventListener("change", async () => {
    const [file] = importFileInput.files;
    if (!file) {
      return;
    }

    const text = await file.text();
    const isHtml = /\.html?$/i.test(file.name) || (file.type || "").includes("html");
    editor.innerHTML = isHtml ? sanitizeImportedHtml(text) : plainTextToHtml(text);

    docTitle.value = file.name.replace(/\.[^.]+$/, "") || "Imported document";
    updateStats();
    syncToolbarState();
    queueAutosave();
    setStatus(`Loaded ${file.name}`);
    importFileInput.value = "";
  });

  document.getElementById("saveTxtBtn").addEventListener("click", () => {
    const baseName = toFileSafeName(docTitle.value);
    triggerDownload(`${baseName}.txt`, editor.innerText, "text/plain;charset=utf-8");
    setStatus("Exported .txt");
  });

  document.getElementById("saveHtmlBtn").addEventListener("click", () => {
    const baseName = toFileSafeName(docTitle.value);
    const html = `<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n<title>${escapeHtml(
      docTitle.value || "Untitled document"
    )}</title>\n</head>\n<body>\n${editor.innerHTML}\n</body>\n</html>`;
    triggerDownload(`${baseName}.html`, html, "text/html;charset=utf-8");
    setStatus("Exported .html");
  });

  document.getElementById("printBtn").addEventListener("click", () => {
    window.print();
    setStatus("Sent to printer");
  });
}

function init() {
  loadSavedDocument();
  bindCoreEvents();
  updateStats();
  syncToolbarState();
}

init();
