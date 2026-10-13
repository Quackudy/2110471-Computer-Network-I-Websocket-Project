"""Build the supplied 20-slide explanation structure from the real source."""
from html import escape
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]
slides = []


def code(filename, marker, count=14):
    lines = (ROOT / filename).read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if marker in line)
    excerpt = dedent("\n".join(lines[start:start + count]))
    return f'<div class="source">Code snapshot · {escape(filename)} · line {start + 1}</div><pre><code>{escape(excerpt)}</code></pre>'


def slide(title, body, tag="IMPLEMENTATION EXPLANATION", prompt=False):
    disclosure = '<div class="prompt">Generative AI prompt: shared project request disclosed on slide 1. Code generated with Codex, then checked with socket and browser tests.</div>' if prompt else ""
    slides.append(f'<section class="slide"><div class="tag">{tag}</div><h1>{title}</h1>{body}{disclosure}<footer><span>Relay · 2110471 Computer Network I</span><span>{len(slides) + 1:02d} / 20</span></footer></section>')


slide("Socket Programming<br><em>A little closer, with Relay.</em>", '''
<p class="lead">A browser chat application with private rooms, voluntary group chats and local AI summaries.</p>
<p><strong>Group:</strong> [add group number]<br><strong>Members:</strong> [add student IDs and names]</p>
<div class="note">Generative AI disclosure — actual user prompts, excerpts with credential details omitted:<br>
“read all the pdf file and plan what to do”<br>“yes do it … pls use this github … for this project. you can create github workflow to auto deploy to my oracle server … push image to github registry and let server pull”<br>“Browser app with WebSockets”<br>
These requests authorized the R1–R11 implementation and extras in the preceding plan. No separate per-feature user prompts were supplied. Runtime summary instructions are in <code>server.py</code>.</div>''', "TERM PROJECT")

slide("Part 1<br><em>System architecture.</em>", '<p class="lead">1.5 points · Complete this part before Part 2 can be graded.</p><p>R1: two physical client computers, architecture and protocol explanation.<br>R2: socket programming for all chat messages.</p>')

slide("R1 · System architecture", '''
<div class="architecture"><div class="stack"><div class="box">Browser A<small>Physical computer 1</small></div><div class="box">Browser B<small>Physical computer 2</small></div></div><div class="arrow">⇄<small>HTTPS / WSS<br>TCP 443</small></div><div class="box">Traefik<small>Oracle TLS proxy</small></div><div class="arrow">⇄<small>WebSocket<br>TCP 8080</small></div><div class="box">Python server<small>161.118.238.148<br>ARM64 Docker</small></div></div>
<div class="ai-row">Python server → internal HTTP / TCP 11434 → Ollama / Qwen2.5 (no public port)</div>
<p>Server and browser client are separate files. The Oracle server runs the central room/membership state and routes messages only to authorized participants.</p>
<div class="note">Demonstrate with two different physical computers. Three browser sessions are automated checks; they do not replace this physical-computer requirement.</div>''')

slide("R1 · Protocol choices", '''
<table><tr><th>Protocol</th><th>Why and how</th></tr>
<tr><td>IP + TCP</td><td>Route data between hosts; provide a reliable, ordered transport.</td></tr>
<tr><td>HTTPS</td><td>Serve the browser client and establish the WebSocket upgrade handshake.</td></tr>
<tr><td>WebSocket / WSS</td><td>Persistent, bidirectional framed messages. Every chat command and delivery uses /ws.</td></tr>
<tr><td>JSON</td><td>Application event format inside WebSocket frames, including room IDs and message bodies.</td></tr>
<tr><td>TLS</td><td>Encrypt browser-to-proxy traffic; internal socket traffic stays on the Docker network.</td></tr>
<tr><td>SSH + HTTPS registry</td><td>Authenticated deployment connection and pulling the container image from GHCR.</td></tr>
<tr><td>Internal HTTP</td><td>Request AI inference from Ollama; it is not the client chat transport.</td></tr></table>''')

