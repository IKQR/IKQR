#!/usr/bin/env python3
"""Renders the repo's Markdown profile files into a single PDF resume.

Source of truth (all in the repo root, next to this script's parent dir):
    Summary.md, SKILLS.md, EXPERIENCE.md, PROJECTS.md, EDUCATION.md,
    CERTIFICATES.md, LANGUAGES.md

Configuration (contact header, phone) comes from environment variables with
defaults - see config.py for the full list (RESUME_FULL_NAME, RESUME_PHONE,
etc.). The output path is fixed at resume/output/Kusik_Illia_Resume.pdf.

Usage:
    python scripts/generate_resume.py
"""

from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Circle, Drawing, Group, Line, Polygon, Rect
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import config

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RESUME_DIR = Path(__file__).resolve().parent.parent
LINK_COLOR = "#1a56db"
MUTED_COLOR = "#555555"

# Base-14 fonts (Helvetica & co.) have no Cyrillic/Unicode glyphs beyond
# WinAnsi. Fall back to the first Unicode TrueType family found on disk -
# Arial on Windows (local dev), DejaVu Sans on Linux (CI runners, see
# .github/workflows/release-cv.yml which installs fonts-dejavu-core) -
# so any non-Latin text added to the profile Markdown later still renders
# correctly instead of showing missing-glyph boxes; otherwise stick with
# Helvetica.
FONT_REGULAR, FONT_BOLD, FONT_ITALIC = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
_FONT_CANDIDATES = [
    (
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path(r"C:\Windows\Fonts\ariali.ttf"),
        Path(r"C:\Windows\Fonts\arialbi.ttf"),
    ),
    (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
    ),
]
for _regular, _bold, _italic, _bold_italic in _FONT_CANDIDATES:
    if _regular.exists() and _bold.exists() and _italic.exists() and _bold_italic.exists():
        pdfmetrics.registerFont(TTFont("Body", str(_regular)))
        pdfmetrics.registerFont(TTFont("Body-Bold", str(_bold)))
        pdfmetrics.registerFont(TTFont("Body-Italic", str(_italic)))
        pdfmetrics.registerFont(TTFont("Body-BoldItalic", str(_bold_italic)))
        pdfmetrics.registerFontFamily(
            "Body", normal="Body", bold="Body-Bold",
            italic="Body-Italic", boldItalic="Body-BoldItalic",
        )
        FONT_REGULAR, FONT_BOLD, FONT_ITALIC = "Body", "Body-Bold", "Body-Italic"
        break


# --------------------------------------------------------------------------
# Markdown helpers
# --------------------------------------------------------------------------

def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text: str) -> str:
    """Convert the small subset of Markdown used in the profile files
    (**bold** and [text](url)) into ReportLab's paragraph markup."""
    text = esc(text.strip())
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        rf'<link href="\2" color="{LINK_COLOR}"><u>\1</u></link>',
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# Splits on sentence-ending punctuation followed by a capitalized word, but
# not after known abbreviations (e.g. "e.g. MRI machines" should stay one
# sentence). Long multi-sentence fields render as one wall-of-text bullet
# otherwise; splitting them into one bullet per sentence keeps each bullet
# scannable at a glance.
_SENTENCE_SPLIT_RE = re.compile(r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\betc\.)(?<=[.!?])\s+(?=[A-Z])")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def split_blocks(text: str) -> list[str]:
    """Split a chunk on the '---' separator lines the repo uses between blocks."""
    return [b.strip() for b in re.split(r"\n-{3,}\n", text) if b.strip()]


