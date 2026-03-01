const STORAGE_KEY = "padel-payment-tracker-v1";
const SESSION_COST = 48;
const PLAYERS_PER_SESSION = 4;
const SHARE_PER_PLAYER = SESSION_COST / PLAYERS_PER_SESSION;

const moneyFormatter = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
});

function createId(prefix) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function money(value) {
  return moneyFormatter.format(Number(value) || 0);
}

function prettyDate(value) {
  if (!value) {
    return "Unknown";
  }
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function makeDefaultState() {
  return {
    meName: "You",
    players: [
      { id: createId("player"), name: "Player A" },
      { id: createId("player"), name: "Player B" },
      { id: createId("player"), name: "Player C" },
    ],
    sessions: [],
    payments: [],
  };
}

function normalizeState(raw) {
  const fallback = makeDefaultState();
  if (!raw || typeof raw !== "object") {
    return fallback;
  }

  const players = Array.isArray(raw.players)
    ? raw.players
        .map((item) => ({
          id: typeof item?.id === "string" ? item.id : createId("player"),
          name:
            typeof item?.name === "string" && item.name.trim()
              ? item.name.trim().slice(0, 50)
              : "Unnamed Player",
        }))
        .filter((item, index, arr) => arr.findIndex((row) => row.id === item.id) === index)
    : [];

  const playerSet = new Set(players.map((item) => item.id));

  const sessions = Array.isArray(raw.sessions)
    ? raw.sessions
        .map((item) => {
          let playerIds = Array.isArray(item?.playerIds)
            ? item.playerIds.filter((value, index, arr) => (value === "me" || playerSet.has(value)) && arr.indexOf(value) === index)
            : [];

          const isLegacy = item?.v !== 2;
          if (isLegacy && !playerIds.includes("me")) {
            playerIds = ["me", ...playerIds];
          }

          const payer = typeof item?.payer === "string" && (item.payer === "me" || playerSet.has(item.payer)) ? item.payer : "me";
          const date = typeof item?.date === "string" && item.date ? item.date : todayIso();
          const note = typeof item?.note === "string" ? item.note.slice(0, 120) : "";

          return {
            id: typeof item?.id === "string" ? item.id : createId("session"),
            v: 2,
            date,
            payer,
            playerIds,
            note,
          };
        })
        .filter((item) => item.playerIds.length > 0)
    : [];

  const payments = Array.isArray(raw.payments)
    ? raw.payments
        .map((item) => {
          const playerId = typeof item?.playerId === "string" ? item.playerId : "";
          const amount = Number(item?.amount);
          if (!playerSet.has(playerId) || !Number.isFinite(amount) || amount <= 0) {
            return null;
          }
          return {
            id: typeof item?.id === "string" ? item.id : createId("payment"),
            date: typeof item?.date === "string" && item.date ? item.date : todayIso(),
            playerId,
            direction: item?.direction === "from_me" ? "from_me" : "to_me",
            amount: Math.round(amount * 100) / 100,
            note: typeof item?.note === "string" ? item.note.slice(0, 120) : "",
          };
        })
        .filter(Boolean)
    : [];

  if (!players.length) {
    return fallback;
  }

  return {
    meName: typeof raw.meName === "string" && raw.meName.trim() ? raw.meName.trim().slice(0, 50) : "You",
    players,
    sessions,
    payments,
  };
}

function loadState() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return makeDefaultState();
    }
    return normalizeState(JSON.parse(raw));
  } catch {
    return makeDefaultState();
  }
}

