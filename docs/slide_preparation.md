# Presentation Slides Content & AI Prompts Log
**Project:** Relay – WebSocket Chat Application (2110471 Computer Network I)
**Architecture:** Python `aiohttp` + `Pydantic v2` Dispatcher + Native Browser WebSockets

---

## Part 1: System Architecture Design (1.5 Points)

### Slide 01: Title Slide
* **Title:** Socket Programming: Simple Chat Application
* **Group:** Group X
* **Members:** [Student ID] Name Surname, [Student ID] Name Surname
* **Overview:** A real-time WebSocket chat application featuring 1-on-1 private messaging, self-join group chats, Base64 socket file transfer, message receipts, and local AI summarization via Ollama.

---

### Slide 02: Part 1 Overview
* **Title:** Part 1 – System Architecture Design
* **Key Requirement:** Must be fully completed before Part 2 can be graded.

---

### Slide 03: R1 – System Architecture Design (Diagram & Topology)
* **Requirement:** At least two clients running on different physical computers + server architecture.
* **Architecture Diagram:**
  * Client 1 (Physical Laptop A) $\to$ HTTPS/WSS (Port 443) $\to$ Traefik Reverse Proxy
  * Client 2 (Physical Laptop B) $\to$ HTTPS/WSS (Port 443) $\to$ Traefik Reverse Proxy
  * Traefik $\to$ Docker Internal Network (Port 8080) $\to$ Python `aiohttp` WebSocket Server
  * Python Server $\to$ Internal Network (Port 11434) $\to$ Ollama (Qwen2.5 0.5B Instruct)
* **Explanation:** Client and server are completely separated. The central server holds connection sessions and routes messages strictly to authorized participant sockets.

---

### Slide 04: R1 – Network Protocol Analysis
* **Table of Protocols:**
  | Protocol | Layer | Why Selected & How Used in Relay |
  |---|---|---|
  | **IP / TCP** | Network / Transport | Provides reliable, ordered packet delivery between physical hosts; underlies all WebSocket connections. |
  | **HTTPS** | Application | Serves static assets (`index.html`, `app.js`, `style.css`) and initiates the standard HTTP-to-WebSocket upgrade handshake (`Upgrade: websocket`). |
  | **WebSocket (WSS)** | Application | Full-duplex, persistent connection over a single TCP socket. All chat actions, messages, receipts, and files travel exclusively over `/ws`. |
  | **JSON** | Presentation | Structured schema for dispatching commands and events inside WebSocket frames. |
  | **TLS / SSL** | Security | Encrypts browser-to-proxy traffic to protect against sniffing and MITM attacks over public networks. |
  | **Internal HTTP** | Application | Private container communication between the Python server and the Ollama inference engine (no public port exposed). |

---

### Slide 05: R2 – Socket-Only Chat Transport & Dispatcher Architecture
* **Requirement:** The chat messages between the server and each client must be implemented using Socket Programming only.
* **Generative AI Prompt:**
  ```text
  Create an asynchronous Python WebSocket chat backend using aiohttp and Pydantic. 
  Ensure all chat commands travel strictly over a single persistent /ws endpoint.
  Implement a clean architecture:
  1. UserSession to encapsulate WebSocket connections and client metadata.
  2. ChatRoom to hold participant sets and in-memory message history.
  3. ChatServer with a dispatch() method routing commands to handlers and catching ValidationError centrally.
  4. Separate static HTTP asset serving from real-time socket communication.
  ```
* **Code Snapshot (for Slide Code Box):**
  ```python
  # server_v2.py: Central dispatch and single /ws WebSocket transport
  async def dispatch(self, session: UserSession, raw_text: str):
      try:
          data = json.loads(raw_text)
          handler = self.handlers.get(data.get("type"))
          if not handler:
              raise ValueError("Unknown command.")
          await handler(session, data)
      except (ValidationError, ValueError) as err:
          msg = err.errors()[0]["msg"] if isinstance(err, ValidationError) else str(err)
          await self.send(session, {"type": "error", "message": msg})

  async def ws_handler(request: web.Request) -> web.WebSocketResponse:
      socket = web.WebSocketResponse(heartbeat=30.0)
      await socket.prepare(request)
      session = UserSession(socket=socket)
      ...
  ```
* **Speaker Notes / Talking Points:**
  * **R2 Compliance:** Chat messages, group joins, and receipts travel strictly over the `/ws` WebSocket endpoint. No HTTP POST/GET endpoints are used for chat.
  * **Dispatcher Pattern:** Replaces long `if/elif` statements with a clean lookup table (`self.handlers`).
  * **Central Error Handling:** Catches Pydantic `ValidationError` and standard `ValueError` in one place, automatically returning `{"type": "error", "message": ...}` to the client.

---

## Part 2: Fundamental Implementation (7 Points)

