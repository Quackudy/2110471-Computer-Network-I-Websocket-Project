# Presentation Slides Content & AI Prompts Log
**Project:** Relay – WebSocket Chat Application (2110471 Computer Network I)
**Architecture:** Python `aiohttp` + `Pydantic v2` Dispatcher + Native Browser WebSockets
**Target:** 20-slide implementation explanation (rubric total: 12.5 points)

**Presentation files:** [Editable PowerPoint](Relay_Implementation_Explanation.pptx) and [filled PDF](Relay_Implementation_Explanation.pdf). Both use the supplied 20-page PDF template. Replace the group and student placeholders on slide 1 in the PowerPoint before presenting. Regenerate from the current source with `python docs/build_presentation.py` after installing `pymupdf` and `python-pptx`.

---

## Part 1: System Architecture Design (1.5 Points)

### Slide 01: Title Slide
* **Title:** Socket Programming: Simple Chat Application
* **Group:** Group X
* **Members:** [Student ID] Name Surname, [Student ID] Name Surname
* **Overview:** A real-time WebSocket chat application featuring 1-on-1 private messaging, self-join group chats, Base64 socket file transfer, message receipts, and user-selected Gemini or local Qwen summaries.

---

### Slide 02: Part 1 Overview & AI Planning Methodology
* **Title:** Part 1 – System Architecture Design & AI Planning
* **Key Requirement:** Must be fully completed before Part 2 can be graded (1.5 Points).
* **Coverage:** R1 (System Architecture & Network Protocols) and R2 (Socket-Only Chat Transport).
* **AI Pair Programming Methodology:**
  * Rather than prompting for disconnected code snippets, we attached the official course rubric PDF (`project_guidelines.pdf`) into our initial prompt to establish complete architectural constraints upfront.
  * We used an iterative step-by-step roadmap (Steps 1–5), pairing with the AI to refine schemas, handlers, and security boundaries.
* **Initial Master Prompt (Context & Architecture Planning):**
  ```text
  [Attached file: project_guidelines.pdf]

  "We have a university term project for Computer Network I to build a real-time chat application using WebSockets in Python.

  We attached our course requirement rubric. Key targets:
  - Part 1: System architecture (two physical laptops, pure socket chat transport over /ws, protocol explanation).
  - Part 2: Fundamental chat features (R3 unique names, R4 presence list, R5-R7 private 1-on-1 chat rooms, R8-R11 self-join group chats with member isolation).
  - Part 3: Special points (AI summary, socket file transfer, read/delivered receipts, automated cloud deployment).

  We want to use aiohttp and Pydantic for clean data validation and message routing (dispatcher pattern) so the code doesn't become a messy if-else block. Everything should run in-memory without a database.

  Can you help us design the architecture, plan out the data structures (sessions, rooms), and guide us through implementing it step-by-step?"
  ```
* **Speaker Notes / Talking Points:**
  * **Spec-Driven Architecture:** Grounded the AI on the actual course rubric PDF from day one.
  * **Architectural Roadmap:** The AI proposed the in-memory data structures (`UserSession`, `ChatRoom`) and an incremental 5-step implementation plan. Subsequent slide prompts follow this exact roadmap.

---

### Slide 03: R1 – System Architecture Design (Topology & Infrastructure)
* **Requirement:** At least two clients running on different physical computers + server architecture.
* **Architecture Flowchart:**
  ```text
  [ Client 1 (Laptop A) ] ──┐
                            ├──► [ Traefik : 443 ] ──► [ Python server : 8080 ] ──► [ Gemini API over HTTPS ]
  [ Client 2 (Laptop B) ] ──┘       (HTTPS / WSS)              │
                                                             └──► [ Ollama : 11434, private Docker network ]
  ```
* **How It Works (System Flow):**
  1. Two physical laptops (Client 1 & 2) connect over HTTPS/WSS (Port 443) to Traefik Reverse Proxy.
  2. Traefik terminates TLS/SSL and proxies plain HTTP/WebSocket traffic to Python server (Port 8080) on internal network.
  3. Each summary command selects Gemini or local Qwen. Gemini requests use HTTPS and require a server-side API key; local requests use Ollama on port 11434. A failed Gemini request retries with Ollama.
* **Key Notes & Highlights:**
  * **Physical Separation:** Completely independent client machines running native browser WebSockets.
  * **Public Boundary:** Traefik handles the public HTTPS/WSS route. Ollama has no published port; the Python app also has a host-loopback port for its deployment health check.

---

