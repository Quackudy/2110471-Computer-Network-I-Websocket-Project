"use strict";
const $ = id => document.getElementById(id);
const state = { socket: null, me: null, users: [], groups: [], rooms: new Map(), active: null, pending: null, urls: new Map(), maxFile: 262144, aiModel: "", disconnected: false };
let toastTimer;

function node(tag, className, text) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
}
function initials(name) { return name.trim().split(/\s+/u).slice(0, 2).map(s => Array.from(s)[0]).join("").toUpperCase(); }
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 5000);
}
function send(event) {
  if (state.socket?.readyState !== WebSocket.OPEN || !state.me) { toast("You’re disconnected. Join again to continue."); return false; }
  state.socket.send(JSON.stringify(event));
  return true;
}
function reset() {
  for (const url of state.urls.values()) URL.revokeObjectURL(url);
  state.urls.clear(); state.rooms.clear(); state.me = null; state.users = []; state.groups = []; state.active = null; state.pending = null;
  $("welcome").hidden = false; $("chat").hidden = true; $("users").replaceChildren(); $("groups").replaceChildren();
  $("search").value = ""; $("message-input").value = ""; $("breadcrumb-room").textContent = "Welcome";
}
function connect(name) {
  reset(); state.disconnected = false;
  $("join-button").disabled = true; $("login-error").textContent = "Connecting…";
  const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  state.socket = socket;
  socket.addEventListener("open", () => socket.send(JSON.stringify({ type: "register", name })));
  socket.addEventListener("message", event => {
    let data;
    try { data = JSON.parse(event.data); } catch { toast("The server sent an invalid response."); return; }
    if (data.type === "welcome") {
      state.me = { id: data.id, name: data.name }; state.maxFile = data.max_file; state.aiModel = data.ai_model;
      $("my-name").textContent = data.name; $("my-avatar").textContent = initials(data.name);
      $("connection-label").textContent = "Online"; $("connection-badge").lastChild.textContent = "Live connection";
      $("login-dialog").close(); $("login-error").textContent = ""; $("join-button").disabled = false;
    } else if (data.type === "error") {
      state.pending = null;
      if (!state.me) { $("login-error").textContent = data.message; $("join-button").disabled = false; socket.close(); }
      else toast(data.message);
    } else if (data.type === "state") {
      state.users = data.users; state.groups = data.groups;
      for (const group of state.groups) { const room = state.rooms.get(group.id); if (room) Object.assign(room, group); }
      renderNav(); renderHeader();
    } else if (data.type === "room") {
      const old = state.rooms.get(data.room.id);
      state.rooms.set(data.room.id, { ...data.room, messages: data.messages, unread: old?.unread || 0, summary: old?.summary || null });
      const wanted = state.pending === "new" || state.pending === data.room.id || data.room.members.some(m => m.id === state.pending);
      if (!state.active || wanted) { state.pending = null; activate(data.room.id); }
      else if (state.active === data.room.id) renderMessages();
      renderNav();
    } else if (data.type === "message") {
      const room = state.rooms.get(data.message.room);
      if (!room) return;
      if (!room.messages.some(m => m.id === data.message.id)) room.messages.push(data.message);
      if (room.messages.length > 100) releaseMessage(room.messages.shift());
      if (data.message.sender !== state.me.id) send({ type: "received", room: room.id, ids: [data.message.id] });
      if (state.active === room.id) { renderMessages(true); markRead(); }
      else room.unread = (room.unread || 0) + 1;
      renderNav();
    } else if (data.type === "receipt") {
      const room = state.rooms.get(data.room);
      const message = room?.messages.find(m => m.id === data.id);
      if (message) { message.read_by = data.read_by; message.delivered_by = data.delivered_by; if (state.active === data.room) renderMessages(); }
    } else if (["summary_pending", "summary", "summary_error"].includes(data.type)) {
      const room = state.rooms.get(data.room);
      if (!room) return;
      room.summary = { text: data.type === "summary_pending" ? "Catching up on the conversation…" : (data.text || data.message), model: data.model, pending: data.type === "summary_pending" };
      if (state.active === data.room) renderSummary();
    }
  });
  socket.addEventListener("close", () => {
    if (state.socket !== socket) return;
    $("connection-label").textContent = "Offline";
    $("connection-badge").lastChild.textContent = "Disconnected";
    $("join-button").disabled = false;
    if (!$("login-error").textContent || $("login-error").textContent === "Connecting…") $("login-error").textContent = state.disconnected ? "See you soon. Join again whenever you’re ready." : "Connection closed. Join again to reconnect.";
    if ($("group-dialog").open) $("group-dialog").close();
    if (!$("login-dialog").open) $("login-dialog").showModal();
  });
  socket.addEventListener("error", () => { $("login-error").textContent = "Couldn’t reach the server. Please try again."; });
}

