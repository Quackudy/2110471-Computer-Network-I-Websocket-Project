"""Three independent browser clients exercise the real UI and socket server."""
import argparse
import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright, expect


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?", default="http://127.0.0.1:8080")
    parser.add_argument("--ai", action="store_true", help="Require a working live model")
    args = parser.parse_args()
    errors = []
    async with async_playwright() as playwright:
        options = {"headless": True}
        if os.getenv("CHROMIUM_PATH"):
            options["executable_path"] = os.environ["CHROMIUM_PATH"]
        browser = await playwright.chromium.launch(**options)
        contexts = [await browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
                    for _ in range(3)]
        pages = [await context.new_page() for context in contexts]
        alice, bob, eve = pages
        # Use run-specific names when testing a shared live server.
        import secrets
        suffix = secrets.token_hex(2)
        names = [f"Alex-{suffix}", f"Sam-{suffix}", f"Jamie-{suffix}"]
        for page, name in zip(pages, names):
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(args.url)
            await page.locator("#name-input").fill(name)
            await page.locator("#login-form").get_by_role("button").click()
            await expect(page.locator("#login-dialog")).not_to_be_visible()
        await expect(alice.locator("#users")).to_contain_text(names[2])
        await alice.locator("#users button").filter(has_text=names[1]).click()
        await expect(alice.locator("#room-name")).to_have_text(names[1])
        await alice.locator("#message-input").fill("Meet at noon. Bring the project slides. <script>alert(1)</script>")
        await alice.locator("#composer").get_by_role("button", name="Send message").click()
        await expect(bob.locator("#messages")).to_contain_text("Meet at noon.")
        await expect(bob.locator("#messages script")).to_have_count(0)
        await expect(eve.locator("#chat")).not_to_be_visible()
        await bob.bring_to_front()
        await expect(alice.locator("#messages")).to_contain_text("Read")
        await bob.locator("#message-input").fill("Agreed. I will prepare the diagram.")
        await bob.locator("#composer").get_by_role("button", name="Send message").click()
        await expect(alice.locator("#messages")).to_contain_text("prepare the diagram")
        await alice.locator("#search").fill("diagram")
        await expect(alice.locator(".message-row")).to_have_count(1)
        await alice.locator("#search").fill("")

        await bob.locator("#file-input").set_input_files({"name": "notes.txt", "mimeType": "text/plain", "buffer": b"Meet at noon.\n"})
        await expect(alice.locator("#messages")).to_contain_text("notes.txt")
        async with alice.expect_download() as download_info:
            await alice.locator(".file-download").click()
        download = await download_info.value
        assert download.suggested_filename == "notes.txt"
        assert Path(await download.path()).read_bytes() == b"Meet at noon.\n"

        if args.ai:
            await alice.locator("#summarize").click()
            await expect(alice.locator("#summary-model")).to_contain_text("qwen2.5", timeout=130000)
            assert len((await alice.locator("#summary-text").inner_text()).strip()) > 10
            await expect(bob.locator("#summary-card")).not_to_be_visible()

        group_name = f"Project room {suffix}"
        await alice.locator("#new-group").click()
        await alice.locator("#group-input").fill(group_name)
        await alice.locator("#group-form").get_by_role("button", name="Create room").click()
        await expect(alice.locator("#room-name")).to_have_text(group_name)
        await expect(alice.locator("#room-members")).not_to_contain_text(names[1])
        await alice.locator("#message-input").fill("Before anyone joins.")
        await alice.locator("#composer").get_by_role("button", name="Send message").click()
        group = bob.locator("#groups button").filter(has_text=group_name)
        await expect(group).to_contain_text("Join")
        await group.click()
        await expect(bob.locator("#room-name")).to_have_text(group_name)
        await expect(bob.locator("#messages")).not_to_contain_text("Before anyone joins.")
        await bob.locator("#message-input").fill("Now we are both here.")
        await bob.locator("#composer").get_by_role("button", name="Send message").click()
        await expect(alice.locator("#messages")).to_contain_text("Now we are both here.")
        await expect(eve.locator("#chat")).not_to_be_visible()
        await expect(eve.locator("#groups button").filter(has_text=group_name)).to_contain_text("Join")
        await bob.locator("#disconnect").click()
        await expect(bob.locator("#login-dialog")).to_be_visible()
        await expect(alice.locator("#room-members")).not_to_contain_text(names[1])

        output = Path("test-results")
        output.mkdir(exist_ok=True)
        await alice.screenshot(path=str(output / "chat-desktop.png"))
        await eve.screenshot(path=str(output / "welcome-desktop.png"))
        await alice.set_viewport_size({"width": 390, "height": 844})
        await alice.screenshot(path=str(output / "chat-mobile.png"))
        assert await alice.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile layout overflows"
        await alice.locator("#toggle-sidebar").click()
        await expect(alice.locator(".sidebar")).to_be_visible()
        await contexts[0].close()
        await contexts[1].close()
        await contexts[2].close()
        await browser.close()
    assert not errors, errors
    print("PASS: three clients, private/group privacy, XSS escaping, receipts, files, search, disconnects, mobile" + (", live AI" if args.ai else ""))


if __name__ == "__main__":
    asyncio.run(main())
