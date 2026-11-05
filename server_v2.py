"""
Relay Chat Server (Version 2 - Clean Architecture with Pydantic & Dispatcher)
Step 3: Private Rooms (R5, R6) and Direct Messaging (R7)
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from aiohttp import WSMsgType, web
from pydantic import BaseModel, Field, ValidationError, field_validator

STATIC_DIR = Path(__file__).parent / "static"
MAX_FILE = 256 * 1024
MAX_HISTORY_BYTES = 32 * 1024 * 1024
AI_MODEL = os.getenv("AI_MODEL", "qwen2.5:0.5b")
NAME_PATTERN = re.compile(r"^[\w .-]{1,24}$", re.UNICODE)


# ==============================================================================
# 1. Pydantic Command Models (Validation Layer)
# ==============================================================================

class RegisterCmd(BaseModel):
    """Validates user registration payload (R3)."""
    type: Literal["register"] = "register"
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not (1 <= len(trimmed) <= 24) or not NAME_PATTERN.fullmatch(trimmed):
            raise ValueError("Use 1–24 letters, numbers, spaces, dots, underscores or hyphens.")
        return trimmed


class OpenPrivateCmd(BaseModel):
    """Validates opening a private 1-on-1 conversation (R5)."""
    type: Literal["open_private"] = "open_private"
    peer: str


class MessageCmd(BaseModel):
    """Validates text message sending (R6, R7)."""
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


# ==============================================================================
# 2. Core Data Models
# ==============================================================================

@dataclass
class UserSession:
    """Represents an active client WebSocket connection."""
    socket: web.WebSocketResponse
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    requests: deque = field(default_factory=deque)  # For sliding-window rate limiting


@dataclass
class ChatRoom:
    """Represents a private or group chat room."""
    id: str
    kind: Literal["private", "group"]
    name: str
    members: set[str]  # Stores session.id of participants
    names: dict[str, str] = field(default_factory=dict)  # session.id -> display name
    messages: deque = field(default_factory=deque)


# ==============================================================================
# 3. Central Chat Server & Dispatcher
# ==============================================================================

class ChatServer:
    """Manages connected clients, rooms, and routes WebSocket commands."""

    def __init__(self):
        self.sessions: dict[str, UserSession] = {}
        self.rooms: dict[str, ChatRoom] = {}
        self.history_bytes = 0
        self.sequence = 0
        
        # Dispatch table: command "type" -> handler function
        self.handlers: dict[str, Callable] = {
            "register": self.handle_register,
            "open_private": self.handle_open_private,
            "message": self.handle_message,
        }

    async def send(self, session: UserSession, event: dict):
        """Send a JSON frame safely to a single client socket."""
        try:
            await asyncio.wait_for(session.socket.send_json(event), timeout=5.0)
        except (ConnectionError, RuntimeError, asyncio.TimeoutError):
            asyncio.create_task(session.socket.close())

    async def broadcast(self, event: dict, members: set[str] | None = None):
        """Broadcast a JSON frame to all users or an authorized subset of members."""
        targets = [
            s for s in self.sessions.values()
            if members is None or s.id in members
        ]
        await asyncio.gather(*(self.send(s, event) for s in targets))

    def describe_room(self, room: ChatRoom) -> dict:
        """Helper to serialize a room description for client state."""
        return {
            "id": room.id,
            "kind": room.kind,
            "name": room.name,
            "members": [
                {"id": mid, "name": room.names.get(mid, "")}
                for mid in sorted(room.members)
            ],
        }

    @staticmethod
    def wire_message(message: dict) -> dict:
        """Strip internal server metadata (audience, size) before wire delivery."""
        return {k: v for k, v in message.items() if k not in {"audience", "size", "sequence"}}

    def authorized_room(self, session: UserSession, data: dict) -> ChatRoom:
        """Verify the room exists and the session is an authorized participant."""
        room_id = data.get("room")
        room = self.rooms.get(room_id) if isinstance(room_id, str) else None
        if room is None or session.id not in room.members:
            raise ValueError("Join this room before using it.")
        return room

    async def open_room(self, session: UserSession, room: ChatRoom):
        """Deliver room metadata and authorized historical messages to a client."""
        await self.send(session, {
            "type": "room",
            "room": self.describe_room(room),
            "messages": [
                self.wire_message(m) for m in room.messages
                if session.id in m["audience"]
            ],
        })

    def retain(self, room: ChatRoom, message: dict):
        """Retain message in memory buffer with 32 MB upper bound."""
        self.sequence += 1
        message["sequence"] = self.sequence
        message["size"] = len(json.dumps(self.wire_message(message)).encode())

        if len(room.messages) >= 100:
            self.history_bytes -= room.messages.popleft()["size"]
        room.messages.append(message)
        self.history_bytes += message["size"]

        while self.history_bytes > MAX_HISTORY_BYTES:
            oldest = min(
                (r for r in self.rooms.values() if r.messages),
                key=lambda r: r.messages[0]["sequence"]
            )
            self.history_bytes -= oldest.messages.popleft()["size"]

    async def broadcast_presence(self):
        """Broadcast online users and active groups to all connected clients (R4)."""
        await self.broadcast({
            "type": "state",
            "users": [{"id": s.id, "name": s.name} for s in self.sessions.values() if s.name],
            "groups": [self.describe_room(r) for r in self.rooms.values() if r.kind == "group"],
        })

    # --------------------------------------------------------------------------
    # Handlers
    # --------------------------------------------------------------------------

    async def handle_register(self, session: UserSession, data: dict):
        """R3: Validate and register unique client name."""
        cmd = RegisterCmd(**data)

        if any(s.name.casefold() == cmd.name.casefold() for s in self.sessions.values()):
            raise ValueError("That name is already connected. Choose another.")

        if len(self.sessions) >= 100:
            raise ValueError("The server is full. Try again later.")

        session.name = cmd.name
        
        await self.send(session, {
            "type": "welcome",
            "id": session.id,
            "name": session.name,
            "ai_model": AI_MODEL,
            "max_file": MAX_FILE,
        })
        await self.broadcast_presence()

    async def handle_open_private(self, session: UserSession, data: dict):
        """R5: Open or create an isolated private chat room for two participants."""
        cmd = OpenPrivateCmd(**data)
        peer = self.sessions.get(cmd.peer)
        if peer is None or peer.id == session.id:
            raise ValueError("Choose another online user.")

        members = {session.id, peer.id}
        room = next((r for r in self.rooms.values()
                     if r.kind == "private" and r.members == members), None)
        if room is None:
            if len(self.rooms) >= 100:
                raise ValueError("Room limit reached.")
            room = ChatRoom(
                id=uuid.uuid4().hex,
                kind="private",
                name="Private conversation",
                members=members,
                names={s.id: s.name for s in [session, peer]}
            )
            self.rooms[room.id] = room

        await asyncio.gather(*(self.open_room(s, room) for s in [session, peer]))

    async def handle_message(self, session: UserSession, data: dict):
        """R7: Deliver text message strictly to room members."""
        room = self.authorized_room(session, data)
        if room.kind == "private" and not room.members <= self.sessions.keys():
            raise ValueError("This user disconnected. Open a new chat when they return.")

        cmd = MessageCmd(**data)
        message = {
            "id": uuid.uuid4().hex,
            "room": room.id,
            "sender": session.id,
            "name": session.name,
            "timestamp": time.time(),
            "kind": "message",
            "text": cmd.text,
            "audience": set(room.members),
            "read_by": [],
            "delivered_by": [],
        }

        self.retain(room, message)
        # R7: Delivered strictly to room.members (only sender and receiver)
        await self.broadcast(
            {"type": "message", "message": self.wire_message(message)},
            room.members
        )

    # --------------------------------------------------------------------------
    # Dispatcher Loop
    # --------------------------------------------------------------------------

    async def dispatch(self, session: UserSession, raw_text: str):
        """Central entry point: rate-limit, parse JSON, validate, and route."""
        try:
            now = time.monotonic()
            while session.requests and session.requests[0] < now - 1.0:
                session.requests.popleft()
            if len(session.requests) >= 20:
                raise ValueError("Too many requests. Please slow down.")
            session.requests.append(now)

            data = json.loads(raw_text)
            if not isinstance(data, dict):
                raise ValueError("Payload must be a JSON object.")

            action = data.get("type")
            if not isinstance(action, str):
                raise ValueError("Send a JSON object with a command type.")

            if not session.name and action != "register":
                raise ValueError("Choose a name first.")

            handler = self.handlers.get(action)
            if not handler:
                raise ValueError("Unknown command.")

            await handler(session, data)

        except (ValidationError, ValueError) as err:
            if isinstance(err, ValidationError):
                msg = err.errors()[0]["msg"].removeprefix("Value error, ")
            else:
                msg = str(err)
            await self.send(session, {"type": "error", "message": msg})

    async def disconnect(self, session: UserSession):
        """Clean up session on disconnect, purge abandoned private rooms, and update presence."""
        if self.sessions.pop(session.id, None) is None:
            return

        for room_id, room in list(self.rooms.items()):
            if room.kind == "group":
                room.members.discard(session.id)
                room.names.pop(session.id, None)
            # Private rooms retain history until BOTH participants disconnect
            if room.kind == "private" and not room.members & self.sessions.keys():
                self.history_bytes -= sum(m["size"] for m in room.messages)
                del self.rooms[room_id]

        if session.name:
            await self.broadcast_presence()


# ==============================================================================
# 4. HTTP & WebSocket Transport Layer (R2)
# ==============================================================================

async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """Single persistent WebSocket endpoint (/ws) for all chat interactions."""
    server: ChatServer = request.app["chat_server"]
    socket = web.WebSocketResponse(heartbeat=30.0, max_msg_size=400_000)
    await socket.prepare(request)

    session = UserSession(socket=socket)
    server.sessions[session.id] = session

    try:
        async for msg in socket:
            if msg.type == WSMsgType.TEXT:
                await server.dispatch(session, msg.data)
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        await server.disconnect(session)

    return socket


def create_app() -> web.Application:
    """Create the aiohttp application with static HTTP routes and the /ws socket endpoint."""
    server = ChatServer()
    app = web.Application()
    app["chat_server"] = server

    app.router.add_get("/ws", ws_handler)

    async def health(request):
        return web.json_response({"status": "ok"})

    async def serve_static(request):
        filename = request.match_info.get("filename", "index.html")
        file_path = STATIC_DIR / filename
        if not file_path.exists():
            raise web.HTTPNotFound()
        return web.FileResponse(file_path)

    app.router.add_get("/healthz", health)
    app.router.add_get("/", serve_static)
    app.router.add_get("/{filename}", serve_static)

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
