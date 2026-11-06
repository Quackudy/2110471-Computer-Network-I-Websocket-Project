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
  summarize: (room) => ({ type: "summarize", room }),
};

// ==============================================================================
// 2. Application State
// ==============================================================================

const state = {
  socket: null,
  me: null,             // { id, name }
  users: [],            // [{ id, name }]
  groups: [],           // [{ id, name, members: [{ id, name }] }]
  rooms: new Map(),     // room_id -> { id, kind, name, members, messages, summary }
  activeRoomId: null,
  maxFile: 262144,      // 256 KiB
  aiModel: "",
  fileUrls: new Map(),  // message_id -> Blob ObjectURL
};

// ==============================================================================
// 3. DOM Element Helpers
// ==============================================================================

const $ = (id) => document.getElementById(id);

let toastTimer = null;
function showToast(message) {
  const el = $("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 4000);
}

function sendCmd(cmd) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
    showToast("Disconnected from server. Please reconnect.");
    return false;
  }
  state.socket.send(JSON.stringify(cmd));
  return true;
}

// ==============================================================================
// 4. WebSocket Lifecycle & Dispatcher
// ==============================================================================

function connect(username) {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${protocol}://${location.host}/ws`;
  const socket = new WebSocket(wsUrl);
  state.socket = socket;

  $("btn-login").disabled = true;
  $("login-error").textContent = "Connecting...";

  socket.addEventListener("open", () => {
    // Send R3 register command
    sendCmd(ModelCmd.register(username));
  });

  socket.addEventListener("message", (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      showToast("Received invalid message payload.");
      return;
    }

    switch (data.type) {
      case "welcome":
        state.me = { id: data.id, name: data.name };
        state.maxFile = data.max_file || 262144;
        state.aiModel = data.ai_model || "";
        $("my-name").textContent = data.name;
        $("login-overlay").hidden = true;
        $("app").hidden = false;
        $("login-error").textContent = "";
        $("btn-login").disabled = false;
        break;

      case "error":
        if (!state.me) {
          $("login-error").textContent = data.message;
          $("btn-login").disabled = false;
          socket.close();
        } else {
          showToast(data.message);
        }
        break;

      case "state":
        state.users = data.users || [];
        state.groups = data.groups || [];
        renderSidebar();
        if (state.activeRoomId) renderHeader();
        break;

      case "room":
        state.rooms.set(data.room.id, {
          ...data.room,
          messages: data.messages || [],
          summary: null,
        });
        selectRoom(data.room.id);
        renderSidebar();
        break;

      case "message":
        handleIncomingMessage(data.message);
        break;

      case "receipt":
        handleReceiptUpdate(data);
        break;

      case "summary_pending":
        handleSummaryUpdate(data.room, "Generating summary with Ollama...", true);
        break;

      case "summary":
        handleSummaryUpdate(data.room, data.text, false, data.model);
        break;
    }
  });

  socket.addEventListener("close", () => {
    state.me = null;
    state.activeRoomId = null;
    $("login-overlay").hidden = false;
    $("app").hidden = true;
    $("btn-login").disabled = false;
    if ($("login-error").textContent === "Connecting...") {
      $("login-error").textContent = "Connection lost. Please log in again.";
    }
  });

  socket.addEventListener("error", () => {
    $("login-error").textContent = "Unable to connect to server.";
    $("btn-login").disabled = false;
  });
}

// ==============================================================================
// 5. Message & Receipt Handling
// ==============================================================================

function handleIncomingMessage(msg) {
  const room = state.rooms.get(msg.room);
  if (!room) return;

  if (!room.messages.some((m) => m.id === msg.id)) {
    room.messages.push(msg);
  }

  // Auto-send delivery receipt if sender is not me
  if (state.me && msg.sender !== state.me.id) {
    sendCmd(ModelCmd.received(room.id, [msg.id]));
  }

  if (state.activeRoomId === room.id) {
    renderMessages();
    markRead();
  }
}

