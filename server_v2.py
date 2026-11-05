"""
Relay Chat Server (Version 2 - Clean Architecture with Pydantic & Dispatcher)
Step 1: Foundation, Data Models, and Single WebSocket Endpoint (R2)
"""

import asyncio
import json
import logging
import os
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from aiohttp import WSMsgType, web
from pydantic import BaseModel, ValidationError

STATIC_DIR = Path(__file__).parent / "static"


# ==============================================================================
# 1. Core Data Models
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
# 2. Central Chat Server & Dispatcher
# ==============================================================================

class ChatServer:
    """Manages connected clients, rooms, and routes WebSocket commands."""

    def __init__(self):
        self.sessions: dict[str, UserSession] = {}
        self.rooms: dict[str, ChatRoom] = {}
        
        # Dispatch table: command "type" -> handler function
        # Handlers will be populated progressively in upcoming steps
        self.handlers: dict[str, Callable] = {}

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

    async def dispatch(self, session: UserSession, raw_text: str):
        """Central entry point: parse JSON, validate, and route to specific handlers."""
        try:
            data = json.loads(raw_text)
            if not isinstance(data, dict):
                raise ValueError("Payload must be a JSON object.")

            action = data.get("type")
            handler = self.handlers.get(action)
            if not handler:
                raise ValueError("Unknown command.")

            # Route to the registered handler (which validates using Pydantic)
            await handler(session, data)

        except (ValidationError, ValueError) as err:
            # Format clean error message and send directly to client
            msg = err.errors()[0]["msg"] if isinstance(err, ValidationError) else str(err)
            await self.send(session, {"type": "error", "message": msg})

    async def disconnect(self, session: UserSession):
        """Clean up when a client disconnects."""
        self.sessions.pop(session.id, None)


# ==============================================================================
# 3. HTTP & WebSocket Transport Layer (R2)
# ==============================================================================

async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """Single persistent WebSocket endpoint (/ws) for all chat interactions."""
    server: ChatServer = request.app["chat_server"]
    socket = web.WebSocketResponse(heartbeat=30.0)
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

    # 1. Single WebSocket endpoint for all chat messaging (R2)
    app.router.add_get("/ws", ws_handler)

    # 2. HTTP endpoints for static assets and health check
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
