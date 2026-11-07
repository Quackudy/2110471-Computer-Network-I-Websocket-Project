"use strict";

// ==============================================================================
// 1. Client Command Schemas (Mirrors server.py Pydantic Models)
// ==============================================================================

const ModelCmd = {
  register: (name) => ({ type: "register", name }),
  openPrivate: (peer) => ({ type: "open_private", peer }),
  createGroup: (name) => ({ type: "create_group", name }),
  joinGroup: (room) => ({ type: "join_group", room }),
  message: (room, text) => ({ type: "message", room, text }),
  file: (room, filename, data) => ({ type: "file", room, filename, data }),
  read: (room, ids) => ({ type: "read", room, ids }),
  received: (room, ids) => ({ type: "received", room, ids }),
  summarize: (room, provider) => ({ type: "summarize", room, provider }),
};

// ==============================================================================
// 2. Application State & Helpers
// ==============================================================================

const state = {
  socket: null,
  me: null,
  users: [],
  groups: [],
  rooms: new Map(),
  activeRoomId: null,
  maxFile: 262144,
  fileUrls: new Map(),
  markedReadIds: new Set(),
  markedReceivedIds: new Set(),
};

const $ = (id) => document.getElementById(id);

function showToast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  setTimeout(() => { t.hidden = true; }, 3000);
}

function setLoginBusy(busy) {
  const btn = $("btn-login");
  const input = $("name-input");
  if (btn) {
    btn.disabled = busy;
    btn.textContent = busy ? "Connecting..." : "Connect";
  }
  if (input) input.disabled = busy;
}

function setSummarizeBusy(busy) {
  const btn = $("btn-summarize");
  $("summary-provider").disabled = busy;
  if (btn) {
    btn.disabled = busy;
    btn.textContent = busy ? "Summarizing..." : "AI Summary";
  }
}

function send(cmd) {
  if (state.socket?.readyState === WebSocket.OPEN) {
    state.socket.send(JSON.stringify(cmd));
  } else {
    showToast("Disconnected.");
  }
}

// ==============================================================================
// 3. WebSocket Lifecycle & Event Dispatching
// ==============================================================================