### Slide 06: Part 2 Overview
* **Title:** Part 2 – Fundamental Implementation
* **Coverage:** R3–R11 (Registration $\to$ Presence $\to$ Private Rooms $\to$ Group Chats & Permissions).
* **Grading Requirement:** Must be fully completed before Part 3 Special Points can be graded.

---

### Slide 07: R3 – Unique Client Names
* **Requirement:** Each client must have a unique name.
* **Generative AI Prompt:**
  ```text
  Implement client name validation and uniqueness registration using Pydantic v2 in Python aiohttp:
  1. Define RegisterCmd model with field_validator ensuring the name contains 1–24 characters, matching [a-zA-Z0-9 ._-] and stripped of whitespace.
  2. In ChatServer.handle_register, check uniqueness across active UserSession objects using case-insensitive comparison (s.name.casefold() == cmd.name.casefold()).
  3. If duplicate, raise a ValueError with "That name is already connected. Choose another."
  4. On success, store the name in session.name and send a welcome JSON payload.
  ```
* **Code Snapshot (for Slide Code Box):**
  ```python
  class RegisterCmd(BaseModel):
      type: Literal["register"] = "register"
      name: str

      @field_validator("name")
      @classmethod
      def validate_name(cls, value: str) -> str:
          trimmed = value.strip()
          if not (1 <= len(trimmed) <= 24) or not NAME_PATTERN.fullmatch(trimmed):
              raise ValueError("Use 1–24 letters, numbers, spaces, dots, underscores or hyphens.")
          return trimmed

  async def handle_register(self, session: UserSession, data: dict):
      cmd = RegisterCmd(**data)
      if any(s.name.casefold() == cmd.name.casefold() for s in self.sessions.values()):
          raise ValueError("That name is already connected. Choose another.")
      session.name = cmd.name
      await self.send(session, {"type": "welcome", "id": session.id, "name": session.name})
      await self.broadcast_presence()
  ```
* **Speaker Notes / Talking Points:**
  * **Strict Validation:** Names are validated via regex and trimmed before storage.
  * **Case-Insensitive Equality:** `Alice` and `alice` cannot connect simultaneously.
  * **Immediate Confirmation:** Server assigns a unique UUID session ID and sends `welcome`.

---

### Slide 08: R4 – Connected Clients List (Presence)
* **Requirement:** Each client can see a list of names of all clients that are currently connected to the server including its own name.
* **Generative AI Prompt:**
  ```text
  Implement real-time presence broadcasting for connected chat clients:
  1. Create broadcast_presence() in ChatServer that collects all active registered sessions into a list of {"id": s.id, "name": s.name} and current groups.
  2. Broadcast a "state" JSON event to all connected sockets concurrently using asyncio.gather.
  3. Ensure broadcast_presence() triggers both when a user registers and when a user disconnects.
  ```
* **Code Snapshot (for Slide Code Box):**
  ```python
  async def broadcast_presence(self):
      """Broadcast online users and active groups to all connected clients (R4)."""
      await self.broadcast({
          "type": "state",
          "users": [{"id": s.id, "name": s.name} for s in self.sessions.values() if s.name],
          "groups": [self.describe_room(r) for r in self.rooms.values() if r.kind == "group"],
      })

  async def disconnect(self, session: UserSession):
      """Clean up session on disconnect and broadcast updated presence."""
      if self.sessions.pop(session.id, None) is not None:
          if session.name:
              await self.broadcast_presence()
  ```
* **Speaker Notes / Talking Points:**
  * **Real-Time Sync:** Whenever a user logs in or closes their tab, all online users receive the updated client list immediately.
  * **Includes Self:** The current user is explicitly included in the `users` array, enabling the frontend sidebar to display "Online (me)".

---

### Slide 09: R5 – Independent Chat Rooms (Private & Group)
* **Requirement:** Each chat between clients (both Private and Group message) must have its own chat room.
* **Generative AI Prompt:**
  ```text
  Implement 1-on-1 private room management in ChatServer:
  1. Define OpenPrivateCmd Pydantic model with peer: str.
  2. In handle_open_private, check if a ChatRoom(kind='private') already exists with members == {session.id, peer.id}.
  3. If not, instantiate a new ChatRoom with a unique UUID id and register both participant names.
  4. Concurrently send the "room" metadata payload to both participants using open_room().
  ```
* **Code Snapshot (for Slide Code Box):**
  ```python
  class OpenPrivateCmd(BaseModel):
      type: Literal["open_private"] = "open_private"
      peer: str

  async def handle_open_private(self, session: UserSession, data: dict):
      cmd = OpenPrivateCmd(**data)
      peer = self.sessions.get(cmd.peer)
      if peer is None or peer.id == session.id:
          raise ValueError("Choose another online user.")

      members = {session.id, peer.id}
      room = next((r for r in self.rooms.values()
                   if r.kind == "private" and r.members == members), None)
      if room is None:
          room = ChatRoom(uuid.uuid4().hex, "private", "Private conversation",
                          members, names={s.id: s.name for s in [session, peer]})
          self.rooms[room.id] = room
      await asyncio.gather(*(self.open_room(s, room) for s in [session, peer]))
  ```