slide("R2 · Socket-only chat transport", '<p>HTTP serves static files and health checks. Native browser WebSocket sends registration, room commands, text and files through the same persistent connection.</p>' + code("static/app.js", 'function connect(name)', 10) + code("server.py", 'socket = web.WebSocketResponse', 7), prompt=True)

slide("Part 2<br><em>The complete chat.</em>", '<p class="lead">7 points · Complete R3–R11 before bonus features can be graded.</p><p>Names and presence → private rooms → explicit group membership → member-only routing.</p>')

slide("R3 · Unique client names", '<p>Names are validated and compared case-insensitively. The server assigns a session ID and reserves the name until disconnect.</p>' + code("server.py", 'name = data.get("name")', 16) + '<div class="note">Demo: connect Alice, then try “alice” from another client. The second registration must fail.</div>', prompt=True)

slide("R4 · Everyone currently online", '<p>Registration and disconnect broadcast fresh presence to every connected client. The list includes the current user.</p>' + code("server.py", 'async def presence', 9) + code("static/app.js", 'function renderNav', 8), prompt=True)

slide("R5 · Independent chat rooms", '<p>Private rooms belong to a unique participant pair. Group rooms receive separate IDs. The client keeps a separate message list and draft for each room.</p>' + code("server.py", 'members = {client.id, peer.id}', 11) + code("static/app.js", 'function activate', 7), prompt=True)

slide("R6 · Chat window and input", '<div class="columns"><div><p>Each selected room has its own message log and composer. New messages appear live; sending uses a WebSocket command.</p>' + code("static/app.js", '$("composer").addEventListener', 3) + '<p>Enter sends; Shift + Enter inserts a new line. User text is rendered with <code>textContent</code>, so HTML remains text.</p></div><img class="phone" src="images/chat-mobile.png" alt="Actual mobile chat screenshot"></div>', prompt=True)

slide("R7 · Sender and recipient only", '<p>The server derives the sender from the socket session, checks room membership, and delivers only to the room’s members. A third client cannot send, read or summarize this private room.</p>' + code("server.py", 'def authorized_room', 7) + code("server.py", 'self.retain(room, message)', 2) + '<div class="note">Demo: three clients; send Alice → Bob while showing that the third client receives nothing.</div>', prompt=True)

slide("R8 · Creator starts alone", '<p>Creating a group establishes exactly one member: the requesting client. The creator cannot automatically add other users.</p>' + code("server.py", 'elif action == "create_group"', 12), prompt=True)

slide("R9 · Browse all groups and members", '<p>Presence includes all existing groups. Every client sees the current member list even before joining; message contents remain restricted.</p>' + code("server.py", '"groups": [self.describe', 2) + code("static/app.js", 'for (const group of state.groups)', 13), prompt=True)

slide("R10 · Join by your own choice", '<p>The Join button sends a join request on the user’s own socket. The server adds only that socket’s identity. No command accepts a different user to add.</p>' + code("server.py", 'elif action == "join_group"', 11) + '<div class="note">A joining client does not receive messages sent before they were a member.</div>', prompt=True)

slide("R11 · Members-only group messages", '<p>Both text and file messages use the same membership check. The server records the authorized audience when the message is sent.</p>' + code("server.py", 'elif action in {"message", "file"}', 11) + code("server.py", 'async def broadcast', 4), prompt=True)

slide("Part 3<br><em>A little more useful.</em>", '<p class="lead">Four bonus candidates · at least one AI feature.</p><p>1. AI conversation summaries<br>2. Files through sockets<br>3. Delivery and read receipts<br>4. Oracle cloud deployment</p><div class="note">Message search is also implemented. The instructor decides the final acceptance of bonus features.</div>')

