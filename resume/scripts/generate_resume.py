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
from reportlab.graphics.shapes import Circle, Drawing, Group, Path as VectorPath, Polygon
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


# Mail and phone glyph outlines below are traced from Feather Icons
# (mail.svg / phone.svg, MIT licensed, https://github.com/feathericons/feather),
# with the original 24x24 viewBox path/polyline points scaled down to the
# ICON box and y-flipped into ReportLab's bottom-up coordinate space. Drawn
# as thin round-capped strokes (like the source glyphs) rather than filled
# shapes - a previous filled/thick-stroke attempt at this size rendered as
# an unrecognizable solid blob instead of a mail/phone glyph.
_ICON_STROKE_W = 0.65

_MAIL_BODY_POINTS = [1.167, 5.833, 5.833, 5.833, 6.154, 5.833, 6.417, 5.571, 6.417, 5.25, 6.417, 1.75, 6.417, 1.429, 6.154, 1.167, 5.833, 1.167, 1.167, 1.167, 0.846, 1.167, 0.583, 1.429, 0.583, 1.75, 0.583, 5.25, 0.583, 5.571, 0.846, 5.833, 1.167, 5.833]
_MAIL_BODY_OPS = [0, 1, 2, 1, 2, 1, 2, 1, 2, 3]
_MAIL_FLAP_POINTS = [6.417, 5.25, 3.5, 3.208, 0.583, 5.25]

_PHONE_POINTS = [6.417, 2.065, 6.417, 1.19, 6.417, 1.026, 6.349, 0.869, 6.228, 0.758, 6.107, 0.647, 5.944, 0.592, 5.781, 0.607, 4.883, 0.704, 4.021, 1.011, 3.264, 1.502, 2.559, 1.95, 1.962, 2.547, 1.514, 3.252, 1.021, 4.013, 0.714, 4.879, 0.618, 5.781, 0.604, 5.944, 0.658, 6.106, 0.768, 6.227, 0.879, 6.348, 1.035, 6.417, 1.199, 6.417, 2.074, 6.417, 2.367, 6.42, 2.616, 6.205, 2.657, 5.915, 2.694, 5.635, 2.763, 5.36, 2.861, 5.095, 2.941, 4.882, 2.89, 4.642, 2.73, 4.48, 2.36, 4.11, 2.775, 3.379, 3.379, 2.775, 4.11, 2.36, 4.48, 2.73, 4.642, 2.89, 4.882, 2.941, 5.095, 2.861, 5.36, 2.763, 5.635, 2.694, 5.915, 2.657, 6.208, 2.616, 6.424, 2.361, 6.417, 2.065]
_PHONE_OPS = [0, 1, 2, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 1, 2, 1, 2, 2, 2, 3]


def _stroke_path(points: list[float], operators: list[int], color) -> VectorPath:
    path = VectorPath(strokeColor=color, fillColor=None, strokeWidth=_ICON_STROKE_W,
                       strokeLineCap=1, strokeLineJoin=1)
    path.points = points
    path.operators = operators
    return path


def icon_mail() -> Drawing:
    color = colors.HexColor(MUTED_COLOR)
    return _icon([
        _stroke_path(_MAIL_BODY_POINTS, _MAIL_BODY_OPS, color),
        _stroke_path(_MAIL_FLAP_POINTS, [0, 1, 1], color),
    ])


def icon_phone() -> Drawing:
    color = colors.HexColor(MUTED_COLOR)
    return _icon([_stroke_path(_PHONE_POINTS, _PHONE_OPS, color)])


# Brand glyphs below are traced the same way from Simple Icons (CC0 licensed,
# https://github.com/simple-icons/simple-icons), filled solid (like icon_pin)
# rather than stroked, matching each logo's original single-path silhouette.
_GITHUB_POINTS = [3.5, 6.913, 1.566, 6.913, 0.0, 5.346, 0.0, 3.413, 0.0, 1.867, 1.003, 0.555, 2.393, 0.093, 2.568, 0.06, 2.632, 0.168, 2.632, 0.261, 2.632, 0.344, 2.629, 0.564, 2.628, 0.856, 1.654, 0.645, 1.449, 1.326, 1.449, 1.326, 1.29, 1.73, 1.06, 1.837, 1.06, 1.837, 0.743, 2.054, 1.084, 2.05, 1.084, 2.05, 1.436, 2.026, 1.62, 1.69, 1.62, 1.69, 1.932, 1.154, 2.44, 1.309, 2.64, 1.399, 2.671, 1.625, 2.761, 1.779, 2.861, 1.867, 2.084, 1.954, 1.267, 2.255, 1.267, 3.596, 1.267, 3.978, 1.403, 4.29, 1.627, 4.535, 1.588, 4.624, 1.47, 4.98, 1.658, 5.462, 1.658, 5.462, 1.951, 5.556, 2.62, 5.103, 2.9, 5.181, 3.198, 5.219, 3.495, 5.221, 3.793, 5.219, 4.09, 5.181, 4.37, 5.103, 5.035, 5.556, 5.328, 5.462, 5.328, 5.462, 5.517, 4.98, 5.398, 4.624, 5.363, 4.535, 5.587, 4.29, 5.722, 3.978, 5.722, 3.596, 5.722, 2.252, 4.904, 1.956, 4.125, 1.87, 4.248, 1.765, 4.362, 1.55, 4.362, 1.222, 4.362, 0.754, 4.357, 0.377, 4.357, 0.264, 4.357, 0.172, 4.418, 0.062, 4.598, 0.097, 5.998, 0.556, 7.0, 1.869, 7.0, 3.413, 7.0, 5.346, 5.433, 6.913, 3.5, 6.913]
_GITHUB_OPS = [0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3]

