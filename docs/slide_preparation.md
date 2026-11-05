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

*(Slides R5 through Special 4 will be populated in the next steps)*