function saveState() {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function getPlayerName(playerId) {
  const player = state.players.find((item) => item.id === playerId);
  return player ? player.name : "Unknown Player";
}

function getPayerName(payerId) {
  if (payerId === "me") {
    return state.meName;
  }
  return getPlayerName(payerId);
}

function isPlayerReferenced(playerId) {
  const inSessions = state.sessions.some((item) => item.payer === playerId || item.playerIds.includes(playerId));
  const inPayments = state.payments.some((item) => item.playerId === playerId);
  return inSessions || inPayments;
}

function setFeedback(elementId, message, isError = false) {
  const el = document.getElementById(elementId);
  if (!el) {
    return;
  }
  el.textContent = message;
  el.classList.toggle("error", Boolean(message) && isError);
}

function renderPlayers() {
  const meNameInput = document.getElementById("meNameInput");
  meNameInput.value = state.meName;

  const playersList = document.getElementById("playersList");
  playersList.innerHTML = "";

  state.players.forEach((player) => {
    const row = document.createElement("div");
    row.className = "player-row";

    const input = document.createElement("input");
    input.type = "text";
    input.value = player.name;
    input.maxLength = 50;
    input.addEventListener("change", () => {
      const value = input.value.trim();
      if (!value) {
        input.value = player.name;
        return;
      }
      player.name = value;
      saveState();
      renderAll();
    });
    row.appendChild(input);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "subtle";
    removeBtn.textContent = "Remove";
    const referenced = isPlayerReferenced(player.id);
    removeBtn.disabled = referenced;
    removeBtn.title = referenced ? "Delete related sessions/payments first." : "Remove player";
    removeBtn.addEventListener("click", () => {
      state.players = state.players.filter((item) => item.id !== player.id);
      saveState();
      renderAll();
      setFeedback("playerFeedback", `${player.name} removed.`);
    });
    row.appendChild(removeBtn);

    playersList.appendChild(row);
  });
}

function renderSessionForm() {
  const dateInput = document.getElementById("sessionDate");
  dateInput.value = todayIso();

  const payerSelect = document.getElementById("sessionPayer");
  payerSelect.innerHTML = "";

  const meOpt = document.createElement("option");
  meOpt.value = "me";
  meOpt.textContent = `${state.meName} (me)`;
  payerSelect.appendChild(meOpt);

  state.players.forEach((player) => {
    const opt = document.createElement("option");
    opt.value = player.id;
    opt.textContent = player.name;
    payerSelect.appendChild(opt);
  });
  payerSelect.value = "me";

  const picker = document.getElementById("sessionPlayersPicker");
  picker.innerHTML = "";

  const meLabel = document.createElement("label");
  meLabel.className = "pill-option";
  const meCheckbox = document.createElement("input");
  meCheckbox.type = "checkbox";
  meCheckbox.name = "session-player";
  meCheckbox.value = "me";
  meCheckbox.checked = false;
  meLabel.appendChild(meCheckbox);
  meLabel.appendChild(document.createTextNode(`${state.meName} (me)`));
  picker.appendChild(meLabel);

  state.players.forEach((player) => {
    const label = document.createElement("label");
    label.className = "pill-option";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.name = "session-player";
    checkbox.value = player.id;
    checkbox.checked = false;

    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(player.name));
    picker.appendChild(label);
  });

  setFeedback("sessionFeedback", "");
}

function renderPaymentForm() {
  const dateInput = document.getElementById("paymentDate");
  dateInput.value = todayIso();

  const playerSelect = document.getElementById("paymentPlayer");
  playerSelect.innerHTML = "";
  state.players.forEach((player) => {
    const opt = document.createElement("option");
    opt.value = player.id;
    opt.textContent = player.name;
    playerSelect.appendChild(opt);
  });

  document.getElementById("paymentDirection").value = "to_me";
  document.getElementById("paymentAmount").value = "";
  document.getElementById("paymentNote").value = "";
  setFeedback("paymentFeedback", "");
}

function computeBalances() {
  const stats = new Map(
    state.players.map((player) => [
      player.id,
      {
        playerId: player.id,
        name: player.name,
        sessionsPlayed: 0,
        charged: 0,
        credit: 0,
        paymentsNet: 0,
        balance: 0,
      },
    ]),
  );

  let sessionsPaidByMe = 0;

  state.sessions.forEach((session) => {
    const includesMe = session.playerIds.includes("me");

    session.playerIds.forEach((playerId) => {
      if (playerId === "me") {
        return;
      }
      const row = stats.get(playerId);
      if (row) {
        row.sessionsPlayed += 1;
      }
    });

    if (session.payer === "me") {
      sessionsPaidByMe += 1;
      session.playerIds.forEach((playerId) => {
        if (playerId === "me") {
          return;
        }
        const row = stats.get(playerId);
        if (row) {
          row.charged += SHARE_PER_PLAYER;
        }
      });
      return;
    }

    const payerRow = stats.get(session.payer);
    if (payerRow && includesMe) {
      payerRow.credit += SHARE_PER_PLAYER;
    }
  });

  state.payments.forEach((payment) => {
    const row = stats.get(payment.playerId);
    if (!row) {
      return;
    }
    if (payment.direction === "from_me") {
      row.paymentsNet -= payment.amount;
    } else {
      row.paymentsNet += payment.amount;
    }
  });

  const rows = Array.from(stats.values()).map((row) => {
    const balance = row.charged - row.credit - row.paymentsNet;
    return {
      ...row,
      balance,
    };
  });

  const outstandingToMe = rows.reduce((sum, row) => sum + Math.max(row.balance, 0), 0);
  const iOwePlayers = rows.reduce((sum, row) => sum + Math.max(-row.balance, 0), 0);

  return {
    rows: rows.sort((a, b) => b.balance - a.balance),
    sessionsPaidByMe,
    outstandingToMe,
    iOwePlayers,
  };
}

function makeEmptyRow(colspan, text) {
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = colspan;
  td.className = "empty-row";
  td.textContent = text;
  tr.appendChild(td);
  return tr;
}