function connect(username) {
  if (state.socket && state.socket.readyState !== WebSocket.CLOSED) {
    try { state.socket.close(); } catch {}
  }

  setLoginBusy(true);
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/ws`);
  state.socket = socket;

  $("login-error").textContent = "Connecting...";

  socket.addEventListener("open", () => send(ModelCmd.register(username)));

  socket.addEventListener("message", (event) => {
    let data;
    try { data = JSON.parse(event.data); } catch { return; }

    switch (data.type) {
      case "welcome":
        setLoginBusy(false);
        state.me = { id: data.id, name: data.name };
        state.maxFile = data.max_file || 262144;
        $("my-name").textContent = data.name;
        $("login-view").hidden = true;
        $("chat-view").hidden = false;
        $("user-status").hidden = false;
        $("login-error").textContent = "";
        break;

      case "error":
        if (!state.me) {
          setLoginBusy(false);
          $("login-error").textContent = data.message;
          socket.close();
        } else {
          setSummarizeBusy(false);
          showToast(data.message);
        }
        break;

      case "state":
        state.users = data.users || [];
        state.groups = data.groups || [];
        for (const group of state.groups) {
          const room = state.rooms.get(group.id);
          if (room?.kind === "group") {
            room.members = group.members;
          }
        }
        renderSidebar();
        if (state.activeRoomId) renderHeader();
        break;

      case "room":
        state.rooms.set(data.room.id, { ...data.room, messages: data.messages || [], summary: null });
        selectRoom(data.room.id);
        renderSidebar();
        break;

      case "message": {
        const room = state.rooms.get(data.message.room);
        if (!room) return;
        if (!room.messages.some((m) => m.id === data.message.id)) {
          room.messages.push(data.message);
        }
        if (state.me && data.message.sender !== state.me.id && !state.markedReceivedIds.has(data.message.id)) {
          state.markedReceivedIds.add(data.message.id);
          send(ModelCmd.received(room.id, [data.message.id]));
        }
        if (state.activeRoomId === room.id) {
          appendMessage(data.message);
          markRead();
        }
        break;
      }

      case "receipt": {
        const room = state.rooms.get(data.room);
        const msg = room?.messages.find((m) => m.id === data.id);
        if (msg) {
          msg.read_by = data.read_by;
          msg.delivered_by = data.delivered_by;
          if (state.activeRoomId === data.room) {
            updateReceipt(data.id, msg);
          }
        }
        break;
      }

      case "summary_error": {
        setSummarizeBusy(false);
        showToast(data.message || "AI is unavailable. Please try again.");
        const room = state.rooms.get(data.room);
        if (room) {
          room.summary = null;
          if (state.activeRoomId === data.room) renderSummary();
        }
        break;
      }

      case "summary_pending":
      case "summary": {
        const room = state.rooms.get(data.room);
        if (data.type === "summary") setSummarizeBusy(false);
        if (!room) return;
        room.summary = { text: data.type === "summary_pending" ? "Summarizing..." : data.text, model: data.model };
        if (state.activeRoomId === data.room) renderSummary();
        break;
      }
    }
  });

  socket.addEventListener("close", () => {
    state.me = null;
    state.activeRoomId = null;
    state.markedReadIds.clear();
    state.markedReceivedIds.clear();
    setLoginBusy(false);
    setSummarizeBusy(false);
    $("login-view").hidden = false;
    $("chat-view").hidden = true;
    $("user-status").hidden = true;
  });
}

function markRead() {
  if (document.hidden || !document.hasFocus() || !state.activeRoomId) return;
  const room = state.rooms.get(state.activeRoomId);
  if (!room) return;
  const unread = room.messages
    .filter((m) => m.sender !== state.me?.id && !m.read_by.includes(state.me?.id) && !state.markedReadIds.has(m.id))
    .map((m) => m.id);
  if (unread.length) {
    for (const id of unread) state.markedReadIds.add(id);
    send(ModelCmd.read(room.id, unread));
  }
}

// ==============================================================================
// 4. UI Renderers
// ==============================================================================

function renderSidebar() {
  $("user-count").textContent = state.users.length;
  const userList = $("user-list");
  userList.replaceChildren();

  for (const u of state.users) {
    const isMe = u.id === state.me?.id;
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "user-btn";
    btn.textContent = isMe ? `${u.name} (you)` : u.name;
    if (isMe) {
      btn.disabled = true;
    } else {
      btn.addEventListener("click", () => {
        btn.disabled = true;
        send(ModelCmd.openPrivate(u.id));
        setTimeout(() => { btn.disabled = false; }, 600);
      });
    }
    li.appendChild(btn);
    userList.appendChild(li);
  }

  const groupList = $("group-list");
  groupList.replaceChildren();

  for (const g of state.groups) {
    const joined = g.members.some((m) => m.id === state.me?.id);
    const li = document.createElement("li");
    const row = document.createElement("div");
    row.className = `group-row${g.id === state.activeRoomId ? " active" : ""}`;
    row.title = g.members.length ? `Members: ${g.members.map((m) => m.name).join(", ")}` : "No members yet";

    const label = document.createElement("span");
    label.textContent = `# ${g.name} (${g.members.length})`;
    row.appendChild(label);

    if (!joined) {
      const joinBtn = document.createElement("button");
      joinBtn.type = "button";
      joinBtn.textContent = "Join";
      joinBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        send(ModelCmd.joinGroup(g.id));
      });
      row.appendChild(joinBtn);
    } else {
      row.style.cursor = "pointer";
      row.addEventListener("click", () => selectRoom(g.id));
    }

    li.appendChild(row);
    groupList.appendChild(li);
  }
}

function selectRoom(roomId) {
  state.activeRoomId = roomId;
  $("empty-hint").hidden = true;
  $("room-panel").hidden = false;
  renderHeader();
  renderSummary();
  renderMessages();
  markRead();
  $("msg-input").focus();
}

function renderHeader() {
  const room = state.rooms.get(state.activeRoomId);
  if (!room) return;
  $("room-title").textContent = room.kind === "group" ? `# ${room.name}` : room.members.find((m) => m.id !== state.me.id)?.name || "Private";
  $("room-members").textContent = ` [${room.members.map((m) => m.id === state.me.id ? `${m.name}*` : m.name).join(", ")}]`;
}