### Slide 04: R1 – Network Protocol Analysis
* **Table of Protocols (What / Why / How):**
  * **TCP (Transport Layer)**
    * **Why:** Since we’re using WebSocket and HTTP, TCP is naturally used underneath. It gives us reliable, ordered packet delivery between hosts so no chat messages are dropped or out of order.
    * **How:** Works behind our WebSocket and HTTP connections as the underlying transport layer.
  * **WebSocket (Application Layer)**
    * **Why:** In our opinion, this is the easiest and most lightweight way to build our real-time chat application without slow HTTP polling.
    * **How:** Acts as our main channel (`/ws`). All chat actions, messages, receipts, and files travel over this single persistent connection.
  * **HTTP / HTTPS (Application Layer)**
    * **Why:** The standard and simplest way to deliver our web interface to browser clients.
    * **How:** `aiohttp` serves static files (`index.html`, `app.js`, `style.css`) and accepts the WebSocket upgrade. The Python server also makes an outgoing HTTP(S) request to the selected AI provider for summaries.

---

### Slide 05: R2 – Socket-Only Chat Transport & Dispatcher Architecture
* **Requirement:** The chat messages between the server and each client must be implemented using Socket Programming only.
* **Generative AI Prompt:**
  ```text
  "Let's start with Step 1: Set up the application entry point with aiohttp, bind the persistent /ws endpoint in create_app(), and write ws_handler to accept the WebSocket upgrade and route incoming frames into a central dispatch() function."
  ```
* **Code Snapshot 1 (Left: Application Entry Point & Route Registration):**
  ```python
  # server.py: Application Entry Point & Route Registration
  def create_app() -> web.Application:
      server = ChatServer()
      app = web.Application()
      app["chat_server"] = server

      # R2: The ONLY chat endpoint is /ws (no HTTP POST chat endpoints)
      app.router.add_get("/ws", ws_handler)
      app.router.add_get("/healthz", health)
      app.router.add_get("/", serve_static)
      app.router.add_get("/{filename}", serve_static)
      return app

  if __name__ == "__main__":
      app = create_app()
      web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
  ```
* **Code Snapshot 2 (Right: WebSocket Handshake & Central Dispatcher):**
  ```python
  # server.py: WebSocket Handshake & Central Dispatcher
  async def ws_handler(request: web.Request) -> web.WebSocketResponse:
      server: ChatServer = request.app["chat_server"]
      socket = web.WebSocketResponse(heartbeat=30.0, max_msg_size=400_000)
      await socket.prepare(request)  # HTTP 101 Switching Protocols

      session = UserSession(socket=socket)
      server.sessions[session.id] = session
      try:
          async for msg in socket:
              if msg.type == WSMsgType.TEXT:
                  await server.dispatch(session, msg.data)
      finally:
          await server.disconnect(session)
      return socket
  ```
* **How It Works (Code & Flow):**
  1. The `if __name__ == "__main__"` block calls `create_app()` and starts `web.run_app()` on port 8080 by default; `create_app()` binds static routes and `/ws`.
  2. `ws_handler()` accepts connection (HTTP 101 Upgrade), creates `UserSession(id=UUID)`, and streams frames via `async for msg in socket`.
  3. Incoming text frames are passed to `server.dispatch()` to validate schemas and route to handlers.
* **Key Notes & Highlights:**
  * **100% Socket Transport:** No HTTP POST chat endpoints—all messages, receipts, and files travel exclusively over `/ws`.
  * **Central Error Interception:** Catches `ValidationError` and `ValueError` centrally and sends friendly error frames back to client.

---

## Part 2: Fundamental Implementation (7 Points)

### Slide 06: Part 2 Overview
* **Title:** Part 2 – Fundamental Implementation
* **Coverage:** R3–R11 (Registration $\to$ Presence $\to$ Private Rooms $\to$ Group Chats & Permissions).
* **Grading Requirement:** Must be fully completed before Part 3 Special Points can be graded (7 Points).

---

### Slide 07: R3 – Unique Client Names
* **Requirement:** Each client must have a unique name.
* **Generative AI Prompt:**
  ```text
  "For Step 2 (Registration): How should we validate the username with Pydantic and check that the name isn't already taken by another active user?"
  ```
* **Code Snapshot 1 (Left: Pydantic Validation Schema):**
  ```python
  # server.py: Client Registration Command Schema
  NAME_PATTERN = re.compile(r"^[\w .-]{1,24}$", re.UNICODE)

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
  ```
* **Code Snapshot 2 (Right: Registration Handler & Uniqueness Check):**
  ```python
  # server.py: Case-Insensitive Uniqueness Check & Session Binding
  async def handle_register(self, session: UserSession, data: dict):
      cmd = RegisterCmd(**data)

      dead = [s for s in list(self.sessions.values()) if s.socket.closed]
      for s in dead:
          await self.disconnect(s)

      if any(s.name.casefold() == cmd.name.casefold()
             for s in self.sessions.values() if s.id != session.id):
          raise ValueError("That name is already connected. Choose another.")

      if len(self.sessions) >= 100:
          raise ValueError("The server is full. Try again later.")

      session.name = cmd.name
      await self.send(session, {
          "type": "welcome", "id": session.id, "name": session.name,
          "ai_model": AI_MODEL, "max_file": MAX_FILE,
      })
      await self.broadcast_presence()
  ```