def parse_labeled_block(text: str) -> dict[str, str]:
    """Parse a block of '**Label**: value' lines into {label: value}."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\*\*([^*]+)\*\*:\s*(.*)$", line.strip())
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()
    return fields


def parse_grouped_sections(text: str) -> list[dict]:
    """Parse the repeating '## Heading' / '> date range' / blocks... pattern
    shared by EXPERIENCE.md, EDUCATION.md and CERTIFICATES.md."""
    # Drop the leading '# Title' line, if any.
    text = re.sub(r"^#\s+.*\n+", "", text.strip())
    groups: list[dict] = []
    current: dict | None = None
    for chunk in split_blocks(text):
        heading_match = re.match(r"^##\s+(.+)$", chunk, re.MULTILINE)
        if heading_match:
            lines = chunk.splitlines()
            name = re.sub(r"^##\s+", "", lines[0]).strip()
            date_range = ""
            body_start = 1
            for i, line in enumerate(lines[1:], start=1):
                if line.strip().startswith(">"):
                    date_range = line.strip().lstrip(">").strip()
                    body_start = i + 1
                    break
                if line.strip():
                    body_start = i
                    break
            body = "\n".join(lines[body_start:]).strip()
            current = {"name": name, "date_range": date_range, "blocks": []}
            groups.append(current)
            if body:
                current["blocks"].append(parse_labeled_block(body))
        elif current is not None:
            current["blocks"].append(parse_labeled_block(chunk))
    return groups


def parse_flat_blocks(text: str) -> list[dict]:
    """Parse a flat list of labeled blocks (PROJECTS.md style, no grouping)."""
    text = re.sub(r"^#\s+.*\n+", "", text.strip())
    return [parse_labeled_block(chunk) for chunk in split_blocks(text)]


def parse_skills(text: str) -> list[tuple[str, str]]:
    """Parse SKILLS.md's '# Category' + nested '- item' bullets into a
    flat (category, comma-joined items) list."""
    categories: list[tuple[str, list]] = []
    current_items: list | None = None
    current_top: dict | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        heading = re.match(r"^#\s+(.+)$", raw_line)
        if heading:
            current_items = []
            categories.append((heading.group(1).strip(), current_items))
            current_top = None
            continue
        nested = re.match(r"^\s{2,}-\s+(.+)$", raw_line)
        top = re.match(r"^-\s+(.+)$", raw_line)
        if nested and current_top is not None:
            current_top.setdefault("children", []).append(nested.group(1).strip())
        elif top and current_items is not None:
            current_top = {"text": top.group(1).strip(), "children": []}
            current_items.append(current_top)

    result = []
    for category, items in categories:
        parts = []
        for item in items:
            label = re.sub(r"\*\*", "", item["text"])
            if item["children"]:
                children = "; ".join(re.sub(r"\*\*", "", c) for c in item["children"])
                parts.append(f"{label} ({children})")
            else:
                parts.append(label)
        result.append((category, ", ".join(parts)))
    return result


def parse_languages(text: str) -> list[str]:
    text = re.sub(r"^#\s+.*\n+", "", text.strip())
    return [
        re.sub(r"^-\s+", "", line.strip())
        for line in text.splitlines()
        if line.strip().startswith("-")
    ]


# --------------------------------------------------------------------------
# Styles
# --------------------------------------------------------------------------

def build_styles() -> dict[str, ParagraphStyle]:
    return {
        "name": ParagraphStyle(
            "name", fontName=FONT_BOLD, fontSize=22, leading=26,
            alignment=1, spaceAfter=2,
        ),
        "title": ParagraphStyle(
            "title", fontName=FONT_REGULAR, fontSize=11.5, leading=14,
            alignment=1, textColor=colors.HexColor(MUTED_COLOR), spaceAfter=6,
        ),
        "contact": ParagraphStyle(
            "contact", fontName=FONT_REGULAR, fontSize=CONTACT_FONT_SIZE, leading=CONTACT_LEADING,
            alignment=0, textColor=colors.HexColor(MUTED_COLOR),
        ),
        "section": ParagraphStyle(
            "section", fontName=FONT_BOLD, fontSize=13.5, leading=16,
            spaceBefore=15, spaceAfter=4, textColor=colors.HexColor("#1a2b4a"),
            characterSpace=0.4,
        ),
        "body": ParagraphStyle(
            "body", fontName=FONT_REGULAR, fontSize=9.7, leading=13.5,
            alignment=4, spaceAfter=6,
        ),
        "entry_title": ParagraphStyle(
            "entry_title", fontName=FONT_BOLD, fontSize=10.3, leading=13,
        ),
        "entry_date": ParagraphStyle(
            "entry_date", fontName=FONT_REGULAR, fontSize=9.5, leading=13,
            alignment=2, textColor=colors.HexColor(MUTED_COLOR),
        ),
        "entry_sub": ParagraphStyle(
            "entry_sub", fontName=FONT_ITALIC, fontSize=9.3, leading=12,
            textColor=colors.HexColor(MUTED_COLOR), spaceAfter=3,
        ),
        "stack": ParagraphStyle(
            "stack", fontName=FONT_ITALIC, fontSize=8.8, leading=12,
            textColor=colors.HexColor(MUTED_COLOR), spaceBefore=1, spaceAfter=8,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName=FONT_REGULAR, fontSize=9.5, leading=13,
            alignment=4,
        ),
        "skill_line": ParagraphStyle(
            "skill_line", fontName=FONT_REGULAR, fontSize=9.4, leading=13,
            spaceAfter=3,
        ),
    }


def section_heading(title: str, styles: dict) -> list:
    return [
        Paragraph(title.upper(), styles["section"]),
        HRFlowable(width="100%", thickness=1.1, color=colors.HexColor("#1a2b4a"),
                   spaceAfter=6),
    ]


def header_date_row(title_para: Paragraph, date_text: str, styles: dict) -> Table:
    date_para = Paragraph(esc(date_text), styles["entry_date"])
    table = Table([[title_para, date_para]], colWidths=[12 * cm, 5.4 * cm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return table


def bullets(items: list[str], styles: dict) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(inline(item), styles["bullet"]), spaceAfter=2)
         for item in items],
        bulletType="bullet", start="•", leftIndent=12, bulletFontSize=8,
    )


# --------------------------------------------------------------------------
# Small vector contact icons (no icon font needed, so nothing to embed)
# --------------------------------------------------------------------------

ICON = 7  # points, square - the icon artwork's own coordinate space
CONTACT_FONT_SIZE = 7.9
CONTACT_LEADING = 11  # shared row height for both the icon cells and the text cells

# Icons are drawn in a (0, ICON) local box, then re-wrapped into a box as
# tall as the text line (CONTACT_LEADING, set further down) and vertically
# centered in it. Without this, a Drawing sized just ICON x ICON reports a
# much shorter height than the Paragraph cells next to it, so Table's
# VALIGN=MIDDLE centers the icon against a shorter box than the text
# actually occupies and the icon visibly floats above the text baseline.


def _icon(shapes: list) -> Drawing:
    offset = (CONTACT_LEADING - ICON) / 2
    d = Drawing(ICON, CONTACT_LEADING)
    d.add(Group(*shapes, transform=(1, 0, 0, 1, 0, offset)))
    return d


def icon_pin() -> Drawing:
    color = colors.HexColor(MUTED_COLOR)
    cx, cy, r = ICON / 2, ICON * 0.62, ICON * 0.32
    return _icon([
        Polygon(points=[cx - r * 0.8, cy - r * 0.15, cx + r * 0.8, cy - r * 0.15, cx, 0.3],
                fillColor=color, strokeColor=None),
        Circle(cx, cy, r, fillColor=color, strokeColor=None),
        Circle(cx, cy, r * 0.4, fillColor=colors.white, strokeColor=None),
    ])


def icon_mail() -> Drawing:
    color = colors.HexColor(MUTED_COLOR)
    return _icon([
        Rect(0.3, 1.3, ICON - 0.6, ICON - 3.6, fillColor=None, strokeColor=color, strokeWidth=1.0),
        Line(0.3, ICON - 2.3, ICON / 2, ICON / 2 + 0.4, strokeColor=color, strokeWidth=1.0),
        Line(ICON - 0.3, ICON - 2.3, ICON / 2, ICON / 2 + 0.4, strokeColor=color, strokeWidth=1.0),
    ])


def icon_phone() -> Drawing:
    # A filled rounded-rect "handset body" - a thin diagonal bar between two
    # dots (a previous attempt) read as a pencil/slash at 7pt, not a phone.
    # A solid chunky shape stays legible at this size the way the filled pin
    # icon does.
    color = colors.HexColor(MUTED_COLOR)
    return _icon([
        Rect(2.1, 0.5, ICON - 4.2, ICON - 1, radius=1.3, fillColor=color, strokeColor=None),
    ])


# --------------------------------------------------------------------------
# Section builders
# --------------------------------------------------------------------------

def contact_row(items: list[tuple[Drawing | None, str, Paragraph]]) -> Table:
    """Lay out (icon, plain_text, label_flowable) triples on one line, centered.
    icon may be None for a plain text-only item (no icon column for it).

    Table auto-sizing (colWidths=None) sizes a column to its longest *word*,
    not its full text, which silently wraps normal-length labels - so text
    column widths are computed explicitly from the plain text instead.
    Padding is NOT used for the gap between items: TableStyle padding shrinks
    the usable width *inside* its own cell rather than adding space before
    the next column, so any real content padding here would just wrap the
    label a few characters early. The gap is baked into the column width
    itself instead, and all cell padding stays at 0.
    """
    ICON_GAP = 3  # icon -> its own label
    ITEM_GAP = 12  # label -> next item's icon

    cells: list = []
    col_widths: list = []
    for icon, text, label in items:
        if icon is not None:
            cells.append(icon)
            col_widths.append(ICON + ICON_GAP)
        cells.append(label)
        col_widths.append(pdfmetrics.stringWidth(text, FONT_REGULAR, CONTACT_FONT_SIZE) + ITEM_GAP)

    table = Table([cells], colWidths=col_widths)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    table.hAlign = "CENTER"
    return table


def build_header(styles: dict) -> list:
    def link(url: str, label: str) -> Paragraph:
        return Paragraph(f'<link href="{url}" color="{LINK_COLOR}">{esc(label)}</link>', styles["contact"])

    items: list[tuple[Drawing | None, str, Paragraph]] = []
    if config.LOCATION:
        items.append((icon_pin(), config.LOCATION, Paragraph(esc(config.LOCATION), styles["contact"])))
    items.append((icon_mail(), config.EMAIL, link(f"mailto:{config.EMAIL}", config.EMAIL)))
    if config.PHONE:
        items.append((icon_phone(), config.PHONE, Paragraph(esc(config.PHONE), styles["contact"])))

    items += [
        (None, config.LINKEDIN_LABEL, link(config.LINKEDIN_URL, config.LINKEDIN_LABEL)),
        (None, config.GITHUB_LABEL, link(config.GITHUB_URL, config.GITHUB_LABEL)),
        (None, config.SPOTIFY_LABEL, link(config.SPOTIFY_URL, config.SPOTIFY_LABEL)),
    ]

    return [
        Paragraph(esc(config.FULL_NAME), styles["name"]),
        Paragraph(esc(config.TITLE), styles["title"]),
        Spacer(1, 3),
        contact_row(items),
        Spacer(1, 10),
    ]


def build_summary(styles: dict) -> list:
    text = read(REPO_ROOT / "Summary.md")
    text = re.sub(r"^#\s+.*\n+", "", text.strip())
    return section_heading("Summary", styles) + [Paragraph(inline(text), styles["body"])]


def build_skills(styles: dict) -> list:
    categories = parse_skills(read(REPO_ROOT / "SKILLS.md"))
    flow = section_heading("Skills", styles)
    for category, items in categories:
        line = f"<b>{esc(category)}:</b> {inline(items)}"
        flow.append(Paragraph(line, styles["skill_line"]))
    return flow


def entry_bullets(fields: dict) -> list[str]:
    items = []
    for label in ("Description", "Responsibilities", "Contribution"):
        if fields.get(label):
            items.extend(split_sentences(fields[label]))
    return items


def build_experience(styles: dict) -> list:
    companies = parse_grouped_sections(read(REPO_ROOT / "EXPERIENCE.md"))
    flow = section_heading("Experience", styles)
    for company in companies:
        flow.append(header_date_row(
            Paragraph(esc(company["name"]), styles["entry_title"]),
            company["date_range"], styles,
        ))
        flow.append(Spacer(1, 3))
        for block in company["blocks"]:
            if block.get("Project"):
                flow.append(Paragraph(inline(block["Project"]), styles["entry_sub"]))
            flow.append(bullets(entry_bullets(block), styles))
            if block.get("Technologies"):
                flow.append(Paragraph(f"Stack: {esc(block['Technologies'])}", styles["stack"]))
        flow.append(Spacer(1, 2))
    return flow


def build_projects(styles: dict) -> list:
    projects = parse_flat_blocks(read(REPO_ROOT / "PROJECTS.md"))
    flow = section_heading("Projects", styles)
    for block in projects:
        if block.get("Project"):
            flow.append(Paragraph(inline(block["Project"]), styles["entry_title"]))
        flow.append(bullets(entry_bullets(block), styles))
        if block.get("Technologies"):
            flow.append(Paragraph(f"Stack: {esc(block['Technologies'])}", styles["stack"]))
    return flow


def build_education(styles: dict) -> list:
    institutions = parse_grouped_sections(read(REPO_ROOT / "EDUCATION.md"))
    flow = section_heading("Education", styles)
    for inst in institutions:
        flow.append(header_date_row(
            Paragraph(esc(inst["name"]), styles["entry_title"]),
            inst["date_range"], styles,
        ))
        flow.append(Spacer(1, 3))
        degree_lines = []
        for block in inst["blocks"]:
            degree = block.get("Degree", "")
            faculty = block.get("Faculty", "")
            line = f"{degree} - {faculty}" if degree and faculty else (degree or faculty)
            # A degree's own **Dates** field (for a degree completed in a
            # different period than the institution's other degrees) takes
            # priority over the shared institution-level date line.
            dates = block.get("Dates", "")
            if dates and dates != inst["date_range"]:
                line = f"{line} ({dates})"
            degree_lines.append(line)
        flow.append(bullets(degree_lines, styles))
        flow.append(Spacer(1, 2))
    return flow


def build_certificates(styles: dict) -> list:
    issuers = parse_grouped_sections(read(REPO_ROOT / "CERTIFICATES.md"))
    flow = section_heading("Certificates", styles)
    for issuer in issuers:
        flow.append(header_date_row(
            Paragraph(esc(issuer["name"]), styles["entry_title"]),
            issuer["date_range"], styles,
        ))
        flow.append(Spacer(1, 3))
        cert_lines = []
        for block in issuer["blocks"]:
            name = block.get("Certificate", "")
            skills = block.get("Skills", "")
            line = name if not skills else f"{name} - {skills}"
            if line:
                cert_lines.append(line)
        flow.append(bullets(cert_lines, styles))
        flow.append(Spacer(1, 2))
    return flow


def build_languages(styles: dict) -> list:
    langs = parse_languages(read(REPO_ROOT / "LANGUAGES.md"))
    flow = section_heading("Languages", styles)
    flow.append(Paragraph(inline("  |  ".join(langs)), styles["body"]))
    return flow


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def build_resume(output_path: Path) -> None:
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=1.3 * cm, rightMargin=1.3 * cm,
        topMargin=1.4 * cm, bottomMargin=1.4 * cm,
        title=f"{config.FULL_NAME} - Resume",
    )

    story: list = []
    story += build_header(styles)
    story += build_summary(styles)
    story += build_skills(styles)
    story += build_experience(styles)
    story += build_projects(styles)
    story += build_education(styles)
    story += build_certificates(styles)
    story += build_languages(styles)

    doc.build(story)


OUTPUT_PATH = RESUME_DIR / "output" / "Kusik_Illia_Resume.pdf"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    build_resume(OUTPUT_PATH)
    print(f"Resume written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