* **Speaker Notes / Talking Points:**
  * **Dedicated Room Entity:** Every pair of users gets their own unique `ChatRoom` instance.
  * **Deduplication:** Clicking a peer multiple times re-opens the existing private room rather than creating duplicates.
  * **Dual Notification:** Calling `open_room()` for both users ensures both participants' UI switches/updates concurrently.

---

### Slide 10: R6 – Chat Box & Chat Window (UI & Message Exchange)
* **Requirement:** Each chat room must include a chat box for sending text messages and a chat window for displaying the sent messages and incoming messages.
* **Generative AI Prompt:**
  ```text
  Design the client-side socket message composer and display window:
  1. Listen for form submit on #composer and send JSON {"type": "message", "room": state.active, "text": text} over the WebSocket.
  2. Render incoming messages securely using textContent inside #messages container.
  3. Support Enter to send and Shift+Enter for multiline input.
  4. Maintain separate message histories and drafts per room in state.rooms.
  ```
* **Code Snapshot (for Slide Code Box):**
  ```javascript
  // static/app.js: Sending and rendering messages in dedicated chat window
  $("composer").addEventListener("submit", event => {
    event.preventDefault();
    const text = $("message-input").value.trim();
    if (text && state.active) {
      send({ type: "message", room: state.active, text });
      $("message-input").value = "";
    }
  });

  // Safe DOM rendering with textContent prevents XSS attacks
  const body = node("div", "message-body");
  body.textContent = message.text;
  row.append(avatar, header, body);
  $("messages").append(row);
  ```
* **Speaker Notes / Talking Points:**
  * **Two-Way Interaction:** Clear visual separation between the `#message-input` composer box and the `#messages` scrollable chat window.
  * **Security First:** Uses native `textContent` rather than `innerHTML`, ensuring HTML tags or script injection attempts render as harmless plain text.
  * **Per-Room State:** When switching rooms, previous message history and current message drafts are preserved in client state.

---

### Slide 11: R7 – Sender and Recipient Isolation (Direct Messages)
* **Requirement:** Each client can send a direct text message to any client in the list. Only the sender and receiver can see the messages.
* **Generative AI Prompt:**
  ```text
  Implement direct message delivery with strict privacy isolation in ChatServer:
  1. Define MessageCmd model validating room: str and text: str (1–4000 chars).
  2. Implement authorized_room() that raises ValueError if the session is not in room.members.
  3. Derive sender identity from session.id on the server (never trusting client-supplied sender values).
  4. Append message to room.messages (deque maxlen=100) and broadcast JSON exclusively to room.members.
  ```
* **Code Snapshot (for Slide Code Box):**
  ```python
  async def handle_message(self, session: UserSession, data: dict):
      cmd = MessageCmd(**data)
      room = self.authorized_room(session, cmd.room)
      message = {
          "id": uuid.uuid4().hex, "room": room.id, "sender": session.id,
          "name": session.name, "timestamp": time.time(), "kind": "message",
          "text": cmd.text, "read_by": [], "delivered_by": [],
      }
      room.messages.append(message)
      await self.broadcast({"type": "message", "message": message}, room.members)
  ```
* **Speaker Notes / Talking Points:**
  * **Strict Privacy Isolation:** Messages are broadcast *only* to `room.members` (`{Alice, Bob}`). A third connected client ("Eve") receives zero packets.
  * **Anti-Spoofing:** Sender ID and sender name are stamped by the server from `session.id` and `session.name`; forged `"sender"` fields in the client payload are completely ignored.
  * **Automatic Ring Buffer:** `room.messages` uses Python `deque(maxlen=100)`—automatically keeping the 100 newest messages without any complicated byte eviction logic.

---

### Slide 12: R8 – Group Creation (Creator Starts Alone)
* **Requirement:** Each client can create a chat group(s), which initially includes only themselves as a member.
* **Generative AI Prompt:**
  ```text
  Implement chat group creation using Pydantic in ChatServer:
  1. Define CreateGroupCmd model with name: str (1–40 characters, trimmed).
  2. In handle_create_group, instantiate ChatRoom(kind='group') with members={session.id} ensuring the creator is the sole initial member.
  3. Open room for the creator and broadcast updated presence so all clients see the new group.
  ```