function renderBalanceTable(summary) {
  const table = document.getElementById("balancesTable");
  table.innerHTML = "";

  if (!summary.rows.length) {
    table.appendChild(makeEmptyRow(6, "Add players to start tracking."));
    return;
  }

  summary.rows.forEach((row) => {
    const tr = document.createElement("tr");

    const nameCell = document.createElement("td");
    nameCell.textContent = row.name;
    tr.appendChild(nameCell);

    const playedCell = document.createElement("td");
    playedCell.textContent = String(row.sessionsPlayed);
    tr.appendChild(playedCell);

    const chargedCell = document.createElement("td");
    chargedCell.textContent = money(row.charged);
    tr.appendChild(chargedCell);

    const creditCell = document.createElement("td");
    creditCell.textContent = money(row.credit);
    tr.appendChild(creditCell);

    const paymentsCell = document.createElement("td");
    paymentsCell.textContent =
      row.paymentsNet > 0 ? `+${money(row.paymentsNet)}` : row.paymentsNet < 0 ? `-${money(Math.abs(row.paymentsNet))}` : money(0);
    tr.appendChild(paymentsCell);

    const balanceCell = document.createElement("td");
    const tag = document.createElement("span");
    tag.className = "tag";
    if (row.balance > 0.005) {
      tag.classList.add("positive");
      tag.textContent = `Owes you ${money(row.balance)}`;
    } else if (row.balance < -0.005) {
      tag.classList.add("negative");
      tag.textContent = `You owe ${money(Math.abs(row.balance))}`;
    } else {
      tag.classList.add("zero");
      tag.textContent = "Settled";
    }
    balanceCell.appendChild(tag);
    tr.appendChild(balanceCell);

    table.appendChild(tr);
  });
}

function renderSessionTable() {
  const table = document.getElementById("sessionsTable");
  table.innerHTML = "";

  if (!state.sessions.length) {
    table.appendChild(makeEmptyRow(5, "No sessions yet."));
    return;
  }

  state.sessions.forEach((session) => {
    const tr = document.createElement("tr");

    const dateCell = document.createElement("td");
    dateCell.textContent = prettyDate(session.date);
    tr.appendChild(dateCell);

    const playersCell = document.createElement("td");
    const participants = session.playerIds
      .map((playerId) => (playerId === "me" ? state.meName : getPlayerName(playerId)))
      .join(", ");
    playersCell.textContent = participants;
    tr.appendChild(playersCell);

    const payerCell = document.createElement("td");
    payerCell.textContent = getPayerName(session.payer);
    tr.appendChild(payerCell);

    const noteCell = document.createElement("td");
    noteCell.textContent = session.note || " ";
    tr.appendChild(noteCell);

    const actionCell = document.createElement("td");
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "subtle";
    removeBtn.dataset.sessionId = session.id;
    removeBtn.textContent = "Delete";
    actionCell.appendChild(removeBtn);
    tr.appendChild(actionCell);

    table.appendChild(tr);
  });
}

function renderPaymentTable() {
  const table = document.getElementById("paymentsTable");
  table.innerHTML = "";

  if (!state.payments.length) {
    table.appendChild(makeEmptyRow(5, "No payments yet."));
    return;
  }

  state.payments.forEach((payment) => {
    const tr = document.createElement("tr");

    const dateCell = document.createElement("td");
    dateCell.textContent = prettyDate(payment.date);
    tr.appendChild(dateCell);

    const flowCell = document.createElement("td");
    const playerName = getPlayerName(payment.playerId);
    flowCell.textContent =
      payment.direction === "from_me" ? `${state.meName} paid ${playerName}` : `${playerName} paid ${state.meName}`;
    tr.appendChild(flowCell);

    const amountCell = document.createElement("td");
    amountCell.textContent = money(payment.amount);
    tr.appendChild(amountCell);

    const noteCell = document.createElement("td");
    noteCell.textContent = payment.note || " ";
    tr.appendChild(noteCell);

    const actionCell = document.createElement("td");
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "subtle";
    removeBtn.dataset.paymentId = payment.id;
    removeBtn.textContent = "Delete";
    actionCell.appendChild(removeBtn);
    tr.appendChild(actionCell);

    table.appendChild(tr);
  });
}

function renderSummary(summary) {
  document.getElementById("sessionsCount").textContent = String(state.sessions.length);
  document.getElementById("yourSpend").textContent = money(summary.sessionsPaidByMe * SESSION_COST);
  document.getElementById("owedToYou").textContent = money(summary.outstandingToMe);
  document.getElementById("youOwe").textContent = money(summary.iOwePlayers);
}

