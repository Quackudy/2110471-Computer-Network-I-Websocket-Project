"""
Relay Chat Server (Version 2 - Clean Architecture with Pydantic & Dispatcher)
Step 2: Client Registration (R3) & Presence Broadcast (R4)
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
from pydantic import BaseModel, ValidationError, field_validator

STATIC_DIR = Path(__file__).parent / "static"
MAX_FILE = 256 * 1024
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
        
        # Dispatch table: command "type" -> handler function
        self.handlers: dict[str, Callable] = {
            "register": self.handle_register,
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

        # Uniqueness check (case-insensitive) across active sessions
        if any(s.name.casefold() == cmd.name.casefold() for s in self.sessions.values()):
            raise ValueError("That name is already connected. Choose another.")

        if len(self.sessions) >= 100:
            raise ValueError("The server is full. Try again later.")

        session.name = cmd.name
        
        # Welcome current user with assigned session ID
        await self.send(session, {
            "type": "welcome",
            "id": session.id,
            "name": session.name,
            "ai_model": AI_MODEL,
            "max_file": MAX_FILE,
        })

        # Broadcast updated presence to everyone including this client (R4)
        await self.broadcast_presence()

    # --------------------------------------------------------------------------
    # Dispatcher Loop
    # --------------------------------------------------------------------------

    async def dispatch(self, session: UserSession, raw_text: str):
        """Central entry point: rate-limit, parse JSON, validate, and route."""
        try:
            # Rate limiting (max 20 requests per second)
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

            # Must register a name before running any other chat command
            if not session.name and action != "register":
                raise ValueError("Choose a name first.")

            handler = self.handlers.get(action)
            if not handler:
                raise ValueError("Unknown command.")

            # Route to handler
            await handler(session, data)

        except (ValidationError, ValueError) as err:
            # Clean up error message formatting for client
            if isinstance(err, ValidationError):
                msg = err.errors()[0]["msg"].removeprefix("Value error, ")
            else:
                msg = str(err)
            await self.send(session, {"type": "error", "message": msg})

    async def disconnect(self, session: UserSession):
        """Clean up session on disconnect and broadcast updated presence."""
        if self.sessions.pop(session.id, None) is not None:
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
