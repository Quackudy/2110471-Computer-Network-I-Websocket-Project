"""Real socket tests for the assignment's access boundaries and lifecycle."""

import base64
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestServer

from server import create_app


class ChatTests(AioHTTPTestCase):
    async def get_application(self):
        return create_app()

    async def user(self, name):
        socket = await self.client.ws_connect("/ws")
        await socket.send_json({"type": "register", "name": name})
        welcome = await self.event(socket, "welcome")
        return socket, welcome["id"]

    async def event(self, socket, kind):
        for _ in range(30):
            event = await socket.receive_json(timeout=3)
            if event["type"] == kind:
                return event
            if kind == "error" and event["type"] in {"message", "room", "summary"}:
                self.fail(f"Unexpected private delivery: {event['type']}")
        self.fail(f"No {kind} event received")

    async def private(self, alice, bob, bob_id):
        await alice.send_json({"type": "open_private", "peer": bob_id})
        room = (await self.event(alice, "room"))["room"]
        await self.event(bob, "room")
        return room["id"]

    async def test_unique_names_presence_and_disconnect(self):
        alice, alice_id = await self.user("Alice")
        presence = await self.event(alice, "state")
        self.assertEqual(presence["users"], [{"id": alice_id, "name": "Alice"}])
        duplicate = await self.client.ws_connect("/ws")
        await duplicate.send_json({"type": "register", "name": " alice "})
        self.assertIn("already", (await self.event(duplicate, "error"))["message"])
        bob, bob_id = await self.user("Bob")
        presence = await self.event(alice, "state")
        self.assertEqual({u["id"] for u in presence["users"]}, {alice_id, bob_id})
        await bob.close()
        presence = await self.event(alice, "state")
        self.assertEqual(len(presence["users"]), 1)
        replacement, _ = await self.user("Bob")
        await replacement.close()
        await duplicate.close()
        await alice.close()

    async def test_private_messages_files_receipts_and_room_isolation(self):
        alice, alice_id = await self.user("Alice")
        bob, bob_id = await self.user("Bob")
        eve, _ = await self.user("Eve")
        room = await self.private(alice, bob, bob_id)
        await alice.send_json({"type": "message", "room": room, "text": "secret", "sender": "forged"})
        delivered = (await self.event(bob, "message"))["message"]
        self.assertEqual(delivered["sender"], alice_id)
        self.assertEqual(delivered["text"], "secret")
        self.assertEqual((await self.event(alice, "message"))["message"]["id"], delivered["id"])
        await bob.send_json({"type": "received", "room": room, "ids": [delivered["id"]]})
        self.assertEqual((await self.event(alice, "receipt"))["delivered_by"], [bob_id])
        await eve.send_json({"type": "message", "room": room, "text": "intrusion"})
        self.assertEqual((await self.event(eve, "error"))["type"], "error")
        await bob.send_json({"type": "read", "room": room, "ids": [delivered["id"]]})
        self.assertEqual((await self.event(alice, "receipt"))["read_by"], [bob_id])
        payload = base64.b64encode(b"project notes\x00").decode()
        await bob.send_json({"type": "file", "room": room, "filename": "notes.txt", "data": payload})
        file = (await self.event(alice, "message"))["message"]
        self.assertEqual(base64.b64decode(file["data"]), b"project notes\x00")
        self.assertEqual(file["bytes"], 14)
        await self.event(bob, "message")
        await alice.send_json({"type": "open_private", "peer": bob_id})
        self.assertEqual(len((await self.event(alice, "room"))["messages"]), 2)
        await self.event(bob, "room")
        await eve.send_json({"type": "summarize", "room": room})
        self.assertEqual((await self.event(eve, "error"))["type"], "error")
        await bob.close()
        await self.event(alice, "state")
        await alice.send_json({"type": "message", "room": room, "text": "offline"})
        self.assertIn("disconnected", (await self.event(alice, "error"))["message"])
        await alice.close()
        await eve.close()

    async def test_groups_self_join_and_no_prejoin_history(self):
        alice, alice_id = await self.user("Alice")
        bob, bob_id = await self.user("Bob")
        eve, eve_id = await self.user("Eve")
        await alice.send_json({"type": "create_group", "name": "Team"})
        group = (await self.event(alice, "room"))["room"]
        self.assertEqual(group["members"], [{"id": alice_id, "name": "Alice"}])
        state = await self.event(bob, "state")
        while not state["groups"]:
            state = await self.event(bob, "state")
        self.assertEqual(state["groups"][0]["name"], "Team")
        await alice.send_json({"type": "message", "room": group["id"], "text": "before join"})
        await self.event(alice, "message")
        await bob.send_json({"type": "message", "room": group["id"], "text": "not a member"})
        await self.event(bob, "error")
        await bob.send_json({"type": "join_group", "room": group["id"]})
        joined = await self.event(bob, "room")
        self.assertEqual(joined["messages"], [])
        self.assertEqual({m["id"] for m in joined["room"]["members"]}, {alice_id, bob_id})
        await bob.send_json({"type": "message", "room": group["id"], "text": "members only"})
        self.assertEqual((await self.event(alice, "message"))["message"]["text"], "members only")
        await self.event(bob, "message")
        # A forbidden command gives a boundary in Eve's queue: no prior room/message deliveries.
        await eve.send_json({"type": "read", "room": group["id"], "ids": []})
        await self.event(eve, "error")
        await eve.send_json({"type": "join_group", "room": group["id"]})
        self.assertEqual((await self.event(eve, "room"))["messages"], [])
        await eve.close()
        await bob.close()
        await alice.close()

    async def test_validation_origin_and_file_limits(self):
        response = await self.client.get("/healthz")
        self.assertEqual((await response.json())["status"], "ok")
        with self.assertRaises(Exception) as rejected:
            await self.client.ws_connect("/ws", headers={"Origin": "https://evil.example"})
        self.assertEqual(rejected.exception.status, 403)
        alice, _ = await self.user("Alice")
        bob, bob_id = await self.user("Bob")
        room = await self.private(alice, bob, bob_id)
        for event in [
            {"type": "message", "room": room, "text": " "},
            {"type": "message", "room": room, "text": "x" * 4001},
            {"type": "file", "room": room, "filename": "../bad", "data": "eA=="},
            {"type": "file", "room": room, "filename": "bad", "data": "!not base64!"},
            {"type": "file", "room": room, "filename": "huge", "data": "x" * 350000},
            {"type": "read", "room": room, "ids": [None]},
            {"type": "message", "room": {}, "text": "invalid room"},
        ]:
            await alice.send_json(event)
            await self.event(alice, "error")
        await alice.send_str("{invalid")
        await self.event(alice, "error")
        await alice.send_json({"type": "message", "room": room, "text": "still works"})
        self.assertEqual((await self.event(bob, "message"))["message"]["text"], "still works")
        await alice.close()
        await bob.close()

    async def test_ai_gets_only_authorized_history_and_reports_errors(self):
        requests = []

        async def model(request):
            requests.append(await request.json())
            if len(requests) > 1:
                return web.json_response({"error": "offline"}, status=503)
            return web.json_response({"message": {"content": "- Meet at noon."}})

        mock_app = web.Application()
        mock_app.router.add_post("/api/chat", model)
        async with TestServer(mock_app) as ai:
            with patch("server.AI_URL", str(ai.make_url("")).rstrip("/")):
                alice, _ = await self.user("Alice")
                bob, bob_id = await self.user("Bob")
                room = await self.private(alice, bob, bob_id)
                await alice.send_json({"type": "message", "room": room, "text": "Meet at noon."})
                await self.event(alice, "message")
                await alice.send_json({"type": "summarize", "room": room})
                await self.event(alice, "summary_pending")
                self.assertEqual((await self.event(alice, "summary"))["text"], "- Meet at noon.")
                self.assertIn("Alice: Meet at noon.", requests[0]["messages"][1]["content"])
                await alice.send_json({"type": "summarize", "room": room})
                self.assertIn("unavailable", (await self.event(alice, "summary_error"))["message"])
                await alice.close()
                await bob.close()

    async def test_bounded_history_and_empty_summary(self):
        alice, _ = await self.user("Alice")
        await alice.send_json({"type": "create_group", "name": "Archive"})
        room_id = (await self.event(alice, "room"))["room"]["id"]
        await alice.send_json({"type": "summarize", "room": room_id})
        self.assertIn("text messages", (await self.event(alice, "error"))["message"])
        from server import CHAT_KEY
        chat = self.app[CHAT_KEY]
        room = chat.rooms[room_id]
        for n in range(120):
            chat.retain(room, {"id": str(n), "text": "x" * 100, "audience": set()})
        self.assertEqual(len(room.messages), 100)
        self.assertEqual(room.messages[0]["id"], "20")
        with patch("server.MAX_HISTORY_BYTES", 500):
            chat.retain(room, {"id": "last", "text": "last", "audience": set()})
        self.assertLessEqual(chat.history_bytes, 500)
        await alice.close()


if __name__ == "__main__":
    unittest.main()