function renderAll() {
  renderPlayers();
  renderSessionForm();
  renderPaymentForm();
  const summary = computeBalances();
  renderSummary(summary);
  renderBalanceTable(summary);
  renderSessionTable();
  renderPaymentTable();
}

function getSessionSelection() {
  return Array.from(document.querySelectorAll('input[name="session-player"]:checked')).map((item) => item.value);
}

function onAddPlayer() {
  const input = document.getElementById("newPlayerInput");
  const name = input.value.trim();
  if (!name) {
    setFeedback("playerFeedback", "Enter a player name first.", true);
    return;
  }

  state.players.push({ id: createId("player"), name: name.slice(0, 50) });
  saveState();
  input.value = "";
  renderAll();
  setFeedback("playerFeedback", `${name} added.`);
}

function onMeNameChange() {
  const input = document.getElementById("meNameInput");
  const value = input.value.trim();
  state.meName = value || "You";
  saveState();
  renderAll();
}

function onAddSession(event) {
  event.preventDefault();
  setFeedback("sessionFeedback", "");

  if (state.players.length + 1 < PLAYERS_PER_SESSION) {
    setFeedback("sessionFeedback", "Add enough players so 4 participants can be selected.", true);
    return;
  }

  const date = document.getElementById("sessionDate").value || todayIso();
  const payer = document.getElementById("sessionPayer").value || "me";
  const playerIds = getSessionSelection();
  const note = document.getElementById("sessionNote").value.trim().slice(0, 120);

  if (playerIds.length !== PLAYERS_PER_SESSION) {
    setFeedback("sessionFeedback", "Select exactly 4 players for a session.", true);
    return;
  }

  if (payer !== "me" && !playerIds.includes(payer)) {
    setFeedback("sessionFeedback", "If a player paid, they must be part of the selected session.", true);
    return;
  }

  state.sessions.unshift({
    id: createId("session"),
    v: 2,
    date,
    payer,
    playerIds,
    note,
  });
  saveState();
  renderAll();
  setFeedback("sessionFeedback", "Session added.");
}

function onAddPayment(event) {
  event.preventDefault();
  setFeedback("paymentFeedback", "");

  const date = document.getElementById("paymentDate").value || todayIso();
  const playerId = document.getElementById("paymentPlayer").value;
  const direction = document.getElementById("paymentDirection").value === "from_me" ? "from_me" : "to_me";
  const amount = Number(document.getElementById("paymentAmount").value);
  const note = document.getElementById("paymentNote").value.trim().slice(0, 120);

  if (!state.players.some((player) => player.id === playerId)) {
    setFeedback("paymentFeedback", "Select a valid player.", true);
    return;
  }
  if (!Number.isFinite(amount) || amount <= 0) {
    setFeedback("paymentFeedback", "Enter a valid positive amount.", true);
    return;
  }

  state.payments.unshift({
    id: createId("payment"),
    date,
    playerId,
    direction,
    amount: Math.round(amount * 100) / 100,
    note,
  });
  saveState();
  renderAll();
  setFeedback("paymentFeedback", "Payment recorded.");
}

function onQuickAmount(amount) {
  document.getElementById("paymentAmount").value = String(amount);
}

function onDeleteSession(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement) || !target.dataset.sessionId) {
    return;
  }
  const sessionId = target.dataset.sessionId;
  state.sessions = state.sessions.filter((session) => session.id !== sessionId);
  saveState();
  renderAll();
}

function onDeletePayment(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement) || !target.dataset.paymentId) {
    return;
  }
  const paymentId = target.dataset.paymentId;
  state.payments = state.payments.filter((payment) => payment.id !== paymentId);
  saveState();
  renderAll();
}

function onReset() {
  if (!window.confirm("Reset all padel tracker data? This cannot be undone.")) {
    return;
  }
  state = makeDefaultState();
  saveState();
  renderAll();
  setFeedback("playerFeedback", "Tracker reset.");
}

let state = loadState();

function init() {
  renderAll();
  document.getElementById("addPlayerBtn").addEventListener("click", onAddPlayer);
  document.getElementById("newPlayerInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      onAddPlayer();
    }
  });
  document.getElementById("meNameInput").addEventListener("change", onMeNameChange);
  document.getElementById("sessionForm").addEventListener("submit", onAddSession);
  document.getElementById("paymentForm").addEventListener("submit", onAddPayment);
  document.getElementById("quick12Btn").addEventListener("click", () => onQuickAmount(12));
  document.getElementById("quick48Btn").addEventListener("click", () => onQuickAmount(48));
  document.getElementById("sessionsTable").addEventListener("click", onDeleteSession);
  document.getElementById("paymentsTable").addEventListener("click", onDeletePayment);
  document.getElementById("resetBtn").addEventListener("click", onReset);
}

init();