function renderSummary() {
  const room = state.rooms.get(state.activeRoomId);
  const box = $("summary-box");
  if (!room?.summary) { box.hidden = true; return; }
  box.hidden = false;
  $("summary-text").textContent = room.summary.text;
  $("summary-model").textContent = room.summary.model ? `(${room.summary.model})` : "";
}

function getFileUrl(id, b64) {
  if (state.fileUrls.has(id)) return state.fileUrls.get(id);
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([arr]));
  state.fileUrls.set(id, url);
  return url;
}

function createMessageElement(m) {
  const isMine = m.sender === state.me?.id;
  const line = document.createElement("div");
  line.className = `msg-line${isMine ? " mine" : ""}`;
  line.dataset.id = m.id;

  const time = document.createElement("span");
  time.className = "time";
  time.textContent = new Date(m.timestamp * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const author = document.createElement("b");
  author.textContent = isMine ? "You: " : `${m.name}: `;

  line.append(time, author);

  if (m.kind === "file") {
    const a = document.createElement("a");
    a.href = getFileUrl(m.id, m.data);
    a.download = m.filename;
    a.textContent = `[File: ${m.filename} (${(m.bytes / 1024).toFixed(1)} KiB)]`;
    line.appendChild(a);
  } else {
    line.appendChild(document.createTextNode(m.text));
  }

  if (isMine) {
    const rec = document.createElement("span");
    rec.className = `receipt${m.read_by?.length ? " read" : ""}`;
    rec.textContent = m.read_by?.length ? "✓✓ Read" : (m.delivered_by?.length ? "✓✓ Delivered" : "✓ Sent");
    line.appendChild(rec);
  }

  return line;
}

function renderMessages() {
  const room = state.rooms.get(state.activeRoomId);
  const box = $("msg-box");
  box.replaceChildren();
  if (!room) return;

  for (const m of room.messages) {
    box.appendChild(createMessageElement(m));
  }
  box.scrollTop = box.scrollHeight;
}

function appendMessage(m) {
  const box = $("msg-box");
  if (box.querySelector(`[data-id="${m.id}"]`)) return;
  box.appendChild(createMessageElement(m));
  box.scrollTop = box.scrollHeight;
}

function updateReceipt(id, msg) {
  const line = $("msg-box").querySelector(`[data-id="${id}"] .receipt`);
  if (line) {
    line.className = `receipt${msg.read_by?.length ? " read" : ""}`;
    line.textContent = msg.read_by?.length ? "✓✓ Read" : (msg.delivered_by?.length ? "✓✓ Delivered" : "✓ Sent");
  }
}

// ==============================================================================
// 5. Event Listeners
// ==============================================================================

$("login-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = $("name-input").value.trim();
  if (name) connect(name);
});

$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const inp = $("msg-input");
  const text = inp.value.trim();
  if (text && state.activeRoomId) {
    send(ModelCmd.message(state.activeRoomId, text));
    inp.value = "";
  }
});

$("group-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const inp = $("group-name-input");
  const name = inp.value.trim();
  if (name) {
    send(ModelCmd.createGroup(name));
    inp.value = "";
  }
});

$("btn-summarize").addEventListener("click", () => {
  if (state.activeRoomId) {
    setSummarizeBusy(true);
    send(ModelCmd.summarize(state.activeRoomId, $("summary-provider").value));
  }
});

$("btn-close-summary").addEventListener("click", () => {
  const room = state.rooms.get(state.activeRoomId);
  if (room) { room.summary = null; renderSummary(); }
});

$("btn-attach").addEventListener("click", () => $("file-input").click());

$("file-input").addEventListener("change", () => {
  const file = $("file-input").files[0];
  $("file-input").value = "";
  if (!file || !state.activeRoomId) return;
  if (file.size > state.maxFile) {
    showToast(`File too large (max 256 KiB).`);
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    send(ModelCmd.file(state.activeRoomId, file.name, reader.result.split(",")[1]));
  };
  reader.readAsDataURL(file);
});

$("btn-disconnect").addEventListener("click", () => state.socket?.close());

document.addEventListener("visibilitychange", markRead);
window.addEventListener("focus", markRead);
