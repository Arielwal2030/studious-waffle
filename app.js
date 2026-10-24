// SeatSmart: a dependency-free seating chart planner. All data stays in localStorage.

// Set this to your Ko-fi / Buy Me a Coffee / Gumroad link to show a support link in the footer.
const SUPPORT_URL = "";

const STORAGE_KEY = "seatsmart.v1";
const $ = (sel) => document.querySelector(sel);

let state = load();
let selectedGuest = null;

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved && Array.isArray(saved.guests) && Array.isArray(saved.tables)) return saved;
  } catch (e) {}
  return { guests: [], tables: [] };
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {}
}

const uid = () => Math.random().toString(36).slice(2, 10);
const norm = (s) => s.trim().toLowerCase();

function addGuest(name, party = "", avoid = []) {
  name = name.trim();
  if (!name) return;
  state.guests.push({ id: uid(), name, party: party.trim(), avoid, table: null });
}

function parseAvoid(text) {
  return text.split(",").map(norm).filter(Boolean);
}

function conflicts(a, b) {
  return a.id !== b.id && (a.avoid.includes(norm(b.name)) || b.avoid.includes(norm(a.name)));
}

function guestsAt(tableId) {
  return state.guests.filter((g) => g.table === tableId);
}

// Seats every unseated guest, keeping existing placements. Parties stay together where
// possible, and "keep apart" pairs never share a table. Returns guests it couldn't place.
function autoSeat() {
  const free = new Map(state.tables.map((t) => [t.id, t.seats - guestsAt(t.id).length]));

  const clusters = new Map();
  for (const g of state.guests) {
    if (g.table) continue;
    const key = g.party ? "p:" + norm(g.party) : "g:" + g.id;
    if (!clusters.has(key)) clusters.set(key, []);
    clusters.get(key).push(g);
  }
  const ordered = [...clusters.values()].sort((a, b) => b.length - a.length);

  const fits = (chunk, t) =>
    free.get(t.id) >= chunk.length &&
    !guestsAt(t.id).some((s) => chunk.some((c) => conflicts(c, s)));

  const unplaced = [];
  for (const cluster of ordered) {
    let rest = cluster.slice();
    while (rest.length) {
      const maxFree = Math.max(0, ...free.values());
      const chunk = rest.slice(0, Math.min(rest.length, maxFree));
      const candidates = chunk.length ? state.tables.filter((t) => fits(chunk, t)) : [];
      if (!candidates.length) {
        unplaced.push(rest.shift());
        continue;
      }
      // Prefer a table where this party already sits, then the tightest fit.
      const party = chunk[0].party && norm(chunk[0].party);
      candidates.sort((a, b) => {
        const pa = party && guestsAt(a.id).some((g) => norm(g.party) === party) ? 0 : 1;
        const pb = party && guestsAt(b.id).some((g) => norm(g.party) === party) ? 0 : 1;
        return pa - pb || free.get(a.id) - free.get(b.id);
      });
      const target = candidates[0];
      for (const g of chunk) g.table = target.id;
      free.set(target.id, free.get(target.id) - chunk.length);
      rest = rest.slice(chunk.length);
    }
  }
  return unplaced;
}

function warnings() {
  const out = [];
  for (const t of state.tables) {
    const seated = guestsAt(t.id);
    if (seated.length > t.seats) out.push(`${t.name} has ${seated.length} guests but only ${t.seats} seats.`);
    for (let i = 0; i < seated.length; i++)
      for (let j = i + 1; j < seated.length; j++)
        if (conflicts(seated[i], seated[j]))
          out.push(`${seated[i].name} and ${seated[j].name} should be kept apart but share ${t.name}.`);
  }
  const parties = new Map();
  for (const g of state.guests) {
    if (!g.party || !g.table) continue;
    const k = norm(g.party);
    if (!parties.has(k)) parties.set(k, { label: g.party, tables: new Set() });
    parties.get(k).tables.add(g.table);
  }
  for (const p of parties.values())
    if (p.tables.size > 1) out.push(`${p.label} is split across ${p.tables.size} tables.`);
  return out;
}

function guestEl(g) {
  const li = document.createElement("li");
  li.className = "guest";
  li.draggable = true;
  li.dataset.id = g.id;
  if (selectedGuest === g.id) li.classList.add("selected");
  if (g.table && guestsAt(g.table).some((o) => conflicts(g, o))) li.classList.add("conflict");

  const label = document.createElement("span");
  label.textContent = g.name;
  if (g.party) {
    const small = document.createElement("small");
    small.textContent = " · " + g.party;
    label.appendChild(small);
  }
  const x = document.createElement("button");
  x.className = "x";
  x.title = "Remove guest";
  x.textContent = "×";
  x.onclick = (e) => {
    e.stopPropagation();
    state.guests = state.guests.filter((o) => o.id !== g.id);
    commit();
  };
  li.append(label, x);

  li.ondragstart = (e) => e.dataTransfer.setData("text/plain", g.id);
  li.onclick = (e) => {
    e.stopPropagation();
    selectedGuest = selectedGuest === g.id ? null : g.id;
    render();
  };
  return li;
}

function makeDropzone(el, tableId) {
  el.ondragover = (e) => {
    e.preventDefault();
    el.classList.add("over");
  };
  el.ondragleave = () => el.classList.remove("over");
  el.ondrop = (e) => {
    e.preventDefault();
    el.classList.remove("over");
    moveGuest(e.dataTransfer.getData("text/plain"), tableId);
  };
  el.onclick = () => {
    if (selectedGuest) moveGuest(selectedGuest, tableId);
  };
}

