import unittest
from unittest.mock import patch

import server


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def json(self):
        return self.body


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return FakeResponse(*next(self.responses))


class SummaryTests(unittest.IsolatedAsyncioTestCase):
    async def check_summary(self, key, provider, responses, expected_urls, expected_model, expected_text):
        client = FakeClient(responses)
        events = []
        chat = server.ChatServer()

        async def capture(_session, event):
            events.append(event)

        with patch.object(server, "GEMINI_API_KEY", key), patch.object(server, "GEMINI_MODEL", "gemini-test"), \
             patch.object(server, "OLLAMA_MODEL", "qwen-test"), \
             patch.object(server, "HttpClient", return_value=client), patch.object(chat, "send", capture):
            await chat.execute_summarize(object(), "room-1", ["Alex: hello"], provider)

        self.assertEqual(events[-1]["type"], "summary")
        self.assertEqual(events[-1]["text"], expected_text)
        self.assertEqual(events[-1]["model"], expected_model)
        self.assertEqual(len(client.requests), len(expected_urls))
        for (url, options), expected_url in zip(client.requests, expected_urls):
            self.assertIn(expected_url, url)
            self.assertIn("Alex: hello", str(options["json"]))
        self.assertEqual(client.requests[0][1]["headers"].get("x-goog-api-key"), key if expected_urls[0] == ":generateContent" else None)

    async def test_gemini(self):
        await self.check_summary("secret", "gemini", [(200, {"candidates": [{"content": {"parts": [{"text": "Better summary"}]}}]})],
                                 [":generateContent"], "gemini-test", "Better summary")

    async def test_selected_ollama(self):
        await self.check_summary("secret", "ollama", [(200, {"message": {"content": "Local summary"}})],
                                 ["/api/chat"], "qwen-test", "Local summary")

    async def test_gemini_failure_falls_back_to_ollama(self):
        await self.check_summary("secret", "gemini", [(503, {}), (200, {"message": {"content": "Fallback summary"}})],
                                 [":generateContent", "/api/chat"], "qwen-test", "Fallback summary")


if __name__ == "__main__":
    unittest.main()