* **Code Snapshot (for Slide Code Box):**
  ```python
  class CreateGroupCmd(BaseModel):
      type: Literal["create_group"] = "create_group"
      name: str = Field(min_length=1, max_length=40)

  async def handle_create_group(self, session: UserSession, data: dict):
      cmd = CreateGroupCmd(**data)
      room = ChatRoom(
          id=uuid.uuid4().hex, kind="group", name=cmd.name,
          members={session.id}, names={session.id: session.name}
      )
      self.rooms[room.id] = room
      await self.open_room(session, room)
      await self.broadcast_presence()
  ```
* **Speaker Notes / Talking Points:**
  * **Creator Only:** The new group's initial membership set is strictly `{session.id}`.
  * **No Forced Inclusion:** There is no command or mechanism to force other clients into the group upon creation.
  * **Immediate Sync:** All connected clients immediately see the new group in their sidebar.

---

### Slide 13: R9 – Browse All Groups & Member Lists
* **Requirement:** Each client can see a list of all existing chat groups (with the member list) created by any client.
* **Generative AI Prompt:**
  ```text
  Implement group list and membership discovery in ChatServer:
  1. In describe_room(), map room.members to [{"id": mid, "name": room.names[mid]}].
  2. In broadcast_presence(), include all active groups in the "groups" list of the "state" event.
  3. On the frontend, display all groups and their current member list in the sidebar navigation.
  ```
* **Code Snapshot (for Slide Code Box):**
  ```python
  def describe_room(self, room: ChatRoom) -> dict:
      return {
          "id": room.id, "kind": room.kind, "name": room.name,
          "members": [{"id": mid, "name": room.names.get(mid, "")}
                      for mid in sorted(room.members)],
      }

  async def broadcast_presence(self):
      await self.broadcast({
          "type": "state",
          "users": [{"id": s.id, "name": s.name} for s in self.sessions.values() if s.name],
          "groups": [self.describe_room(r) for r in self.rooms.values() if r.kind == "group"],
      })
  ```
* **Speaker Notes / Talking Points:**
  * **Full Visibility:** Every client can see all existing groups and who is inside, even before choosing to join.
  * **Real-Time Group State:** Any group creation or member joining immediately broadcasts fresh group state to everyone.

---

### Slide 14: R10 – Voluntary Self-Join Group Chat
* **Requirement:** Clients can choose to join a group chat only by themselves; they are not added automatically by the group creator.
* **Generative AI Prompt:**
  ```text
  Implement voluntary group joining in ChatServer:
  1. Define JoinGroupCmd model validating room: str.
  2. In handle_join_group, ensure the room exists and kind == 'group'.
  3. Add session.id to room.members (self-joining action triggered by the user).
  4. Call open_room() for the joining client and broadcast updated group presence to all clients.
  ```
* **Code Snapshot (for Slide Code Box):**
  ```python
  class JoinGroupCmd(BaseModel):
      type: Literal["join_group"] = "join_group"
      room: str

  async def handle_join_group(self, session: UserSession, data: dict):
      cmd = JoinGroupCmd(**data)
      room = self.rooms.get(cmd.room)
      if room is None or room.kind != "group":
          raise ValueError("This group does not exist.")
      room.members.add(session.id)
      room.names[session.id] = session.name
      await self.open_room(session, room)
      await self.broadcast_presence()
  ```
* **Speaker Notes / Talking Points:**
  * **Self-Action Only:** The user must explicitly send a `join_group` command on their own WebSocket connection.
  * **Instant Access:** Upon joining, `open_room()` delivers the room view and the member list updates for everyone.

---

### Slide 15: R11 – Members-Only Group Messaging
* **Requirement:** Each client can send a text message to the group that they joined. Only the members of the chat group can see the messages.
* **Generative AI Prompt:**
  ```text
  Enforce group message authorization and delivery boundaries:
  1. In handle_message, verify session.id in room.members via authorized_room().
  2. Broadcast group text messages strictly to room.members.
  3. Non-members who attempt to send to the group receive an error and non-members receive zero message frames.
  ```
* **Code Snapshot (for Slide Code Box):**
  ```python
  def authorized_room(self, session: UserSession, room_id: str) -> ChatRoom:
      room = self.rooms.get(room_id)
      if room is None or session.id not in room.members:
          raise ValueError("Join this room before using it.")
      return room

  async def handle_message(self, session: UserSession, data: dict):
      cmd = MessageCmd(**data)
      room = self.authorized_room(session, cmd.room)
      message = { ... }
      room.messages.append(message)
      await self.broadcast({"type": "message", "message": message}, room.members)
  ```
* **Speaker Notes / Talking Points:**
  * **Unified Security:** Both 1-on-1 and group chats share the same `authorized_room()` guard.
  * **Strict Boundary:** If a client hasn't joined the group, attempting to send raises an error, and messages sent by existing members never reach them.

---

*(Slides Special 1 through Special 4 will be populated in the next step)*