function moveGuest(id, tableId) {
  const g = state.guests.find((o) => o.id === id);
  if (!g) return;
  g.table = tableId || null;
  selectedGuest = null;
  commit();
}

function render() {
  const pool = $("#pool");
  pool.replaceChildren(...state.guests.filter((g) => !g.table).map(guestEl));
  $("#unseatedCount").textContent = pool.children.length;

  const tables = $("#tables");
  tables.replaceChildren(
    ...state.tables.map((t) => {
      const seated = guestsAt(t.id);
      const card = document.createElement("article");
      card.className = "table dropzone";

      const head = document.createElement("header");
      const h3 = document.createElement("h3");
      h3.textContent = t.name;
      h3.title = "Double-click to rename";
      h3.ondblclick = (e) => {
        e.stopPropagation();
        const name = prompt("Table name", t.name);
        if (name && name.trim()) {
          t.name = name.trim();
          commit();
        }
      };
      const cap = document.createElement("span");
      cap.className = "cap" + (seated.length > t.seats ? " over" : seated.length === t.seats ? " full" : "");
      cap.textContent = `${seated.length}/${t.seats}`;
      const del = document.createElement("button");
      del.className = "x";
      del.title = "Delete table";
      del.textContent = "×";
      del.onclick = (e) => {
        e.stopPropagation();
        seated.forEach((g) => (g.table = null));
        state.tables = state.tables.filter((o) => o.id !== t.id);
        commit();
      };
      const right = document.createElement("span");
      right.append(cap, del);
      head.append(h3, right);

      const ul = document.createElement("ul");
      ul.className = "guests";
      ul.replaceChildren(...seated.map(guestEl));
      card.append(head, ul);
      makeDropzone(card, t.id);
      return card;
    })
  );

  const totalSeats = state.tables.reduce((n, t) => n + t.seats, 0);
  const seatedCount = state.guests.filter((g) => g.table).length;
  $("#stats").innerHTML = "";
  for (const [label, value] of [
    ["Guests", state.guests.length],
    ["Seated", seatedCount],
    ["Tables", state.tables.length],
    ["Seats", totalSeats],
  ]) {
    const s = document.createElement("span");
    s.innerHTML = `${label}: <b>${value}</b>`;
    $("#stats").appendChild(s);
  }
  if (state.guests.length > totalSeats && state.tables.length)
    $("#stats").insertAdjacentHTML("beforeend", `<span>You need <b>${state.guests.length - totalSeats}</b> more seats</span>`);

  $("#warnings").replaceChildren(
    ...warnings().map((w) => {
      const d = document.createElement("div");
      d.textContent = w;
      return d;
    })
  );
  $("#empty").hidden = state.tables.length > 0 || state.guests.length > 0;
}

function commit() {
  save();
  render();
}

function download(filename, text, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

const csvCell = (s) => `"${String(s).replace(/"/g, '""')}"`;

// ---- wiring ----

$("#guestForm").onsubmit = (e) => {
  e.preventDefault();
  const f = e.target;
  addGuest(f.name.value, f.party.value, parseAvoid(f.avoid.value));
  f.reset();
  f.name.focus();
  commit();
};

$("#bulkAdd").onclick = () => {
  for (const line of $("#bulk").value.split("\n")) {
    const [name, party = ""] = line.split(",");
    if (name) addGuest(name, party);
  }
  $("#bulk").value = "";
  commit();
};

$("#tableForm").onsubmit = (e) => {
  e.preventDefault();
  const f = e.target;
  const seats = Math.max(1, parseInt(f.seats.value, 10) || 8);
  state.tables.push({ id: uid(), name: f.name.value.trim(), seats });
  f.name.value = `Table ${state.tables.length + 1}`;
  commit();
};
$("#tableForm").name.value = `Table ${state.tables.length + 1}`;

$("#autoSeat").onclick = () => {
  if (!state.tables.length) return alert("Add at least one table first.");
  const unplaced = autoSeat();
  commit();
  if (unplaced.length)
    alert(`${unplaced.length} guest(s) couldn't be seated. Add more tables or seats, or relax a "keep apart" rule.`);
};

$("#clearSeats").onclick = () => {
  state.guests.forEach((g) => (g.table = null));
  commit();
};

$("#print").onclick = () => window.print();

$("#exportCsv").onclick = () => {
  const tableName = new Map(state.tables.map((t) => [t.id, t.name]));
  const rows = [["Table", "Guest", "Party"]];
  for (const g of state.guests) rows.push([tableName.get(g.table) || "Unseated", g.name, g.party]);
  download("seating-chart.csv", rows.map((r) => r.map(csvCell).join(",")).join("\n"), "text/csv");
};

$("#saveJson").onclick = () => download("seating-plan.json", JSON.stringify(state, null, 2), "application/json");

$("#loadJson").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (!Array.isArray(data.guests) || !Array.isArray(data.tables)) throw new Error();
    state = data;
    commit();
  } catch (err) {
    alert("That file isn't a SeatSmart plan.");
  }
  e.target.value = "";
};

$("#reset").onclick = () => {
  if (!confirm("Start a new plan? This clears all guests and tables.")) return;
  state = { guests: [], tables: [] };
  commit();
};

makeDropzone($("#pool"), null);
document.body.addEventListener("click", () => {
  if (selectedGuest) {
    selectedGuest = null;
    render();
  }
});

if (SUPPORT_URL) {
  $("#support").href = SUPPORT_URL;
  $("#support").hidden = false;
}

render();