function handleReceiptUpdate(data) {
  const room = state.rooms.get(data.room);
  if (!room) return;
  const msg = room.messages.find((m) => m.id === data.id);
  if (msg) {
    msg.read_by = data.read_by || [];
    msg.delivered_by = data.delivered_by || [];
    if (state.activeRoomId === data.room) {
      renderMessages();
    }
  }
}

function markRead() {
  if (document.hidden || !document.hasFocus() || !state.activeRoomId) return;
  const room = state.rooms.get(state.activeRoomId);
  if (!room) return;

  const unreadIds = room.messages
    .filter((m) => m.sender !== state.me.id && !m.read_by.includes(state.me.id))
    .map((m) => m.id);

  if (unreadIds.length > 0) {
    sendCmd(ModelCmd.read(room.id, unreadIds));
  }
}

function handleSummaryUpdate(roomId, text, isPending, model) {
  const room = state.rooms.get(roomId);
  if (!room) return;
  room.summary = { text, isPending, model };
  if (state.activeRoomId === roomId) {
    renderSummary();
  }
}

// ==============================================================================
// 6. UI Renderers
// ==============================================================================

function renderSidebar() {
  // 1. Online Users list
  $("user-count").textContent = state.users.length;
  const userList = $("user-list");
  userList.replaceChildren();

  for (const user of state.users) {
    const isMe = state.me && user.id === state.me.id;
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.className = "nav-item";

    const nameSpan = document.createElement("span");
    nameSpan.textContent = user.name;
    btn.appendChild(nameSpan);

    if (isMe) {
      const youBadge = document.createElement("span");
      youBadge.className = "badge-you";
      youBadge.textContent = "you";
      btn.appendChild(youBadge);
      btn.disabled = true;
    } else {
      btn.addEventListener("click", () => {
        sendCmd(ModelCmd.openPrivate(user.id));
      });
    }

    li.appendChild(btn);
    userList.appendChild(li);
  }

  // 2. Groups list
  const groupList = $("group-list");
  groupList.replaceChildren();

  for (const group of state.groups) {
    const joined = group.members.some((m) => state.me && m.id === state.me.id);
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.className = `nav-item${group.id === state.activeRoomId ? " active" : ""}`;

    const infoDiv = document.createElement("div");
    const nameSpan = document.createElement("span");
    nameSpan.textContent = group.name;
    const metaSpan = document.createElement("div");
    metaSpan.className = "nav-item-meta";
    metaSpan.textContent = `${group.members.length} member${group.members.length === 1 ? "" : "s"}`;
    infoDiv.append(nameSpan, metaSpan);
    btn.appendChild(infoDiv);

    if (!joined) {
      const joinBadge = document.createElement("span");
      joinBadge.className = "btn-sm btn-secondary";
      joinBadge.textContent = "Join";
      btn.appendChild(joinBadge);
      btn.addEventListener("click", () => {
        sendCmd(ModelCmd.joinGroup(group.id));
      });
    } else {
      btn.addEventListener("click", () => {
        selectRoom(group.id);
      });
    }

    li.appendChild(btn);
    groupList.appendChild(li);
  }
}

function selectRoom(roomId) {
  state.activeRoomId = roomId;
  $("empty-state").hidden = true;
  $("chat-panel").hidden = false;

  renderHeader();
  renderSummary();
  renderMessages();
  markRead();
  $("message-input").focus();
}

function renderHeader() {
  const room = state.rooms.get(state.activeRoomId);
  if (!room) return;

  const title = room.kind === "group"
    ? `# ${room.name}`
    : room.members.find((m) => m.id !== state.me.id)?.name || "Private chat";

  $("room-title").textContent = title;
  const memberNames = room.members
    .map((m) => (m.id === state.me.id ? `${m.name} (you)` : m.name))
    .join(", ");
  $("room-members").textContent = `Members: ${memberNames}`;
}

function renderSummary() {
  const room = state.rooms.get(state.activeRoomId);
  const box = $("summary-box");
  if (!room || !room.summary) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  $("summary-text").textContent = room.summary.text;
  $("summary-model").textContent = room.summary.model ? `Model: ${room.summary.model}` : "";
}