* **How It Works (Code & Flow):**
  1. Client sends `{"type": "register", "name": "..."}` over WebSocket.
  2. `RegisterCmd` trims whitespace and validates length (1–24 chars) and regex `^[\w .-]{1,24}$`.
  3. `handle_register()` removes closed sockets, checks `casefold()` against other active sessions, and enforces the 100-session limit. If unique, it saves `session.name` and replies with `welcome`.
* **Key Notes & Highlights:**
  * **Case-Insensitive Check:** Prevents duplicate logins like `Alice` and `alice` at the same time.
  * **Ephemeral Identity:** Name is tied to the active socket session UUID; when disconnected, the name is freed.

---

### Slide 08: R4 – Connected Clients List (Presence)
* **Requirement:** Each client can see a list of names of all clients that are currently connected to the server including its own name.
* **Generative AI Prompt:**
  ```text
  "Now for R4: How do we broadcast the list of online users and groups to everyone whenever someone registers or disconnects?"
  ```
* **Code Snapshot 1 (Left: Presence Broadcast Engine):**
  ```python
  # server.py: Real-Time Presence Broadcast
  async def broadcast_presence(self):
      """Broadcast online users and active groups to all clients (R4)."""
      await self.broadcast({
          "type": "state",
          "users": [
              {"id": s.id, "name": s.name}
              for s in self.sessions.values() if s.name
          ],
          "groups": [
              self.describe_room(r)
              for r in self.rooms.values() if r.kind == "group"
          ],
      })
  ```
* **Code Snapshot 2 (Right: Disconnection Lifecycle Cleanup):**
  ```python
  # server.py: Disconnection & Presence Update
  async def disconnect(self, session: UserSession):
      """Clean up on disconnect and update presence across all clients."""
      if session.summary_task and not session.summary_task.done():
          session.summary_task.cancel()
      if self.sessions.pop(session.id, None) is None:
          return

      for room_id, room in list(self.rooms.items()):
          if room.kind == "group":
              room.members.discard(session.id)
              room.names.pop(session.id, None)
              if not room.members:
                  del self.rooms[room_id]
          elif room.kind == "private" and not room.members & self.sessions.keys():
              del self.rooms[room_id]

      if session.name:
          await self.broadcast_presence()
  ```
* **How It Works (Code & Flow):**
  1. Whenever a user registers or disconnects, server calls `broadcast_presence()`.
  2. Server collects all active sessions `[{"id": s.id, "name": s.name}]` and group rooms.
  3. Broadcasts a `{"type": "state", ...}` event to all connected sockets concurrently via `asyncio.gather()`.
* **Key Notes & Highlights:**
  * **Real-Time Sync:** Instant UI updates across all clients without slow HTTP polling.
  * **Self-Inclusive:** User's own session is included so UI can label "(you)".

---

### Slide 09: R5 – Dedicated Chat Rooms (Private & Group)
* **Requirement:** Each chat between clients (both Private and Group message) must have its own chat room.
* **Generative AI Prompt:**
  ```text
  "Moving to Step 3 (Private Chat): How do we create or find an isolated room between two specific sessions when a user clicks on someone's name?"
  ```
