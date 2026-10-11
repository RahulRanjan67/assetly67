const DB = "assetly-outbox", VERSION = 2, STORE = "operations";
let dbPromise;

function openDb() {
  if (!window.indexedDB) return Promise.reject(new Error("IndexedDB unavailable"));
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, VERSION);
    r.onupgradeneeded = e => {
      const d = e.target.result;
      if (!d.objectStoreNames.contains(STORE)) {
        d.createObjectStore(STORE, { keyPath: "client_id" });
      }
    };
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
  return dbPromise;
}

function clientId() {
  return crypto.randomUUID ? crypto.randomUUID() : Date.now() + "-" + Math.random().toString(16).slice(2);
}

async function queue(operation, entity, id, data = {}) {
  const d = await openDb();
  return new Promise((resolve, reject) => {
    const t = d.transaction(STORE, "readwrite");
    t.objectStore(STORE).put({
      client_id: clientId(),
      operation,
      entity,
      id,
      data,
      queued_at: new Date().toISOString()
    });
    t.oncomplete = resolve;
    t.onerror = () => reject(t.error);
  });
}

async function pending() {
  const d = await openDb();
  return new Promise((resolve, reject) => {
    const r = d.transaction(STORE).objectStore(STORE).getAll();
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

async function flush() {
  if (!navigator.onLine) return;
  const status = document.getElementById("sync-status");
  try {
    const ops = await pending();
    if (!ops.length) {
      if (status) status.textContent = "Database Synchronized";
      return;
    }
    if (status) status.textContent = `Syncing ${ops.length} queued action(s)…`;
    const response = await fetch("/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operations: ops })
    });
    if (!response.ok) throw new Error("Sync failed");
    const d = await response.json();
    const db = await openDb();
    const t = db.transaction(STORE, "readwrite");
    const store = t.objectStore(STORE);
    ops.forEach(x => store.delete(x.client_id));
    t.oncomplete = () => {
      if (status) status.textContent = `Database Synchronized (${d.processed} synced)`;
    };
  } catch (e) {
    if (status) status.textContent = "Sync paused — will retry when connected";
  }
}

function setConnection() {
  const label = document.getElementById("connection-label");
  const note = document.getElementById("offline-note");
  if (label) label.textContent = navigator.onLine ? "ONLINE" : "OFFLINE";
  if (note) note.textContent = navigator.onLine ? "" : "· offline changes cached locally";
}

document.addEventListener("submit", async e => {
  const form = e.target;
  if (form.matches("[data-offline-form]") && !navigator.onLine) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    delete data.photo;
    await queue("CREATE", "asset", null, data);
    alert("Saved locally offline. It will be committed to MySQL once you reconnect.");
    return;
  }
  if (!form.matches("[data-sync-form],[data-json-form]")) return;
  e.preventDefault();
  const url = form.action;
  const parts = url.split("/");
  const id = parts[3] || null;
  const data = Object.fromEntries(new FormData(form).entries());

  if (form.matches("[data-json-form]")) {
    await queue("UPSERT", "repair", id, data);
    if (navigator.onLine) {
      try {
        await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data)
        });
        await flush();
        location.reload();
      } catch (_) {}
    } else {
      alert("Repair record saved offline; it will sync when online.");
    }
  } else {
    await queue("STATUS", "asset", id, data);
    if (navigator.onLine) {
      try {
        await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: parts[4] === "lost" ? "LOST" : "DESTROYED" })
        });
        await flush();
        location.reload();
      } catch (_) {}
    } else {
      alert("Status updated offline; it will sync when online.");
    }
  }
});

window.addEventListener("online", () => {
  setConnection();
  flush();
});
window.addEventListener("offline", setConnection);

// Initialize on page load
setConnection();
flush();