function roomName(room) {
  return room.kind === "group" ? room.name : room.members.find(m => m.id !== state.me.id)?.name || "Private chat";
}
function renderNav() {
  $("user-count").textContent = state.users.length;
  $("users").replaceChildren();
  for (const user of state.users) {
    const isMe = user.id === state.me?.id;
    const room = [...state.rooms.values()].find(r => r.kind === "private" && r.members.some(m => m.id === user.id) && !isMe);
    const button = node("button", `nav-row${room?.id === state.active ? " active" : ""}`);
    button.append(node("span", "avatar", initials(user.name)));
    const label = node("span", "nav-name"); label.append(node("strong", "", user.name)); button.append(label);
    if (isMe) { button.append(node("span", "self-label", "You")); button.disabled = true; }
    else {
      if (room?.unread) button.append(node("span", "unread-badge", String(room.unread)));
      else button.append(node("span", "status-dot"));
      button.addEventListener("click", () => { if (room) activate(room.id); else { state.pending = user.id; send({ type: "open_private", peer: user.id }); } });
    }
    $("users").append(button);
  }
  $("groups").replaceChildren();
  for (const group of state.groups) {
    const joined = group.members.some(m => m.id === state.me?.id);
    const button = node("button", `nav-row${group.id === state.active ? " active" : ""}`);
    button.append(node("span", "avatar group-avatar", "#"));
    const label = node("span", "nav-name"); label.append(node("strong", "", group.name));
    label.append(node("small", "", group.members.map(m => m.name).join(", ") || "No members yet"));
    button.append(label); button.title = group.members.map(m => m.name).join(", ") || "No members yet";
    const room = state.rooms.get(group.id);
    if (!joined) button.append(node("span", "join-label", "Join"));
    else if (room?.unread) button.append(node("span", "unread-badge", String(room.unread)));
    button.addEventListener("click", () => { if (joined && room) activate(group.id); else { state.pending = group.id; send({ type: "join_group", room: group.id }); } });
    $("groups").append(button);
  }
  $("no-groups").hidden = state.groups.length > 0;
}
function activate(id) {
  const previous = state.rooms.get(state.active);
  if (previous) previous.draft = $("message-input").value;
  state.active = id;
  const room = state.rooms.get(id); room.unread = 0;
  $("message-input").value = room.draft || ""; resizeComposer();
  $("search").value = ""; $("welcome").hidden = true; $("chat").hidden = false;
  document.querySelector(".sidebar").classList.remove("open");
  renderHeader(); renderNav(); renderSummary(); renderMessages(true); markRead();
  $("message-input").focus();
}
function renderHeader() {
  const room = state.rooms.get(state.active);
  if (!room) return;
  $("breadcrumb-room").textContent = roomName(room); $("room-name").textContent = roomName(room);
  $("room-icon").textContent = room.kind === "group" ? "#" : initials(roomName(room));
  const offline = room.kind === "private" && room.members.some(m => !state.users.some(u => u.id === m.id));
  $("room-members").textContent = room.members.map(m => m.name === state.me.name ? `${m.name} (you)` : m.name).join(" · ") + (offline ? " · Disconnected" : "");
  $("room-privacy").textContent = room.kind === "private" ? "↗ Only you and your recipient" : "↗ Only members of this room";
  $("message-input").disabled = offline; $("attach").disabled = offline; document.querySelector(".send-button").disabled = offline;
  $("message-input").placeholder = offline ? "This person has disconnected." : "Write a little something…";
}
function releaseMessage(message) {
  const url = state.urls.get(message.id); if (url) { URL.revokeObjectURL(url); state.urls.delete(message.id); }
}
function fileLink(message) {
  if (!state.urls.has(message.id)) {
    const bytes = Uint8Array.from(atob(message.data), c => c.charCodeAt(0));
    state.urls.set(message.id, URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" })));
  }
  const link = node("a", "file-download"); link.href = state.urls.get(message.id); link.download = message.filename;
  link.append(node("span", "file-icon", "▤"));
  const details = node("span", "file-details"); details.append(node("strong", "", message.filename), node("small", "", `${(message.bytes / 1024).toFixed(1)} KiB · Download file`));
  link.append(details, node("span", "download-arrow", "↓")); return link;
}
function renderMessages(scroll = false) {
  const room = state.rooms.get(state.active); if (!room) return;
  const container = $("messages"); const wasNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 80;
  const oldTop = container.scrollTop;
  container.replaceChildren();
  const query = $("search").value.trim().toLocaleLowerCase();
  const messages = room.messages.filter(m => `${m.name} ${m.text || m.filename || ""}`.toLocaleLowerCase().includes(query));
  if (!messages.length) {
    const empty = node("div", "chat-empty"); empty.append(node("strong", "", query ? "Nothing here just yet." : "Every conversation starts somewhere."), node("span", "", query ? "Try another search." : "Say hello. Share an idea. Make yourself at home.")); container.append(empty); return;
  }
  for (const message of messages) {
    const mine = message.sender === state.me.id;
    const row = node("article", `message-row${mine ? " mine" : ""}`); row.dataset.messageId = message.id;
    row.append(node("div", "avatar", initials(message.name)));
    const body = node("div", "message-body"); const meta = node("div", "message-meta");
    const date = new Date(message.timestamp * 1000); const timestamp = node("time", "", date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })); timestamp.dateTime = date.toISOString(); timestamp.title = date.toLocaleString();
    meta.append(node("strong", "", mine ? "You" : message.name), timestamp);
    const bubble = node("div", "message-bubble");
    if (message.kind === "file") bubble.append(fileLink(message)); else bubble.textContent = message.text;
    body.append(meta, bubble);
    if (mine) body.append(node("div", "message-receipt", message.read_by.length ? `✓✓ Read${room.kind === "group" ? ` by ${message.read_by.length}` : ""}` : (message.delivered_by.length ? "✓ Delivered" : "✓ Sent")));
    row.append(body); container.append(row);
  }
  if (scroll || wasNearBottom) container.scrollTop = container.scrollHeight; else container.scrollTop = oldTop;
}
function markRead() {
  if (document.hidden || !document.hasFocus()) return;
  const room = state.rooms.get(state.active); if (!room) return;
  const query = $("search").value.trim().toLocaleLowerCase();
  const ids = room.messages.filter(m => m.sender !== state.me.id && !m.read_by.includes(state.me.id) && `${m.name} ${m.text || m.filename || ""}`.toLocaleLowerCase().includes(query)).map(m => m.id);
  if (ids.length) send({ type: "read", room: room.id, ids });
}
function renderSummary() {
  const summary = state.rooms.get(state.active)?.summary;
  $("summary-card").hidden = !summary;
  $("summarize").disabled = Boolean(summary?.pending);
  if (summary) { $("summary-text").textContent = summary.text; $("summary-model").textContent = summary.model ? `Generated by ${summary.model} · AI can make mistakes` : ""; }
}
function resizeComposer() {
  const input = $("message-input"); input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 130)}px`;
  $("message-counter").textContent = `${input.value.length} / 4000`;
}
function openGroupDialog() { if (!state.me) return; $("group-input").value = ""; $("group-dialog").showModal(); }
$("login-form").addEventListener("submit", event => { event.preventDefault(); const name = $("name-input").value.trim(); if (name) connect(name); });
$("login-dialog").addEventListener("cancel", event => event.preventDefault());
$("new-group").addEventListener("click", openGroupDialog);
$("welcome-create").addEventListener("click", openGroupDialog);
$("cancel-group").addEventListener("click", () => $("group-dialog").close());
$("group-form").addEventListener("submit", event => { event.preventDefault(); const name = $("group-input").value.trim(); if (!name) return; state.pending = "new"; if (send({ type: "create_group", name })) $("group-dialog").close(); });
$("composer").addEventListener("submit", event => { event.preventDefault(); const text = $("message-input").value.trim(); if (text && state.active && send({ type: "message", room: state.active, text })) { $("message-input").value = ""; state.rooms.get(state.active).draft = ""; resizeComposer(); } });
$("message-input").addEventListener("input", resizeComposer);
$("message-input").addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("composer").requestSubmit(); } });
$("search").addEventListener("input", () => { renderMessages(); markRead(); });
$("summarize").addEventListener("click", () => send({ type: "summarize", room: state.active }));
$("close-summary").addEventListener("click", () => { state.rooms.get(state.active).summary = null; renderSummary(); });
$("attach").addEventListener("click", () => $("file-input").click());
$("file-input").addEventListener("change", async () => {
  const file = $("file-input").files[0]; $("file-input").value = "";
  if (!file || !state.active) return;
  const room = state.active;
  if (!file.size || file.size > state.maxFile) { toast("Choose a file between 1 byte and 256 KiB."); return; }
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = ""; for (const byte of bytes) binary += String.fromCharCode(byte);
    send({ type: "file", room, filename: file.name, data: btoa(binary) });
  } catch { toast("Couldn’t read this file. Please try another."); }
});
$("disconnect").addEventListener("click", () => { state.disconnected = true; state.socket?.close(); });
$("toggle-sidebar").addEventListener("click", () => document.querySelector(".sidebar").classList.toggle("open"));
document.addEventListener("visibilitychange", markRead);
window.addEventListener("focus", markRead);
$("login-dialog").showModal();