* **Code Snapshot 1 (Left: Private Room Initiation):**
  ```python
  # server.py: Private Room Opening & Deduplication
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
* **Code Snapshot 2 (Right: Room Delivery & State Serialization):**
  ```python
  # server.py: Delivering Room Metadata and History
  async def open_room(self, session: UserSession, room: ChatRoom):
      """Deliver room metadata and message history to a client."""
      await self.send(session, {
          "type": "room",
          "room": self.describe_room(room),
          "messages": list(room.messages),
      })

  def describe_room(self, room: ChatRoom) -> dict:
      return {
          "id": room.id, "kind": room.kind, "name": room.name,
          "members": [{"id": m, "name": room.names.get(m, "")} for m in sorted(room.members)],
      }
  ```
* **How It Works (Code & Flow):**
  1. User sends `{"type": "open_private", "peer": peer_id}`.
  2. `handle_open_private()` checks if a room with `members == {session.id, peer.id}` already exists.
  3. If not, instantiates a new `ChatRoom` with unique UUID.
  4. Calls `open_room()` to deliver room metadata and message history to both users concurrently.
* **Key Notes & Highlights:**
  * **Deduplication:** Multiple clicks on the same user reuse the existing room instead of creating duplicates.
  * **Isolated State:** Each conversation is its own separate room object in memory.

---

### Slide 10: R6 – Chat Box & Chat Window (Message Exchange)
* **Requirement:** Each chat room must include a chat box for sending text messages and a chat window for displaying the sent messages and incoming messages.
* **Generative AI Prompt:**
  ```text
  "For R6: How should we structure the message payload validation with Pydantic and store the recent message history inside each room?"
  ```
* **Code Snapshot 1 (Left: Message Command Validation & Storage Model):**
  ```python
  # server.py: Message Command Schema & Automatic Ring Buffer
  class MessageCmd(BaseModel):
      type: Literal["message"] = "message"
      room: str
      text: str = Field(min_length=1, max_length=4000)

      @field_validator("text")
      @classmethod
      def validate_text(cls, value: str) -> str:
          trimmed = value.strip()
          if not (1 <= len(trimmed) <= 4000):
              raise ValueError("Messages must contain 1–4000 characters.")
          return trimmed

  @dataclass
  class ChatRoom:
      id: str
      kind: Literal["private", "group"]
      name: str
      members: set[str]
      names: dict[str, str] = field(default_factory=dict)
      messages: deque = field(default_factory=lambda: deque(maxlen=100))
  ```
* **Code Snapshot 2 (Right: Message Ingestion & Delivery):**
  ```python
  # server.py: Message Recording & Socket Transmission
  async def handle_message(self, session: UserSession, data: dict):
      cmd = MessageCmd(**data)
      room = self.authorized_room(session, cmd.room)

      message = {
          "id": uuid.uuid4().hex, "room": room.id, "sender": session.id,
          "name": session.name, "timestamp": time.time(), "kind": "message",
          "text": cmd.text, "read_by": [], "delivered_by": [],
      }

      # Automatically keeps newest 100 messages via deque(maxlen=100)
      room.messages.append(message)
      await self.broadcast({"type": "message", "message": message}, room.members)
  ```
* **How It Works (Code & Flow):**
  1. User types in chat box and sends `{"type": "message", "room": room_id, "text": "..."}`.
  2. `MessageCmd` validates text length (1–4000 characters).
  3. Server appends message to `room.messages` (a ring buffer) and broadcasts to room members.
  4. Client chat window renders incoming messages in real time.
* **Key Notes & Highlights:**
  * **Automatic Ring Buffer:** `deque(maxlen=100)` automatically drops oldest messages beyond 100, preventing server memory overflow.
  * **UI Separation:** The message input is inside `#composer`; the scrollable history window is `#msg-box`.

---

### Slide 11: R7 – Sender and Recipient Isolation (Direct Messages)
* **Requirement:** Each client can send a direct text message to any client in the list. Only the sender and receiver can see the messages.
* **Generative AI Prompt:**
  ```text
  "For R7: Handle direct message sending so that only the sender and recipient receive the message, rejecting it if the peer disconnected."
  ```
* **Code Snapshot 1 (Left: Authorization Guard):**
  ```python
  # server.py: Room Authorization Guard
  def authorized_room(self, session: UserSession, room_id: str) -> ChatRoom:
      """Verify room exists and the calling session is an authorized member."""
      room = self.rooms.get(room_id)
      if room is None or session.id not in room.members:
          raise ValueError("Join this room before using it.")
      return room
  ```
* **Code Snapshot 2 (Right: Private Audience Transmission):**
  ```python
  # server.py: Server-Derived Identity & Isolated Broadcast
  async def handle_message(self, session: UserSession, data: dict):
      cmd = MessageCmd(**data)
      room = self.authorized_room(session, cmd.room)

      message = {
          "id": uuid.uuid4().hex, "room": room.id,
          "sender": session.id,  # Server-derived sender identity (anti-spoofing)
          "name": session.name, "timestamp": time.time(),
          "kind": "message", "text": cmd.text,
          "read_by": [], "delivered_by": [],
      }
      room.messages.append(message)

      # R7: Delivered strictly to room.members (only sender and receiver)
      await self.broadcast({"type": "message", "message": message}, room.members)
  ```
* **How It Works (Code & Flow):**
  1. User sends a private message to a 1-on-1 room.
  2. `authorized_room()` checks that sender is actually in `room.members`.
  3. Server injects server-derived `session.id` and `session.name` as sender.
  4. Broadcasts message *only* to the 2 members of `{session.id, peer.id}`.
* **Key Notes & Highlights:**
  * **Zero Packet Leaks:** Third-party clients (e.g. Eve) never receive packets for rooms they aren't part of.
  * **Anti-Spoofing:** Server stamps sender identity; client-supplied sender values are ignored.

---

### Slide 12: R8 – Group Creation (Creator Starts Alone)
* **Requirement:** Each client can create a chat group(s), which initially includes only themselves as a member.
* **Generative AI Prompt:**
  ```text
  "Now Step 4 (Groups): Implement group creation where the creator is initially the only member and broadcast the new group to all clients."
  ```
* **Code Snapshot 1 (Left: Group Creation Schema):**
  ```python
  # server.py: Group Creation Command Schema
  class CreateGroupCmd(BaseModel):
      type: Literal["create_group"] = "create_group"
      name: str = Field(min_length=1, max_length=40)

      @field_validator("name")
      @classmethod
      def validate_name(cls, value: str) -> str:
          trimmed = value.strip()
          if not (1 <= len(trimmed) <= 40):
              raise ValueError("Group names must contain 1–40 characters.")
          return trimmed
  ```