# LinkedIn and Spotify each come from Simple Icons as ONE path with several
# subpaths (badge/circle + letterforms/wave strokes) that wind in opposite
# directions - filling the whole thing at once with nonzero-winding (Path's
# default fillMode) punches the letterforms/waves out in white automatically,
# same as the source SVG's own default fill rule. No separate white overlay
# shapes needed.
_LINKEDIN_POINTS = [5.964, 1.035, 4.927, 1.035, 4.927, 2.659, 4.927, 3.046, 4.919, 3.545, 4.387, 3.545, 3.847, 3.545, 3.764, 3.123, 3.764, 2.688, 3.764, 1.035, 2.727, 1.035, 2.727, 4.375, 3.723, 4.375, 3.723, 3.92, 3.737, 3.92, 3.876, 4.182, 4.214, 4.459, 4.719, 4.459, 5.77, 4.459, 5.964, 3.768, 5.964, 2.868, 5.964, 1.035, 1.557, 4.832, 1.223, 4.832, 0.955, 5.102, 0.955, 5.434, 0.955, 5.766, 1.223, 6.036, 1.557, 6.036, 1.889, 6.036, 2.159, 5.766, 2.159, 5.434, 2.159, 5.102, 1.889, 4.832, 1.557, 4.832, 2.076, 1.035, 1.037, 1.035, 1.037, 4.375, 2.076, 4.375, 2.076, 1.035, 6.482, 7.0, 0.517, 7.0, 0.231, 7.0, 0.0, 6.774, 0.0, 6.496, 0.0, 0.504, 0.0, 0.225, 0.231, 0.0, 0.517, 0.0, 6.481, 0.0, 6.767, 0.0, 7.0, 0.225, 7.0, 0.504, 7.0, 6.496, 7.0, 6.774, 6.767, 7.0, 6.481, 7.0, 6.482, 7.0]
_LINKEDIN_OPS = [0, 1, 1, 2, 2, 1, 1, 1, 1, 1, 1, 2, 2, 1, 3, 0, 2, 2, 2, 2, 3, 0, 1, 1, 1, 1, 3, 0, 2, 2, 2, 2, 3]

_SPOTIFY_POINTS = [3.5, 7.0, 1.575, 7.0, 0.0, 5.425, 0.0, 3.5, 0.0, 1.575, 1.575, 0.0, 3.5, 0.0, 5.425, 0.0, 7.0, 1.575, 7.0, 3.5, 7.0, 5.425, 5.443, 7.0, 3.5, 7.0, 5.11, 1.942, 5.04, 1.838, 4.918, 1.802, 4.812, 1.873, 3.99, 2.38, 2.958, 2.485, 1.732, 2.205, 1.61, 2.17, 1.505, 2.257, 1.47, 2.362, 1.435, 2.485, 1.522, 2.59, 1.628, 2.625, 2.958, 2.923, 4.112, 2.8, 5.022, 2.24, 5.145, 2.188, 5.162, 2.048, 5.11, 1.942, 5.53, 2.905, 5.443, 2.782, 5.285, 2.73, 5.162, 2.817, 4.218, 3.395, 2.783, 3.57, 1.68, 3.22, 1.54, 3.185, 1.383, 3.255, 1.348, 3.395, 1.313, 3.535, 1.383, 3.693, 1.523, 3.728, 2.8, 4.112, 4.375, 3.92, 5.46, 3.255, 5.565, 3.202, 5.617, 3.027, 5.53, 2.905, 5.565, 3.885, 4.445, 4.55, 2.573, 4.62, 1.505, 4.287, 1.33, 4.235, 1.155, 4.34, 1.103, 4.497, 1.05, 4.673, 1.155, 4.848, 1.312, 4.9, 2.555, 5.268, 4.603, 5.198, 5.898, 4.428, 6.055, 4.34, 6.108, 4.13, 6.02, 3.972, 5.933, 3.85, 5.723, 3.798, 5.565, 3.885]
_SPOTIFY_OPS = [0, 2, 2, 2, 2, 3, 0, 2, 2, 2, 2, 2, 2, 3, 0, 2, 2, 2, 2, 2, 2, 3, 0, 2, 2, 2, 2, 2, 2, 3]


def _fill_path(points: list[float], operators: list[int], color) -> VectorPath:
    path = VectorPath(fillColor=color, strokeColor=None)
    path.points = points
    path.operators = operators
    return path


def icon_github() -> Drawing:
    color = colors.HexColor(MUTED_COLOR)
    return _icon([_fill_path(_GITHUB_POINTS, _GITHUB_OPS, color)])


def icon_linkedin() -> Drawing:
    color = colors.HexColor(MUTED_COLOR)
    return _icon([_fill_path(_LINKEDIN_POINTS, _LINKEDIN_OPS, color)])


def icon_spotify() -> Drawing:
    color = colors.HexColor(MUTED_COLOR)
    return _icon([_fill_path(_SPOTIFY_POINTS, _SPOTIFY_OPS, color)])


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
        (icon_linkedin(), config.LINKEDIN_LABEL, link(config.LINKEDIN_URL, config.LINKEDIN_LABEL)),
        (icon_github(), config.GITHUB_LABEL, link(config.GITHUB_URL, config.GITHUB_LABEL)),
        (icon_spotify(), config.SPOTIFY_LABEL, link(config.SPOTIFY_URL, config.SPOTIFY_LABEL)),
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