slide("Special 1 · AI catch-up summaries", '<p><strong>Model:</strong> Qwen2.5 0.5B Instruct via Ollama. Real model inference runs on the Oracle server. Only the requesting user’s authorized text history enters the prompt; only that user receives the summary.</p>' + code("server.py", 'async with session.post(AI_URL', 15) + '<p class="reference">References: <a href="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct">Qwen model card</a> · <a href="https://ollama.com/library/qwen2.5:0.5b">Ollama model</a> · <a href="https://docs.ollama.com/api/chat">Inference API</a>. Small models can make mistakes.</p>', prompt=True)

slide("Special 2 · Share a file", '<p>Files travel inside WebSocket frames as base64 data, through the same private/group access rules. Downloads are attachments, not rendered content. Maximum: 256 KiB.</p>' + code("server.py", 'filename, content = data.get', 14) + '<div class="note">Demo: transfer notes.txt privately and download it from the recipient browser. Verify that the third client receives nothing.</div>', prompt=True)

slide("Special 3 · Delivery and read receipts", '<p>“Sent” means the server accepted the message. A recipient browser acknowledges receipt for “Delivered”. Opening the focused conversation sends “Read”. Receipts are restricted to the message’s original audience.</p>' + code("server.py", 'elif action in {"read", "received"}', 16), prompt=True)

slide("Special 4 · Automated cloud deployment", '<p>Push to main → socket/browser tests → amd64 + arm64 image in GHCR → SSH to Oracle → pull that commit’s image → container health check → public HTTPS check.</p>' + code(".github/workflows/deploy.yml", 'platforms: linux/amd64', 5) + code("scripts/deploy.sh", '"${compose[@]}" pull', 10) + '<div class="note">Before submission: add team details, rehearse on two physical computers, and show a successful workflow run. Names/rooms/history are session-only and reset on deployment.</div>', prompt=True)

assert len(slides) == 20
for index in [4, 7, 8, 19]:
    slides[index] = slides[index].replace('class="slide"', 'class="slide dense"', 1)