* **Code Snapshot 2 (Right: Creator-Only Group Instantiation):**
  ```python
  # server.py: Group Instantiation with Creator as Sole Initial Member
  async def handle_create_group(self, session: UserSession, data: dict):
      cmd = CreateGroupCmd(**data)
      if len(self.rooms) >= 100:
          raise ValueError("Room limit reached.")

      # Initial membership set contains ONLY the creator's session.id (R8)
      room = ChatRoom(
          id=uuid.uuid4().hex, kind="group", name=cmd.name,
          members={session.id}, names={session.id: session.name}
      )
      self.rooms[room.id] = room
      await self.open_room(session, room)
      await self.broadcast_presence()
  ```
* **How It Works (Code & Flow):**
  1. User sends `{"type": "create_group", "name": "Study Group"}`.
  2. `CreateGroupCmd` validates name (1–40 characters).
  3. Server creates `ChatRoom(kind="group")` with initial `members = {session.id}`.
  4. Opens room for creator and broadcasts new group list to everyone via `broadcast_presence()`.
* **Key Notes & Highlights:**
  * **Creator Only:** The creator starts as the sole member; no users are forced into the group.
  * **Immediate Discovery:** All other connected clients see the new group appear in their list right away.

---

### Slide 13: R9 – Browse All Groups & Member Lists
* **Requirement:** Each client can see a list of all existing chat groups (with the member list) created by any client.
* **Generative AI Prompt:**
  ```text
  "For R9: Update the presence state broadcast so all connected clients can see all active chat groups along with their current member list."
  ```
* **Code Snapshot 1 (Left: Group Metadata Serialization):**
  ```python
  # server.py: Group & Member List Serialization
  def describe_room(self, room: ChatRoom) -> dict:
      """Helper to serialize room metadata and member lists for clients."""
      return {
          "id": room.id,
          "kind": room.kind,
          "name": room.name,
          "members": [
              {"id": mid, "name": room.names.get(mid, "")}
              for mid in sorted(room.members)
          ],
      }
  ```
* **Code Snapshot 2 (Right: Global Group State Broadcasting):**
  ```python
  # server.py: Distributing All Groups and Members
  async def broadcast_presence(self):
      """Broadcast online users and active groups to all clients (R4, R9)."""
      await self.broadcast({
          "type": "state",
          "users": [
              {"id": s.id, "name": s.name}
              for s in self.sessions.values() if s.name
          ],
          "groups": [
              self.describe_room(r)
              for r in self.rooms.values() if r.kind == "group"
          ],
      })
  ```
* **How It Works (Code & Flow):**
  1. `describe_room()` formats group metadata: `id`, `name`, and `members` array `[{"id": ..., "name": ...}]`.
  2. `broadcast_presence()` includes all groups in the global `state` event.
  3. Every client receives the list and renders each group name and member count. Hovering a group row shows the current member names in a native tooltip:
     ```js
     row.title = g.members.length ? `Members: ${g.members.map((m) => m.name).join(", ")}` : "No members yet";
     ```
* **Key Notes & Highlights:**
  * **Full Transparency:** Clients can inspect existing groups and their members before deciding to join.
  * **Live Membership Sync:** Joining or leaving broadcasts a new `state` event, so the count and hover tooltip update for all clients.

---

### Slide 14: R10 – Voluntary Self-Join Group Chat
* **Requirement:** Clients can choose to join a group chat only by themselves; they are not added automatically by the group creator.
* **Generative AI Prompt:**
  ```text
  "For R10: Implement self-join for groups so clients can choose to join an existing group voluntarily without being auto-added by the creator."
  ```
* **Code Snapshot 1 (Left: Group Join Command Schema):**
  ```python
  # server.py: Join Group Command Schema
  class JoinGroupCmd(BaseModel):
      """Validates joining an existing group (R10)."""
      type: Literal["join_group"] = "join_group"
      room: str
  ```
* **Code Snapshot 2 (Right: Voluntary Self-Join Execution):**
  ```python
  # server.py: Voluntary Self-Join Execution
  async def handle_join_group(self, session: UserSession, data: dict):
      cmd = JoinGroupCmd(**data)
      room = self.rooms.get(cmd.room)
      if room is None or room.kind != "group":
          raise ValueError("This group does not exist.")

      # The user adds their own session.id strictly on their own connection
      room.members.add(session.id)
      room.names[session.id] = session.name
      await self.open_room(session, room)
      await self.broadcast_presence()
  ```
* **How It Works (Code & Flow):**
  1. User clicks "Join" and sends `{"type": "join_group", "room": room_id}`.
  2. `handle_join_group()` verifies the group exists and adds `session.id` to `room.members`.
  3. Server delivers room history to the user via `open_room()` and updates presence for everyone.
