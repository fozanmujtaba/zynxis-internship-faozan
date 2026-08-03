"""Renders a markdown file into a PDF using reportlab.

A minimal markdown subset is supported (#/##  headings, ``` code fences,
- bullets, plain paragraphs) -- enough for this project's own reports.

Run:
  python generate_report.py accuracy_report.md accuracy_report.pdf
"""

import sys

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("H1", parent=styles["Heading1"], fontSize=15, spaceAfter=8))
styles.add(ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11.5, spaceBefore=9, spaceAfter=4))
styles.add(ParagraphStyle("Body", parent=styles["BodyText"], fontSize=8.8, leading=11.8, alignment=TA_LEFT, spaceAfter=4))
styles.add(ParagraphStyle("BulletItem", parent=styles["Body"], leftIndent=16, bulletIndent=4))
styles.add(ParagraphStyle("CodeBlock", parent=styles["Code"], fontSize=7, leading=9, backColor="#f2f2f2"))


def bold(text: str) -> str:
    while "**" in text:
        text = text.replace("**", "<b>", 1).replace("**", "</b>", 1)
    return text


def flush_para(story: list, buf: list[str]) -> None:
    if not buf:
        return
    text = " ".join(buf)
    if text.startswith("- "):
        story.append(Paragraph("&bull;&nbsp;&nbsp;" + bold(text[2:]), styles["BulletItem"]))
    else:
        story.append(Paragraph(bold(text), styles["Body"]))
    buf.clear()


def build_story(lines: list[str]) -> list:
    story: list = []
    in_code = False
    code_buf: list[str] = []
    para_buf: list[str] = []

    for raw in lines:
        line = raw.rstrip("\n")

        if line.strip().startswith("```"):
            flush_para(story, para_buf)
            if in_code:
                story.append(Preformatted("\n".join(code_buf), styles["CodeBlock"]))
                story.append(Spacer(1, 6))
                code_buf = []
            in_code = not in_code
            continue

        if in_code:
            code_buf.append(line)
            continue

        if not line.strip():
            flush_para(story, para_buf)
            continue

        if line.startswith("## "):
            flush_para(story, para_buf)
            story.append(Paragraph(line[3:], styles["H2"]))
        elif line.startswith("# "):
            flush_para(story, para_buf)
            story.append(Paragraph(line[2:], styles["H1"]))
        elif line.startswith("- "):
            flush_para(story, para_buf)
            para_buf.append(line)
        else:
            para_buf.append(line)

    flush_para(story, para_buf)
    return story


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f:
        lines = f.readlines()

    doc = SimpleDocTemplate(
        out, pagesize=LETTER,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    )
    doc.build(build_story(lines))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
