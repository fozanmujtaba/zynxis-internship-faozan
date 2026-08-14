"""Renders a markdown file into a PDF using reportlab.

A minimal markdown subset is supported (#/##/### headings, ``` code fences,
- bullets, | tables |, > blockquotes, plain paragraphs) -- enough for this
project's own reports.

Run:
  python generate_report.py report.md report.pdf
  python generate_report.py case_study.md case_study.pdf --compact

--compact tightens type and margins for documents that must fit a fixed page
budget, such as a one-page case study.
"""

import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Preformatted, Table, TableStyle,
)

CONTENT_WIDTH = 7.1 * inch  # LETTER minus the 0.7in side margins

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("H1", parent=styles["Heading1"], fontSize=15, spaceAfter=8))
styles.add(ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11.5, spaceBefore=9, spaceAfter=4))
styles.add(ParagraphStyle("H3", parent=styles["Heading3"], fontSize=9.8, spaceBefore=7, spaceAfter=3))
styles.add(ParagraphStyle("Body", parent=styles["BodyText"], fontSize=8.8, leading=11.8, alignment=TA_LEFT, spaceAfter=4))
styles.add(ParagraphStyle("BulletItem", parent=styles["Body"], leftIndent=16, bulletIndent=4))
styles.add(ParagraphStyle("Quote", parent=styles["Body"], leftIndent=14, rightIndent=14,
                          textColor=colors.HexColor("#444444"), fontSize=8.3, spaceBefore=4, spaceAfter=6))
styles.add(ParagraphStyle("CodeBlock", parent=styles["Code"], fontSize=7, leading=9, backColor="#f2f2f2"))
styles.add(ParagraphStyle("TableCell", parent=styles["Body"], fontSize=7.6, leading=9.6, spaceAfter=0))
styles.add(ParagraphStyle("TableHead", parent=styles["TableCell"], textColor=colors.white))


def bold(text: str) -> str:
    while "**" in text:
        text = text.replace("**", "<b>", 1).replace("**", "</b>", 1)
    return text


def split_row(line: str) -> list[str]:
    """Splits '| a | b |' into ['a', 'b']."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator(line: str) -> bool:
    """True for the '| --- | --- |' rule under a table header."""
    return all(set(cell) <= set("-: ") and "-" in cell for cell in split_row(line))


def flush_table(story: list, rows: list[str]) -> None:
    """Turns buffered markdown '|' rows into a styled reportlab Table."""
    if not rows:
        return

    parsed = [split_row(r) for r in rows if not is_separator(r)]
    rows.clear()
    if not parsed:
        return

    # Pad ragged rows so reportlab gets a rectangular grid.
    width = max(len(r) for r in parsed)
    parsed = [r + [""] * (width - len(r)) for r in parsed]

    data = [
        [Paragraph(bold(cell), styles["TableHead" if i == 0 else "TableCell"]) for cell in row]
        for i, row in enumerate(parsed)
    ]

    table = Table(data, colWidths=[CONTENT_WIDTH / width] * width, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#33475b")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d0d8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(Spacer(1, 4))
    story.append(table)
    story.append(Spacer(1, 8))


def join_lines(buf: list[str]) -> str:
    """Joins wrapped lines, honouring markdown's trailing-double-space hard break."""
    parts = []
    for i, line in enumerate(buf):
        stripped = line.rstrip()
        if line.endswith("  ") and i < len(buf) - 1:
            stripped += "<br/>"
        parts.append(stripped)
    return " ".join(parts)


def flush_para(story: list, buf: list[str]) -> None:
    if not buf:
        return
    text = join_lines(buf)
    if text[:2] in ("- ", "* "):
        story.append(Paragraph("&bull;&nbsp;&nbsp;" + bold(text[2:]), styles["BulletItem"]))
    else:
        story.append(Paragraph(bold(text), styles["Body"]))
    buf.clear()


def build_story(lines: list[str]) -> list:
    story: list = []
    in_code = False
    code_buf: list[str] = []
    para_buf: list[str] = []
    table_buf: list[str] = []

    for raw in lines:
        line = raw.rstrip("\n")

        if line.strip().startswith("```"):
            flush_para(story, para_buf)
            flush_table(story, table_buf)
            if in_code:
                story.append(Preformatted("\n".join(code_buf), styles["CodeBlock"]))
                story.append(Spacer(1, 6))
                code_buf = []
            in_code = not in_code
            continue

        if in_code:
            code_buf.append(line)
            continue

        if line.strip().startswith("|"):
            flush_para(story, para_buf)
            table_buf.append(line)
            continue

        flush_table(story, table_buf)

        if not line.strip():
            flush_para(story, para_buf)
            continue

        if line.startswith("### "):
            flush_para(story, para_buf)
            story.append(Paragraph(bold(line[4:]), styles["H3"]))
        elif line.startswith("## "):
            flush_para(story, para_buf)
            story.append(Paragraph(line[3:], styles["H2"]))
        elif line.startswith("# "):
            flush_para(story, para_buf)
            story.append(Paragraph(line[2:], styles["H1"]))
        elif line.startswith("> "):
            flush_para(story, para_buf)
            story.append(Paragraph(bold(line[2:]), styles["Quote"]))
        elif line.strip() == "---":
            flush_para(story, para_buf)
            story.append(Spacer(1, 10))
        elif line[:2] in ("- ", "* "):
            flush_para(story, para_buf)
            para_buf.append(line)
        else:
            para_buf.append(line)

    flush_para(story, para_buf)
    flush_table(story, table_buf)
    return story


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    compact = "--compact" in sys.argv[3:]

    if compact:
        styles["Body"].fontSize, styles["Body"].leading = 8.1, 10.4
        styles["Body"].spaceAfter = 3
        styles["BulletItem"].fontSize, styles["BulletItem"].leading = 8.1, 10.4
        styles["H1"].fontSize, styles["H1"].spaceAfter = 13.5, 5
        styles["H2"].fontSize = 10.5
        styles["H2"].spaceBefore, styles["H2"].spaceAfter = 6, 2
        styles["TableCell"].fontSize, styles["TableCell"].leading = 7.2, 9.0
        styles["Quote"].fontSize = 7.8
    with open(src, encoding="utf-8") as f:
        lines = f.readlines()

    margin = 0.5 if compact else 0.7
    doc = SimpleDocTemplate(
        out, pagesize=LETTER,
        topMargin=(0.45 if compact else 0.6) * inch,
        bottomMargin=(0.45 if compact else 0.6) * inch,
        leftMargin=margin * inch, rightMargin=margin * inch,
    )
    doc.build(build_story(lines))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