* **Key Notes & Highlights:**
  * **Self-Action Only:** Users join strictly by their own voluntary action over their own socket.
  * **No Admin Force:** Group creators cannot force-add members without their consent.

---

### Slide 15: R11 – Members-Only Group Messaging
* **Requirement:** Each client can send a text message to the group that they joined. Only the members of the chat group can see the messages.
* **Generative AI Prompt:**
  ```text
  "For R11: Implement group messaging with strict room authorization so only verified members can send and receive group chat messages."
  ```
* **Code Snapshot 1 (Left: Membership Authorization Guard):**
  ```python
  # server.py: Guarding Group Membership Boundaries
  def authorized_room(self, session: UserSession, room_id: str) -> ChatRoom:
      room = self.rooms.get(room_id)
      if room is None or session.id not in room.members:
          raise ValueError("Join this room before using it.")
      return room
  ```
* **Code Snapshot 2 (Right: Group-Only Targeted Broadcast):**
  ```python
  # server.py: Broadcasting Strictly to Group Members
  async def handle_message(self, session: UserSession, data: dict):
      cmd = MessageCmd(**data)
      # Rejects non-members who haven't joined yet
      room = self.authorized_room(session, cmd.room)

      message = {
          "id": uuid.uuid4().hex, "room": room.id, "sender": session.id,
          "name": session.name, "timestamp": time.time(), "kind": "message",
          "text": cmd.text, "read_by": [], "delivered_by": [],
      }
      room.messages.append(message)

      # R11: Delivered strictly to room.members (non-members receive zero packets)
      await self.broadcast({"type": "message", "message": message}, room.members)
  ```
* **How It Works (Code & Flow):**
  1. Member sends text to group $\to$ `authorized_room()` checks `session.id in room.members`.
  2. If user hasn't joined, server rejects with `ValueError: Join this room before using it`.
  3. If authorized, appends message to history and broadcasts *strictly* to `room.members`.
* **Key Notes & Highlights:**
  * **Enforced Boundaries:** Non-members cannot read messages or post to the group.
  * **Shared Authorization Logic:** Private and group rooms use the exact same `authorized_room()` security gate.

---

## Part 3: Special Points (4 Points: 1.0 Point per Feature)

### Slide 16: Part 3 Overview
* **Title:** Part 3 – Special Points
* **Rubric Requirement:** 4 special features (1.0 point each, with at least 1 AI feature).
* **Our 4 Features:**
  1. **Special Point 1 (AI Feature):** Per-request Gemini or local Qwen summaries, with automatic local retry after Gemini failure.
  2. **Special Point 2:** Direct file transfer (up to 256 KiB) over persistent WebSocket frames using Base64.
  3. **Special Point 3:** Multi-state message receipts (Sent $\to$ Delivered $\to$ Read) with live status indicators.
  4. **Special Point 4:** Cloud-based automated deployment on Oracle Cloud with Docker, Traefik TLS, and CI/CD.

---

### Slide 17: Special Point 1: AI Chat Catch-up Summaries (AI Feature)
* **Description:** The browser's Model selector sends `provider: "gemini"` or `provider: "ollama"` with each summary command. Gemini failure or a missing key retries locally; choosing Local Qwen uses Ollama directly.
* **AI Models:** Gemini 3.5 Flash-Lite via the free-tier API with server-side `GEMINI_API_KEY`, and Qwen2.5 0.5B Instruct via Ollama. [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).
* **Development prompt (not the runtime model prompt):**
  ```text
  "For Special Point 1: Summarize recent room messages asynchronously without blocking WebSocket traffic; allow Gemini or local Qwen, with a local retry if Gemini fails."
  ```
* **Code Snapshot 1 (Left: Summarize Command Schema & Transcript Extraction):**
  ```python
  # server.py: Summarization Command Schema & Ingestion
  class SummarizeCmd(BaseModel):
      type: Literal["summarize"] = "summarize"
      room: str
      provider: Literal["gemini", "ollama"] = "gemini"

  async def handle_summarize(self, session: UserSession, data: dict):
      cmd = SummarizeCmd(**data)
      room = self.authorized_room(session, cmd.room)
      if session.summary_task and not session.summary_task.done():
          raise ValueError("Your summary is still running.")
      if self.ai_lock.locked():
          raise ValueError("AI is busy. Try again shortly.")

      transcript = [
          f"{m['name']}: {m['text']}" for m in room.messages
          if m.get("kind") == "message" and session.id in room.members
      ]
      if not transcript:
          raise ValueError("Send some text messages before requesting a summary.")

      session.summary_task = asyncio.create_task(
          self.execute_summarize(session, room.id, transcript[-30:], cmd.provider)
      )
  ```
