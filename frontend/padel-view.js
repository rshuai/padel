const STORAGE_KEY = "padel-payment-tracker-v1";
const SEEDED_DATA_URL = "/padel-data.json";
const SESSION_COST = 48;
const SHARE_PER_PLAYER = 12;

const moneyFormatter = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
});

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

function createId(prefix) {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
}

function normalizeState(raw) {
  if (!raw || typeof raw !== "object") {
    return { meName: "You", players: [], sessions: [], payments: [] };
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
          const date = typeof item?.date === "string" && item.date ? item.date : "";
          const note = typeof item?.note === "string" ? item.note.slice(0, 120) : "";

          return {
            id: typeof item?.id === "string" ? item.id : createId("session"),
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
            date: typeof item?.date === "string" ? item.date : "",
            playerId,
            direction: item?.direction === "from_me" ? "from_me" : "to_me",
            amount: Math.round(amount * 100) / 100,
            note: typeof item?.note === "string" ? item.note.slice(0, 120) : "",
          };
        })
        .filter(Boolean)
    : [];

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
      return normalizeState(null);
    }
    return normalizeState(JSON.parse(raw));
  } catch {
    return normalizeState(null);
  }
}

function hasMeaningfulData(state) {
  return Boolean(state.players.length || state.sessions.length || state.payments.length);
}

async function loadSeededState() {
  try {
    const response = await fetch(SEEDED_DATA_URL, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    const payload = await response.json();
    return normalizeState(payload);
  } catch {
    return null;
  }
}

async function loadStateWithSeed() {
  const localState = loadState();
  if (hasMeaningfulData(localState)) {
    return localState;
  }

  const seededState = await loadSeededState();
  if (seededState && hasMeaningfulData(seededState)) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(seededState));
    } catch {
      // Ignore storage failures and continue with in-memory seeded state.
    }
    return seededState;
  }

  return localState;
}

function getPlayerName(state, playerId) {
  const player = state.players.find((item) => item.id === playerId);
  return player ? player.name : "Unknown Player";
}

function getPayerName(state, payerId) {
  return payerId === "me" ? state.meName : getPlayerName(state, payerId);
}

function applyResponsiveTableLabels() {
  document.querySelectorAll(".table-wrap table").forEach((table) => {
    const labels = Array.from(table.querySelectorAll("thead th")).map((headerCell) => headerCell.textContent.trim());
    table.querySelectorAll("tbody tr").forEach((row) => {
      Array.from(row.children).forEach((cell, index) => {
        if (cell.tagName !== "TD") {
          return;
        }
        if (cell.classList.contains("empty-row")) {
          cell.removeAttribute("data-label");
          return;
        }
        const label = labels[index];
        if (label) {
          cell.dataset.label = label;
        } else {
          cell.removeAttribute("data-label");
        }
      });
    });
  });
}

function computeBalances(state) {
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

  const rows = Array.from(stats.values()).map((row) => ({
    ...row,
    balance: row.charged - row.credit - row.paymentsNet,
  }));

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

function renderPlayers(state, summary) {
  const playersMeta = document.getElementById("playersMeta");
  const playersList = document.getElementById("playersReadList");
  if (!playersMeta || !playersList) {
    return;
  }

  playersList.innerHTML = "";

  if (!state.players.length) {
    playersMeta.textContent = "No players yet.";
    const li = document.createElement("li");
    li.className = "empty-row";
    li.textContent = "No player data found.";
    playersList.appendChild(li);
    return;
  }

  playersMeta.textContent = `${state.players.length} players tracked. You are "${state.meName}".`;

  summary.rows.forEach((row) => {
    const li = document.createElement("li");
    li.textContent = row.name;

    const badge = document.createElement("span");
    badge.className = "tag";

    if (row.balance > 0.005) {
      badge.classList.add("positive");
      badge.textContent = `Owes ${money(row.balance)}`;
    } else if (row.balance < -0.005) {
      badge.classList.add("negative");
      badge.textContent = `Credit ${money(Math.abs(row.balance))}`;
    } else {
      badge.classList.add("zero");
      badge.textContent = "Settled";
    }

    li.appendChild(badge);
    playersList.appendChild(li);
  });
}

function renderSummary(state, summary) {
  document.getElementById("sessionsCount").textContent = String(state.sessions.length);
  document.getElementById("yourSpend").textContent = money(summary.sessionsPaidByMe * SESSION_COST);
  document.getElementById("owedToYou").textContent = money(summary.outstandingToMe);
  document.getElementById("youOwe").textContent = money(summary.iOwePlayers);
}

function renderBalanceTable(summary) {
  const table = document.getElementById("balancesTable");
  table.innerHTML = "";

  if (!summary.rows.length) {
    table.appendChild(makeEmptyRow(6, "No balance data yet."));
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
    balanceCell.className = "balance-cell";
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

function renderSessionTable(state) {
  const table = document.getElementById("sessionsTable");
  table.innerHTML = "";

  if (!state.sessions.length) {
    table.appendChild(makeEmptyRow(4, "No sessions yet."));
    return;
  }

  state.sessions.forEach((session) => {
    const tr = document.createElement("tr");

    const dateCell = document.createElement("td");
    dateCell.textContent = prettyDate(session.date);
    tr.appendChild(dateCell);

    const playersCell = document.createElement("td");
    playersCell.textContent = session.playerIds
      .map((playerId) => (playerId === "me" ? state.meName : getPlayerName(state, playerId)))
      .join(", ");
    tr.appendChild(playersCell);

    const payerCell = document.createElement("td");
    payerCell.textContent = getPayerName(state, session.payer);
    tr.appendChild(payerCell);

    const noteCell = document.createElement("td");
    noteCell.textContent = session.note || " ";
    tr.appendChild(noteCell);

    table.appendChild(tr);
  });
}

function renderPaymentTable(state) {
  const table = document.getElementById("paymentsTable");
  table.innerHTML = "";

  if (!state.payments.length) {
    table.appendChild(makeEmptyRow(4, "No payments yet."));
    return;
  }

  state.payments.forEach((payment) => {
    const tr = document.createElement("tr");

    const dateCell = document.createElement("td");
    dateCell.textContent = prettyDate(payment.date);
    tr.appendChild(dateCell);

    const flowCell = document.createElement("td");
    const playerName = getPlayerName(state, payment.playerId);
    flowCell.textContent =
      payment.direction === "from_me" ? `${state.meName} paid ${playerName}` : `${playerName} paid ${state.meName}`;
    tr.appendChild(flowCell);

    const amountCell = document.createElement("td");
    amountCell.textContent = money(payment.amount);
    tr.appendChild(amountCell);

    const noteCell = document.createElement("td");
    noteCell.textContent = payment.note || " ";
    tr.appendChild(noteCell);

    table.appendChild(tr);
  });
}

function renderStatus(state) {
  const statusEl = document.getElementById("viewStatus");
  const hasData = state.players.length || state.sessions.length || state.payments.length;
  if (!hasData) {
    statusEl.textContent = "No saved tracker data found yet. Add data in the editable app first.";
    return;
  }
  const refreshedAt = new Date().toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  statusEl.textContent = `Read-only snapshot. Last update ${refreshedAt}.`;
}

async function renderAll() {
  const state = await loadStateWithSeed();
  const summary = computeBalances(state);
  renderStatus(state);
  renderSummary(state, summary);
  renderPlayers(state, summary);
  renderBalanceTable(summary);
  renderSessionTable(state);
  renderPaymentTable(state);
  applyResponsiveTableLabels();
}

window.addEventListener("storage", () => {
  void renderAll();
});

void renderAll();
