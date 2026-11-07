import unittest
from unittest.mock import patch

import server


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def json(self):
        return self.body


class FakeClient:
    def __init__(self, body):
        self.body = body
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return FakeResponse(self.body)


class SummaryTests(unittest.IsolatedAsyncioTestCase):
    async def check_summary(self, key, body, expected_url, expected_text):
        client = FakeClient(body)
        events = []
        chat = server.ChatServer()

        async def capture(_session, event):
            events.append(event)

        with patch.object(server, "GEMINI_API_KEY", key), patch.object(server, "AI_MODEL", "test-model"), \
             patch.object(server, "HttpClient", return_value=client), patch.object(chat, "send", capture):
            await chat.execute_summarize(object(), "room-1", ["Alex: hello"])

        self.assertEqual(events[-1]["type"], "summary")
        self.assertEqual(events[-1]["text"], expected_text)
        url, options = client.request
        self.assertIn(expected_url, url)
        self.assertEqual(options["headers"].get("x-goog-api-key"), key or None)
        self.assertIn("Alex: hello", str(options["json"]))

    async def test_gemini(self):
        await self.check_summary("secret", {"candidates": [{"content": {"parts": [{"text": "Better summary"}]}}]},
                                 ":generateContent", "Better summary")

    async def test_ollama_fallback(self):
        await self.check_summary("", {"message": {"content": "Local summary"}}, "/api/chat", "Local summary")


if __name__ == "__main__":
    unittest.main()