* **Code Snapshot 2 (Right: Provider Selection & Local Retry, shortened excerpt):**
  ```python
  backends = ("gemini", "ollama") if provider == "gemini" and GEMINI_API_KEY else ("ollama",)
  for backend in backends:
      model = GEMINI_MODEL if backend == "gemini" else OLLAMA_MODEL
      try:
          # POST to Gemini generateContent or Ollama /api/chat; parse response.
          await self.send(session, {"type": "summary", "room": room_id,
                                    "text": text[:6000], "model": model})
          break
      except Exception:
          if backend == "ollama":
              raise
          logging.warning("Gemini summary failed; retrying with Ollama", exc_info=True)
  ```
* **How It Works (Code & Flow):**
  1. User selects a provider and sends `{"type": "summarize", "room": room_id, "provider": "gemini"}` (or `"ollama"`). The server collects up to 30 recent text messages.
  2. Server creates an async task (`create_task`) calling the selected provider. Gemini calls use HTTPS; local Qwen calls use internal HTTP. Gemini failures retry with local Qwen.
  3. Server sends `summary_pending` to the requesting user, waits under `asyncio.Lock`, and returns the summary.
* **Key Notes & Highlights:**
  * **Data Flow:** Gemini mode sends recent room text to Google; Ollama mode keeps inference on the Oracle server.
  * **Runtime prompts:** Gemini requests three brief bullet points. Local Qwen requests one factual sentence about agreed plans and tasks, at temperature 0. The local 0.5B model can still miss details; a prompt change does not guarantee accuracy.
  * **Non-Blocking Execution:** Async background task prevents LLM inference delays from blocking active WebSocket messaging.

---

### Slide 18: Special Point 2: File Sharing via WebSocket Frames
* **Description:** Transfer files (images, documents, code) up to 256 KiB directly through persistent WebSocket frames without HTTP upload endpoints.
* **Generative AI Prompt:**
  ```text
  "For Special Point 2: Allow users to send files up to 256KB by encoding them as Base64 inside regular WebSocket messages."
  ```
* **Code Snapshot 1 (Left: File Command Schema & Base64 Validation):**
  ```python
  # server.py: File Command Schema & Base64 Decoding in Model
  class FileCmd(BaseModel):
      type: Literal["file"] = "file"
      room: str
      filename: str
      data: str
      file_bytes: int = 0

      @field_validator("filename")
      @classmethod
      def validate_filename(cls, value: str) -> str:
          if not (1 <= len(value) <= 120) or "/" in value or "\\" in value or any(ord(c) < 32 for c in value):
              raise ValueError("Invalid file name.")
          return value

      @field_validator("data")
      @classmethod
      def validate_data(cls, value: str) -> str:
          try:
              decoded = base64.b64decode(value, validate=True)
          except (binascii.Error, ValueError):
              raise ValueError("Invalid file contents.")
          if not (1 <= len(decoded) <= MAX_FILE):
              raise ValueError("Files must contain 1 byte to 256 KiB.")
          return value
  ```
* **Code Snapshot 2 (Right: File Handling & Room Broadcast):**
  ```python
  # server.py: File Recording & WebSocket Broadcast
  async def handle_file(self, session: UserSession, data: dict):
      cmd = FileCmd(**data)
      room = self.authorized_room(session, cmd.room)

      message = {
          "id": uuid.uuid4().hex, "room": room.id,
          "sender": session.id, "name": session.name,
          "timestamp": time.time(), "kind": "file",
          "filename": cmd.filename, "data": cmd.data,
          "bytes": cmd.file_bytes,
          "read_by": [], "delivered_by": [],
      }
      room.messages.append(message)
      await self.broadcast({"type": "message", "message": message}, room.members)
  ```