function getFileUrl(msgId, filename, base64Data) {
  if (state.fileUrls.has(msgId)) {
    return state.fileUrls.get(msgId);
  }
  const binary = atob(base64Data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  const blob = new Blob([bytes], { type: "application/octet-stream" });
  const url = URL.createObjectURL(blob);
  state.fileUrls.set(msgId, url);
  return url;
}

function renderMessages() {
  const room = state.rooms.get(state.activeRoomId);
  const list = $("message-list");
  list.replaceChildren();
  if (!room) return;

  for (const msg of room.messages) {
    const isMine = state.me && msg.sender === state.me.id;
    const row = document.createElement("div");
    row.className = `msg-row${isMine ? " mine" : ""}`;

    const header = document.createElement("div");
    header.className = "msg-header";
    const sender = document.createElement("strong");
    sender.textContent = isMine ? "You" : msg.name;
    const time = document.createElement("span");
    time.className = "msg-time";
    time.textContent = new Date(msg.timestamp * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    header.append(sender, time);
    row.appendChild(header);

    const body = document.createElement("div");
    body.className = "msg-body";

    if (msg.kind === "file") {
      const fileDiv = document.createElement("div");
      fileDiv.className = "file-attachment";
      const link = document.createElement("a");
      link.href = getFileUrl(msg.id, msg.filename, msg.data);
      link.download = msg.filename;
      link.textContent = `📎 ${msg.filename} (${(msg.bytes / 1024).toFixed(1)} KiB)`;
      fileDiv.appendChild(link);
      body.appendChild(fileDiv);
    } else {
      body.textContent = msg.text;
    }
    row.appendChild(body);

    if (isMine) {
      const receipt = document.createElement("span");
      receipt.className = "msg-receipt";
      if (msg.read_by && msg.read_by.length > 0) {
        receipt.textContent = "✓✓ Read";
        receipt.classList.add("read");
      } else if (msg.delivered_by && msg.delivered_by.length > 0) {
        receipt.textContent = "✓✓ Delivered";
      } else {
        receipt.textContent = "✓ Sent";
      }
      row.appendChild(receipt);
    }

    list.appendChild(row);
  }

  list.scrollTop = list.scrollHeight;
}

// ==============================================================================
// 7. Event Listeners & User Actions
// ==============================================================================

// Login Form Submit
$("login-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = $("name-input").value.trim();
  if (name) connect(name);
});

// Send Message Submit
$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("message-input").value.trim();
  if (text && state.activeRoomId) {
    if (sendCmd(ModelCmd.message(state.activeRoomId, text))) {
      $("message-input").value = "";
    }
  }
});

// Group Creation Modal
$("btn-new-group").addEventListener("click", () => {
  $("group-name-input").value = "";
  $("group-dialog").showModal();
});

$("btn-cancel-group").addEventListener("click", () => {
  $("group-dialog").close();
});

$("group-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = $("group-name-input").value.trim();
  if (name) {
    sendCmd(ModelCmd.createGroup(name));
    $("group-dialog").close();
  }
});

// AI Summary Trigger
$("btn-summarize").addEventListener("click", () => {
  if (state.activeRoomId) {
    sendCmd(ModelCmd.summarize(state.activeRoomId));
  }
});

$("btn-close-summary").addEventListener("click", () => {
  const room = state.rooms.get(state.activeRoomId);
  if (room) {
    room.summary = null;
    renderSummary();
  }
});

// File Upload Trigger
$("btn-attach").addEventListener("click", () => {
  $("file-input").click();
});

$("file-input").addEventListener("change", async () => {
  const file = $("file-input").files[0];
  $("file-input").value = "";
  if (!file || !state.activeRoomId) return;

  if (file.size > state.maxFile) {
    showToast(`File too large. Maximum size is ${(state.maxFile / 1024).toFixed(0)} KiB.`);
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    const base64Data = reader.result.split(",")[1];
    sendCmd(ModelCmd.file(state.activeRoomId, file.name, base64Data));
  };
  reader.readAsDataURL(file);
});

// Disconnect Button
$("btn-disconnect").addEventListener("click", () => {
  state.socket?.close();
});

// Visibility & Focus for Read Receipts
document.addEventListener("visibilitychange", markRead);
window.addEventListener("focus", markRead);