css = '''
*{box-sizing:border-box}body{margin:0;background:#e8eddf;color:#243b31;font-family:Arial,sans-serif}.slide{background:#fafaf6;width:min(1280px,100vw);min-height:720px;margin:30px auto;padding:40px 55px 65px;position:relative;box-shadow:0 8px 40px #263d2420}.tag{font-size:11px;letter-spacing:2px;color:#879a70;margin-bottom:20px}h1{font-family:Georgia,serif;font-size:39px;font-weight:400;line-height:1.2;margin:0 0 25px}h1 em{color:#7b9563;font-weight:400}p{font-size:18px;line-height:1.6;margin:13px 0}.lead{font-size:24px;max-width:900px}footer{position:absolute;bottom:24px;left:55px;right:55px;display:flex;justify-content:space-between;font-size:11px;color:#9aa68d;border-top:1px solid #e0e7d6;padding-top:12px}.note{border-left:3px solid #93af77;background:#edf3e6;padding:14px 18px;font-size:15px;line-height:1.6;margin-top:20px}.prompt{font-size:11px;color:#8b977f;margin-top:14px}.source{font-size:11px;color:#799464;margin:14px 0 6px}pre{background:#153e32;color:#e1edce;border-radius:9px;padding:15px 20px;font-size:13px;line-height:1.55;margin:0;overflow:auto;tab-size:4}table{border-collapse:collapse;width:100%;font-size:16px}th,td{text-align:left;padding:13px 15px;border-bottom:1px solid #dce6d2;line-height:1.5}th{background:#eaf1e1;color:#537342}td:first-child{width:190px}.architecture{display:flex;align-items:center;justify-content:space-between;gap:18px;margin:35px 0}.stack{display:flex;flex-direction:column;gap:20px}.box{padding:25px 18px;text-align:center;background:#e2ebd6;border:1px solid #cbdabb;border-radius:12px;font-size:19px;min-width:170px}.box small,.arrow small{display:block;font-size:12px;color:#6f855b;line-height:1.6;margin-top:10px}.arrow{text-align:center;font-size:40px;color:#729156}.ai-row{border:1px solid #d7e4ca;border-radius:7px;padding:18px;text-align:center;color:#678450;margin:20px 0}.columns{display:flex;gap:35px;align-items:flex-start}.columns>div{flex:1;min-width:0}.phone{width:220px;max-height:460px;object-fit:contain;border-radius:12px;border:1px solid #d6e2cb}.reference{font-size:13px;color:#849577}a{color:#547940}nav{position:fixed;bottom:12px;right:20px;z-index:9;display:flex;gap:8px}nav button{border:1px solid #b9cfa5;background:#174e43;color:#e3f0d4;padding:9px 13px;border-radius:7px;cursor:pointer}html{scroll-behavior:smooth}@media print{@page{size:13.333in 7.5in;margin:0}body{background:white}.slide{width:1280px;height:720px;min-height:720px;margin:0;box-shadow:none;break-after:page;overflow:hidden}nav{display:none}*{print-color-adjust:exact;-webkit-print-color-adjust:exact}html{scroll-behavior:auto}}@media(max-width:700px){.slide{padding:30px 22px 70px;margin:16px auto}h1{font-size:30px}p{font-size:16px}.columns{flex-direction:column}.phone{width:190px}.architecture{flex-wrap:wrap}.box{min-width:140px;font-size:15px}.arrow{font-size:26px}pre{font-size:10px}footer{left:22px;right:22px}.tag{font-size:9px}}
'''
css += 'pre code{white-space:pre-wrap;overflow-wrap:anywhere}.dense pre{font-size:12px;line-height:1.4;padding:12px 18px}.dense p{font-size:16px;line-height:1.5}.dense .note{font-size:14px;padding:12px 16px}.dense h1{margin-bottom:20px}'
document = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Relay — Implementation Explanation</title><style>' + css + '</style><body>' + "\n".join(slides) + '''
<nav><button id="prev" aria-label="Previous slide">←</button><button id="next" aria-label="Next slide">→</button><button id="print">Print / PDF</button></nav>
<script>const slides=[...document.querySelectorAll('.slide')];function move(d){let i=slides.findIndex(s=>s.getBoundingClientRect().top>=-50);if(i<0)i=slides.length-1;slides[Math.max(0,Math.min(slides.length-1,i+d))].scrollIntoView()}document.getElementById('prev').onclick=()=>move(-1);document.getElementById('next').onclick=()=>move(1);document.getElementById('print').onclick=()=>window.print();document.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='PageDown'){e.preventDefault();move(1)}if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();move(-1)}})</script></body></html>'''
output = ROOT / "docs" / "implementation.html"
output.parent.mkdir(exist_ok=True)
output.write_text(document)
print(f"Built {len(slides)} slides: {output}")

if "--pdf" in __import__("sys").argv:
    import asyncio
    import os
    from playwright.async_api import async_playwright

    async def export_pdf():
        async with async_playwright() as playwright:
            options = {"headless": True}
            if os.getenv("CHROMIUM_PATH"):
                options["executable_path"] = os.environ["CHROMIUM_PATH"]
            browser = await playwright.chromium.launch(**options)
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.goto(output.as_uri())
            await page.emulate_media(media="print")
            issues = await page.evaluate('''[...document.querySelectorAll('.slide')].map((s,i)=>({
                slide:i+1, footer:s.querySelector('footer').getBoundingClientRect().top,
                content:Math.max(...[...s.children].filter(x=>x.tagName!=='FOOTER')
                .map(x=>x.getBoundingClientRect().bottom))})).filter(x=>x.content>x.footer-8)''')
            assert not issues, f"Slide content overlaps footer: {issues}"
            await page.pdf(path=str(output.with_suffix(".pdf")), prefer_css_page_size=True, print_background=True)
            await browser.close()
            print("Exported PDF with 20 slides")

    asyncio.run(export_pdf())
