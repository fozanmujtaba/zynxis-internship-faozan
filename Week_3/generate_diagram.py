"""Generates architecture_diagram.pdf — the Week 3 memory architecture diagram."""

from reportlab.lib.pagesizes import landscape, LETTER
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

OUT = "architecture_diagram.pdf"
W, H = landscape(LETTER)

INK      = HexColor("#1f2430")
BOX_FILL = HexColor("#eef2ff")
ST_FILL  = HexColor("#e6f7f0")
LT_FILL  = HexColor("#fff1e6")
LINE     = HexColor("#4b5563")


def box(c, x, y, w, h, label, fill=BOX_FILL, lines=None):
    c.setFillColor(fill)
    c.setStrokeColor(INK)
    c.setLineWidth(1.2)
    c.roundRect(x, y, w, h, 8, fill=1, stroke=1)
    c.setFillColor(INK)
    text_lines = lines if lines else [label]
    font_size = 10.5
    c.setFont("Helvetica-Bold", font_size)
    total_h = len(text_lines) * (font_size + 3)
    start_y = y + h / 2 + total_h / 2 - font_size
    for i, line in enumerate(text_lines):
        c.drawCentredString(x + w / 2, start_y - i * (font_size + 3), line)


def arrow(c, x1, y1, x2, y2, label=None, dash=None):
    c.setStrokeColor(LINE)
    c.setLineWidth(1.3)
    if dash:
        c.setDash(dash, 0)
    else:
        c.setDash([], 0)
    c.line(x1, y1, x2, y2)
    # arrowhead
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    for da in (0.5, -0.5):
        c.line(x2, y2, x2 - 9 * math.cos(ang - da), y2 - 9 * math.sin(ang - da))
    if label:
        c.setDash([], 0)
        c.setFillColor(LINE)
        c.setFont("Helvetica", 8.5)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        c.drawCentredString(mx, my + 5, label)


def main() -> None:
    c = canvas.Canvas(OUT, pagesize=(W, H))

    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(INK)
    c.drawCentredString(W / 2, H - 45, "Personal Assistant — Memory Architecture (Week 3)")
    c.setFont("Helvetica", 9.5)
    c.drawCentredString(W / 2, H - 62, "Short-term buffer for recent turns  +  Long-term ChromaDB store for durable recall")

    bw, bh = 190, 50

    # User query (top center)
    ux, uy = W / 2 - bw / 2, H - 130
    box(c, ux, uy, bw, bh, "", lines=["User Query"])

    # Long-term memory (left)
    ltx, lty = 90, H - 260
    box(c, ltx, lty, bw, bh + 10, "", fill=LT_FILL,
        lines=["Long-Term Memory", "(ChromaDB, ./chroma_store)", "similarity search: recall(query)"])

    # Short-term memory (right)
    stx, sty = W - 90 - bw, H - 260
    box(c, stx, sty, bw, bh + 10, "", fill=ST_FILL,
        lines=["Short-Term Memory", "(in-process buffer)", "last N turns verbatim"])

    # LLM box (center, below both)
    lx, ly = W / 2 - bw / 2, H - 390
    box(c, lx, ly, bw, bh, "", lines=["Groq LLM", "(llama-3.3-70b-versatile)"])

    # Response box (bottom center)
    rx, ry = W / 2 - bw / 2, H - 470
    box(c, rx, ry, bw, bh - 10, "", lines=["Assistant Response"])

    # Arrows: user query -> long-term recall, user query -> short-term
    arrow(c, ux + 20, uy, ltx + bw - 30, lty + bh + 10, label="recall(query)")
    arrow(c, ux + bw - 20, uy, stx + 30, sty + bh + 10, label="append(user turn)")

    # long-term + short-term -> LLM
    arrow(c, ltx + bw - 10, lty + 10, lx + 15, ly + bh - 5, label="top-k memories")
    arrow(c, stx + 10, sty + 10, lx + bw - 15, ly + bh - 5, label="last N turns")

    # user query -> LLM directly (new query)
    c.setDash([3, 3], 0)
    arrow(c, W / 2, uy, W / 2, ly + bh + 5, label="+ new query")
    c.setDash([], 0)

    # LLM -> response
    arrow(c, W / 2, ly, W / 2, ry + (bh - 10))

    # response -> stores (feedback loop, dashed) — routed along the outer
    # sides so they don't cross back through the LLM/response boxes
    arrow(c, lx - 6, ly + 12, ltx + 40, lty - 15, label="remember(user text)", dash=[3, 3])
    arrow(c, lx + bw + 6, ly + 12, stx + bw - 40, sty - 15, label="store assistant turn", dash=[3, 3])

    c.showPage()
    c.save()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