* **How It Works (Code & Flow):**
  1. Client encodes file as Base64 and sends `{"type": "file", "filename": ..., "data": ...}`.
  2. `FileCmd` validates filename (no `/` or `\`) and decodes Base64 to verify size (1 byte to 256 KiB).
  3. Server records message with `kind="file"` and broadcasts directly to room members over `/ws`.
* **Key Notes & Highlights:**
  * **Pure Socket Transfer:** Files travel strictly inside WebSocket frames as Base64—no `POST /upload` or multipart forms.
  * **Path Traversal Protection:** Validator rejects filenames with directory traversal characters (`/` or `\`).

---

### Slide 19: Special Point 3: Delivery and Read Receipts
* **Description:** Real-time multi-stage message delivery tracking (Sent $\to$ Delivered $\to$ Read) displayed via live indicators.
* **Generative AI Prompt:**
  ```text
  "For Special Point 3: Implement read and delivered receipts by tracking which sessions have received or read each message ID."
  ```
* **Code Snapshot 1 (Left: Receipt Command Schema):**
  ```python
  # server.py: Receipt Command Schema
  class ReceiptCmd(BaseModel):
      type: Literal["read", "received"]
      room: str
      ids: list[str] = Field(max_length=100)

      @field_validator("ids")
      @classmethod
      def validate_ids(cls, value: list[str]) -> list[str]:
          if any(not isinstance(i, str) for i in value):
              raise ValueError("Invalid read receipt.")
          return value
  ```
* **Code Snapshot 2 (Right: Receipt State Updates & Broadcast):**
  ```python
  # server.py: Updating Receipt Status Arrays & Broadcasting
  async def handle_receipt(self, session: UserSession, data: dict):
      cmd = ReceiptCmd(**data)
      room = self.authorized_room(session, cmd.room)
      receipt_field = "read_by" if cmd.type == "read" else "delivered_by"

      for message in room.messages:
          if (message["id"] in cmd.ids and session.id in room.members
                  and session.id != message["sender"]
                  and session.id not in message[receipt_field]):
              message[receipt_field].append(session.id)
              await self.broadcast({
                  "type": "receipt", "room": room.id, "id": message["id"],
                  "read_by": message["read_by"], "delivered_by": message["delivered_by"],
              }, room.members)
  ```
* **How It Works (Code & Flow):**
  1. Recipient browser receives message frame $\to$ sends `{"type": "received", "ids": [...]}`.
  2. Recipient views/focuses chat window $\to$ sends `{"type": "read", "ids": [...]}`.
  3. Server appends `session.id` to `delivered_by` / `read_by` and broadcasts live receipt event to room members.
* **Key Notes & Highlights:**
  * **3-Stage Lifecycle:** Real-time tracking from *Sent* $\to$ *Delivered* (double tick) $\to$ *Read* (viewed).
  * **Targeted Updates:** Receipt events are pushed strictly to participants of that specific room.

---

### Slide 20: Special Point 4: Automated Cloud Deployment
* **Description:** Production deployment on Oracle Cloud Infrastructure with automated Docker builds, Traefik TLS proxy, and GitHub Actions CI/CD.
* **Public Live URL:** [https://relay.161.118.238.148.sslip.io](https://relay.161.118.238.148.sslip.io)
* **Generative AI Prompt:**
  ```text
  "For Special Point 4: Write a GitHub Actions workflow and Docker Compose config with Traefik to auto-deploy the app to Oracle Cloud on git push."
  ```
* **Code Snapshot 1 (Left: Relay's Traefik Labels, excerpt):**
  ```yaml
  # compose.oracle.yml: Relay joins an existing Traefik network
  services:
    app:
      environment:
        PUBLIC_ORIGIN: https://${APP_DOMAIN:-relay.161.118.238.148.sslip.io}
      networks:
        - default
        - proxy
      labels:
        traefik.enable: "true"
        traefik.docker.network: eventory-production_default
        traefik.http.services.relay.loadbalancer.server.port: "8080"
        traefik.http.routers.relay.rule: Host(`${APP_DOMAIN:-relay.161.118.238.148.sslip.io}`)
        traefik.http.routers.relay.entrypoints: websecure
        traefik.http.routers.relay.tls: "true"
        traefik.http.routers.relay.tls.certresolver: letsencrypt
  networks:
    proxy:
      external: true
      name: eventory-production_default
  ```
* **Code Snapshot 2 (Right: Oracle Deployment Command):**
  ```bash
  # scripts/deploy.sh: reads both Compose files, then starts the image
  compose=(docker compose -f compose.yml -f compose.oracle.yml)
  export APP_IMAGE="$image"
  "${compose[@]}" pull app ollama model-pull
  "${compose[@]}" up -d --no-build --wait --wait-timeout 600
  curl --fail --silent --show-error --retry 5 --retry-delay 2 http://127.0.0.1:8080/healthz
  ```
* **How It Works (Code & Flow):**
  1. A code push to `main` (or a manual workflow run) builds an AMD64/ARM64 image and publishes it to GitHub Container Registry. Documentation-only pushes are ignored by this workflow.
  2. Actions connects to Oracle over SSH, transfers both Compose files and `deploy.sh`, and passes the GHCR token and `GEMINI_API_KEY` secret to the script over standard input.
  3. `deploy.sh` pulls the image, runs Compose with both files, checks local `/healthz`, and records the successful image for rollback. The workflow also checks public HTTPS `/healthz`.
* **Key Notes & Highlights:**
  * **Shared Proxy:** Relay does not start another Traefik container. It joins the existing `eventory-production_default` Docker network and supplies routing labels; that network belongs to a separate project.
  * **Public Name:** `relay.161.118.238.148.sslip.io` resolves to the Oracle server's IP without registering a domain. Traefik uses Let's Encrypt for HTTPS/WSS.

---

## Slide Preparation Outline (Slides 01 – 20)
This document provides material for the 20-slide presentation:
1. Requirements & Titles
2. Engineering-grade Generative AI Prompts
3. Two-Box Backend Code Snapshots (Left: Pydantic Schema / Right: Handler Execution)
4. Speaker Notes & Talking Points
