"""Fill the course's 20-page PDF template and create editable slide overlays."""

from pathlib import Path
import tempfile
import textwrap

import pymupdf
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Pt


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "Computer_Network_Term_Project___Socket_Programming___Implementation_Explanation-1047532-17880926752070.pdf"
PDF_OUT = Path(__file__).with_name("Relay_Implementation_Explanation.pdf")
PPTX_OUT = PDF_OUT.with_suffix(".pptx")
BLACK = (0, 0, 0)
WHITE = (1, 1, 1)

# Each code page follows the template's two code boxes and two prompt boxes.
# Snippets are intentionally short excerpts; the cited files contain complete functions.
CONTENT = {
    7:  (("server.py", 38, 49), ("server.py", 259, 274),
         "Validate a 1-24 character username with Pydantic.",
         "Reject active duplicate names, ignoring case."),
    8:  (("server.py", 242, 249), ("static/app.js", 117, 122),
         "Broadcast every connected user's name in real time.",
         "Update the browser list when a state event arrives."),
    9:  (("server.py", 279, 292), ("server.py", 234, 240),
         "Create or reuse a private room for two sessions.",
         "Send room metadata and recent history to clients."),
    10: (("server.py", 78, 89), ("server.py", 340, 353),
         "Validate message text and keep 100 per room.",
         "Send each new message to its room members."),
    11: (("server.py", 227, 232), ("server.py", 347, 353),
         "Check room membership before accepting a message.",
         "Deliver a private message only to its two peers."),
    12: (("server.py", 58, 69), ("server.py", 303, 318),
         "Validate the new group's name and length.",
         "Start each group with only its creator inside."),
    13: (("server.py", 215, 225), ("static/app.js", 230, 239),
         "Include every group's current member names.",
         "Show group members when hovering over its row."),
    14: (("server.py", 72, 76), ("server.py", 320, 330),
         "Require an explicit Join command from the user.",
         "Add only the requesting session to the group."),
    15: (("server.py", 227, 232), ("server.py", 342, 353),
         "Reject text from users who have not joined.",
         "Broadcast group messages to members only."),
    17: (("server.py", 138, 142), ("server.py", ((435, 439), (471, 477))),
         "Build a room summary with Gemini or Qwen.",
         "If Gemini fails, retry with local Qwen."),
    18: (("server.py", 93, 105), ("server.py", 363, 378),
         "Validate Base64 contents and the 256 KiB limit.",
         "Send the file in WebSocket frames to members."),
    19: (("server.py", 124, 135), ("server.py", 384, 401),
         "Track received and read message IDs.",
         "Broadcast receipt updates to room members."),
    20: (("compose.oracle.yml", 6, 16), ("scripts/deploy.sh", ((17, 21), (28, 29))),
         "Route the app through existing Traefik TLS.",
         "Build, push, SSH deploy, and check health."),
}

HEADINGS = {
    17: ("Special Point 1: AI chat summaries", "AI models: Gemini 3.5 Flash-Lite; Qwen2.5 0.5B (Ollama)"),
    18: ("Special Point 2: WebSocket file sharing", ""),
    19: ("Special Point 3: Delivery and read receipts", ""),
    20: ("Special Point 4: Oracle cloud deployment", ""),
}


def add_text(page, slide, rect, value, size=12, font="helv", align="left", fill=True):
    """Add the same editable text overlay to the PDF and PowerPoint page."""
    if fill:
        page.draw_rect(rect, color=None, fill=WHITE, overlay=True)
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(rect.x0), Pt(rect.y0),
                                       Pt(rect.width), Pt(rect.height))
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(255, 255, 255)
        shape.line.fill.background()
    actual_size = size
    while actual_size >= 8:
        remaining = page.insert_textbox(rect, value, fontsize=actual_size, fontname=font,
                                        color=BLACK, align=1 if align == "center" else 0,
                                        overlay=True)
        if remaining >= 0:
            break
        # Failed insertions draw nothing; retry at a smaller size.
        actual_size -= 0.5
    if actual_size < 8:
        raise ValueError(f"Text does not fit: {value[:60]!r}")
    box = slide.shapes.add_textbox(Pt(rect.x0), Pt(rect.y0), Pt(rect.width), Pt(rect.height))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Pt(0)
    frame.margin_right = Pt(0)
    frame.margin_top = Pt(0)
    frame.margin_bottom = Pt(0)
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE if align == "center" else MSO_ANCHOR.TOP
    for i, line in enumerate(value.split("\n")):
        paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        paragraph.text = line
        paragraph.alignment = PP_ALIGN.CENTER if align == "center" else PP_ALIGN.LEFT
        paragraph.space_after = Pt(0)
        paragraph.space_before = Pt(0)
        for run in paragraph.runs:
            run.font.name = "Consolas" if font == "cour" else "Aptos"
            run.font.size = Pt(actual_size)
            run.font.color.rgb = RGBColor(0, 0, 0)


def code_page(page, slide, items):
    boxes = [d["rect"] for d in page.get_drawings()
             if d["type"] == "s" and d["rect"].width > 300]
    if len(boxes) != 4:
        raise ValueError(f"Expected four template boxes, found {len(boxes)}")
    left_code, right_code = sorted((r for r in boxes if r.y0 < 400), key=lambda r: r.x0)
    left_prompt, right_prompt = sorted((r for r in boxes if r.y0 >= 400), key=lambda r: r.x0)
    for rect, spec in zip((left_code, right_code), items[:2]):
        filename = spec[0]
        ranges = [(spec[1], spec[2])] if len(spec) == 3 else spec[1]
        source = (Path(__file__).resolve().parents[1] / filename).read_text().splitlines()
        label = ",".join(f"{start}-{end}" for start, end in ranges)
        excerpts = [textwrap.dedent("\n".join(source[start - 1:end])) for start, end in ranges]
        value = f"{filename}:{label}\n" + "\n# ...\n".join(excerpts)
        inner = pymupdf.Rect(rect.x0 + 10, rect.y0 + 8, rect.x1 - 10, rect.y1 - 7)
        add_text(page, slide, inner, value, size=9.5, font="cour")
    for rect, value in zip((left_prompt, right_prompt), items[2:]):
        inner = pymupdf.Rect(rect.x0 + 7, rect.y0 + 5, rect.x1 - 7, rect.y1 - 4)
        add_text(page, slide, inner, value, size=11.2)


def draw_box(page, slide, rect, label):
    page.draw_rect(rect, color=BLACK, width=1, overlay=True)
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(rect.x0), Pt(rect.y0),
                                   Pt(rect.width), Pt(rect.height))
    shape.fill.background()
    shape.line.color.rgb = RGBColor(0, 0, 0)
    shape.line.width = Pt(1)
    add_text(page, slide, pymupdf.Rect(rect.x0 + 5, rect.y0 + 17,
                                       rect.x1 - 5, rect.y1 - 5),
             label, size=14, align="center", fill=False)


def build():
    pdf = pymupdf.open(TEMPLATE)
    ppt = Presentation()
    ppt.slide_width = Pt(pdf[0].rect.width)
    ppt.slide_height = Pt(pdf[0].rect.height)
    blank = ppt.slide_layouts[6]
    with tempfile.TemporaryDirectory() as temp:
        for number, page in enumerate(pdf, 1):
            # Rasterized original is the PPTX background; PDF retains original vectors.
            background = Path(temp) / f"page-{number}.png"
            page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(background)
            slide = ppt.slides.add_slide(blank)
            slide.shapes.add_picture(str(background), 0, 0, ppt.slide_width, ppt.slide_height)

            if number == 1:
                add_text(page, slide, pymupdf.Rect(330, 319, 630, 354),
                         "Group X", size=24, align="center")
                add_text(page, slide, pymupdf.Rect(300, 356, 660, 391),
                         "6xxxxxxxx21 Name Surname", size=23, align="center")
                add_text(page, slide, pymupdf.Rect(300, 392, 660, 427),
                         "6xxxxxxxx21 Name Surname", size=23, align="center")
            elif number == 3:
                add_text(page, slide, pymupdf.Rect(280, 248, 680, 290), "", fill=True)
                draw_box(page, slide, pymupdf.Rect(85, 190, 220, 265), "Browser A")
                draw_box(page, slide, pymupdf.Rect(85, 285, 220, 360), "Browser B")
                draw_box(page, slide, pymupdf.Rect(315, 235, 455, 315), "Traefik\nHTTPS/WSS")
                draw_box(page, slide, pymupdf.Rect(540, 235, 680, 315), "Python server\n/ws :8080")
                draw_box(page, slide, pymupdf.Rect(765, 183, 875, 255), "Gemini\nHTTPS")
                draw_box(page, slide, pymupdf.Rect(765, 288, 875, 360), "Ollama\n:11434")
                for x0, y0, x1, y1 in [(220, 227, 315, 275), (220, 323, 315, 275),
                                       (455, 275, 540, 275), (680, 275, 765, 219),
                                       (680, 275, 765, 324)]:
                    page.draw_line((x0, y0), (x1, y1), color=BLACK, width=1.5)
                    connector = slide.shapes.add_connector(1, Pt(x0), Pt(y0), Pt(x1), Pt(y1))
                    connector.line.color.rgb = RGBColor(0, 0, 0)
                    connector.line.width = Pt(1.5)
                add_text(page, slide, pymupdf.Rect(72, 414, 890, 490),
                         "Two laptops reach Oracle through Traefik. Chat uses one /ws connection. "
                         "Each summary selects Gemini or local Qwen; Gemini failure retries locally.",
                         size=18)
            elif number == 4:
                add_text(page, slide, pymupdf.Rect(70, 285, 900, 510),
                         "TCP: reliable, ordered transport under HTTP and WebSocket.\n"
                         "HTTPS/WSS: encrypt browser traffic through Traefik on port 443.\n"
                         "WebSocket /ws: one persistent channel for chat, files, and receipts.\n"
                         "JSON: command and event format within WebSocket frames.\n"
                         "Internal HTTP: server to Ollama; HTTPS: server to Gemini.\n"
                         "SSH: GitHub Actions connects to Oracle for deployment.", size=17)
            elif number == 5:
                boxes = sorted((d["rect"] for d in page.get_drawings()
                                if d["type"] == "s" and d["rect"].width > 800),
                               key=lambda r: r.y0)
                large, small = boxes
                add_text(page, slide, pymupdf.Rect(large.x0 + 15, large.y0 + 12,
                                                   large.x1 - 15, large.y1 - 10),
                         "server.py / WebSocket transport\n"
                         "def create_app():\n"
                         "    app = web.Application()\n"
                         "    app['chat_server'] = ChatServer()\n"
                         "    app.router.add_get('/ws', ws_handler)\n"
                         "    return app\n\n"
                         "async def ws_handler(request):\n"
                         "    server = request.app['chat_server']\n"
                         "    socket = web.WebSocketResponse(heartbeat=30.0)\n"
                         "    await socket.prepare(request)\n"
                         "    session = UserSession(socket=socket)\n"
                         "    server.sessions[session.id] = session\n"
                         "    try:\n"
                         "        async for msg in socket:\n"
                         "            if msg.type == WSMsgType.TEXT:\n"
                         "                await server.dispatch(session, msg.data)\n"
                         "    finally:\n"
                         "        await server.disconnect(session)", size=13.5, font="cour")
                add_text(page, slide, pymupdf.Rect(small.x0 + 9, small.y0 + 5,
                                                   small.x1 - 9, small.y1 - 4),
                         "Prompt: Build a single /ws endpoint; route JSON frames to a central dispatcher.", size=12)
            elif number in CONTENT:
                if number in HEADINGS:
                    title, subtitle = HEADINGS[number]
                    add_text(page, slide, pymupdf.Rect(85, 35, 875, 120), "")
                    add_text(page, slide, pymupdf.Rect(85, 39, 875, 86),
                             title, size=28, align="center", fill=False)
                    if subtitle:
                        add_text(page, slide, pymupdf.Rect(180, 82, 780, 117),
                                 subtitle, size=17, align="center", fill=False)
                    if number == 17:
                        add_text(page, slide, pymupdf.Rect(100, 121, 860, 145),
                                 "Model refs: ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite  |  ollama.com/library/qwen2.5:0.5b",
                                 size=10, align="center", fill=False)
                code_page(page, slide, CONTENT[number])

        pdf.save(PDF_OUT, garbage=4, deflate=True)
        ppt.save(PPTX_OUT)
    print(PDF_OUT)
    print(PPTX_OUT)


if __name__ == "__main__":
    build()
