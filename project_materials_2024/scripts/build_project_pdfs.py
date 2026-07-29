#!/usr/bin/env python3
"""Build the three student-facing HTW Summer School PDFs."""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
DRAFTS = ROOT / "project_materials_2024" / "drafts"
ASSETS = ROOT / "project_materials_2024" / "assets"
OUTPUT = ROOT / "output" / "pdf"

AUTHOR = "Dr. Helio Quintanilha Jr."
ROLE = "Sourcing and Hedging Specialist"
COMPANY = "Ostrom GmbH"
EMAIL = "helio@ostrom.de"
PROJECT = "HTW Summer School Project"
TITLE_MAJOR = "Power Markets"
TITLE_SUBTITLE = "Trading and Hedging a Retail Electricity Portfolio"
TITLE_FULL = f"{TITLE_MAJOR} - {TITLE_SUBTITLE}"
DISCLAIMER = (
    "This simplified educational exercise includes constructed scenario assumptions. "
    "It does not represent an executable historical trading strategy or financial, "
    "trading, or risk-management advice."
)

NAVY = HexColor("#0D3658")
TEAL = HexColor("#168E91")
AMBER = HexColor("#F2A640")
CORAL = HexColor("#E6755B")
CREAM = HexColor("#FFF8EA")
PALE_TEAL = HexColor("#E9F4F3")
PALE_AMBER = HexColor("#FFF0D2")
GRID = HexColor("#C7D5D8")
SLATE = HexColor("#4E626E")
LIGHT_TEXT = HexColor("#6D7D85")

PAGE_W, PAGE_H = A4
LEFT = 19 * mm
RIGHT = 19 * mm
TOP = 20 * mm
BOTTOM = 18 * mm
FRAME_W = PAGE_W - LEFT - RIGHT


def register_fonts() -> tuple[str, str, str, str]:
    """Use Aptos when available; otherwise use built-in Helvetica."""

    font_candidates = [
        (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
        ),
        (
            "/Library/Fonts/Arial.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/Library/Fonts/Arial Italic.ttf",
            "/Library/Fonts/Arial Bold Italic.ttf",
        ),
    ]
    for regular, bold, italic, bold_italic in font_candidates:
        paths = [Path(regular), Path(bold), Path(italic), Path(bold_italic)]
        if all(path.exists() for path in paths):
            pdfmetrics.registerFont(TTFont("ProjectSans", regular))
            pdfmetrics.registerFont(TTFont("ProjectSans-Bold", bold))
            pdfmetrics.registerFont(TTFont("ProjectSans-Italic", italic))
            pdfmetrics.registerFont(TTFont("ProjectSans-BoldItalic", bold_italic))
            pdfmetrics.registerFontFamily(
                "ProjectSans",
                normal="ProjectSans",
                bold="ProjectSans-Bold",
                italic="ProjectSans-Italic",
                boldItalic="ProjectSans-BoldItalic",
            )
            return (
                "ProjectSans",
                "ProjectSans-Bold",
                "ProjectSans-Italic",
                "ProjectSans-BoldItalic",
            )
    return ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique")


FONT, FONT_BOLD, FONT_ITALIC, FONT_BOLD_ITALIC = register_fonts()


def register_math_font() -> str:
    """Register a serif italic font for textbook-style equations."""

    candidates = [
        Path("/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf"),
        Path("/Library/Fonts/Times New Roman Italic.ttf"),
    ]
    for path in candidates:
        if path.exists():
            pdfmetrics.registerFont(TTFont("ProjectMath", str(path)))
            return "ProjectMath"
    return "Times-Italic"


MATH_FONT = register_math_font()


def make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "cover_kicker",
            parent=base["Normal"],
            fontName=FONT_BOLD,
            fontSize=9,
            leading=11,
            textColor=TEAL,
            tracking=1.2,
            alignment=TA_CENTER,
            spaceAfter=5 * mm,
        ),
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName=FONT_BOLD,
            fontSize=29,
            leading=32,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=3 * mm,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=15,
            leading=19,
            textColor=SLATE,
            alignment=TA_CENTER,
            spaceAfter=8 * mm,
        ),
        "cover_tagline": ParagraphStyle(
            "cover_tagline",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=10.3,
            leading=14.2,
            textColor=SLATE,
            alignment=TA_CENTER,
            leftIndent=18 * mm,
            rightIndent=18 * mm,
            spaceBefore=5 * mm,
        ),
        "abstract_title": ParagraphStyle(
            "abstract_title",
            parent=base["Title"],
            fontName=FONT_BOLD,
            fontSize=25,
            leading=28,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=1.5 * mm,
        ),
        "abstract_subtitle": ParagraphStyle(
            "abstract_subtitle",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=13,
            leading=16,
            textColor=TEAL,
            alignment=TA_LEFT,
            spaceAfter=3 * mm,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=7.8,
            leading=10,
            textColor=LIGHT_TEXT,
            alignment=TA_LEFT,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName=FONT_BOLD,
            fontSize=14,
            leading=17,
            textColor=NAVY,
            spaceBefore=5 * mm,
            spaceAfter=2.5 * mm,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontName=FONT_BOLD,
            fontSize=10.2,
            leading=12.5,
            textColor=TEAL,
            spaceBefore=3.5 * mm,
            spaceAfter=1.5 * mm,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=8.7,
            leading=11.7,
            textColor=colors.HexColor("#233741"),
            spaceAfter=2.2 * mm,
            allowWidows=0,
            allowOrphans=0,
        ),
        "body_compact": ParagraphStyle(
            "body_compact",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=8.5,
            leading=10.9,
            textColor=colors.HexColor("#233741"),
            spaceAfter=1.3 * mm,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=8.5,
            leading=11.2,
            textColor=colors.HexColor("#233741"),
        ),
        "table": ParagraphStyle(
            "table",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=7.2,
            leading=9,
            textColor=colors.HexColor("#233741"),
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=base["BodyText"],
            fontName=FONT_BOLD,
            fontSize=7.2,
            leading=9,
            textColor=colors.white,
        ),
        "code": ParagraphStyle(
            "code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.35,
            leading=9.7,
            textColor=NAVY,
            leftIndent=0,
        ),
        "quote": ParagraphStyle(
            "quote",
            parent=base["BodyText"],
            fontName=FONT_BOLD,
            fontSize=9.5,
            leading=13,
            textColor=NAVY,
            leftIndent=2 * mm,
            rightIndent=2 * mm,
            spaceAfter=0,
        ),
        "equation": ParagraphStyle(
            "equation",
            parent=base["Normal"],
            fontName=MATH_FONT,
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#1F2D34"),
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
        "table_math": ParagraphStyle(
            "table_math",
            parent=base["BodyText"],
            fontName=MATH_FONT,
            fontSize=7.8,
            leading=9.5,
            textColor=colors.HexColor("#233741"),
        ),
        "reference": ParagraphStyle(
            "reference",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=7.4,
            leading=9.5,
            textColor=colors.HexColor("#334A55"),
            spaceAfter=1.5 * mm,
        ),
        "list_marker": ParagraphStyle(
            "list_marker",
            parent=base["BodyText"],
            fontName=FONT_BOLD,
            fontSize=7.5,
            leading=11.2,
            textColor=TEAL,
            alignment=TA_LEFT,
        ),
        "cover_disclaimer": ParagraphStyle(
            "cover_disclaimer",
            parent=base["Normal"],
            fontName=FONT_ITALIC,
            fontSize=7.4,
            leading=9.8,
            textColor=LIGHT_TEXT,
            alignment=TA_CENTER,
            leftIndent=17 * mm,
            rightIndent=17 * mm,
            spaceBefore=4 * mm,
        ),
    }


STYLES = make_styles()


def normalize_text(text: str) -> str:
    replacements = {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def inline_markup(text: str) -> str:
    text = normalize_text(text.strip())
    text = escape(text)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        lambda match: (
            f'<link href="{match.group(2)}" color="#334A55">'
            f"{match.group(1)}</link>"
        ),
        text,
    )
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    return text


GLOSSARY_SYMBOL_MARKUP = {
    "p, t, τ, j, b": "p, t, τ, j, b",
    "E_p, n_p, e_p": (
        "E<sub>p</sub>, n<sub>p</sub>, e<sub>p</sub>"
    ),
    "s_p,t, L_p,t, L_t": (
        "s<sub>p,t</sub>, L<sub>p,t</sub>, L<sub>t</sub>"
    ),
    "P_base, P_peak, P_off, P_slice": (
        "P<sub>base</sub>, P<sub>peak</sub>, "
        "P<sub>off</sub>, P<sub>slice</sub>"
    ),
    "N_all, N_peak, N_off": (
        "N<sub>all</sub>, N<sub>peak</sub>, N<sub>off</sub>"
    ),
    "s_t, mean_slice(s), HPFC_t": (
        "s<sub>t</sub>, mean<sub>slice</sub>(s), HPFC<sub>t</sub>"
    ),
    "Δt, x_j, D_j,t, H_t": (
        "Δt, x<sub>j</sub>, D<sub>j,t</sub>, H<sub>t</sub>"
    ),
    "R_t^DA, P_t^DA": (
        "R<sub>t</sub><super>DA</super>, "
        "P<sub>t</sub><super>DA</super>"
    ),
    "A_t, I_t, P_t^imb": (
        "A<sub>t</sub>, I<sub>t</sub>, "
        "P<sub>t</sub><super>imb</super>"
    ),
    "C_futures, C_forecast": (
        "C<sub>futures</sub>, C<sub>forecast</sub>"
    ),
    "C_residual^DA, C_imb, C_final": (
        "C<sub>residual</sub><super>DA</super>, "
        "C<sub>imb</sub>, C<sub>final</sub>"
    ),
    "Π_futures, Premium_imb, Saving": (
        "Π<sub>futures</sub>, Premium<sub>imb</sub>, Saving"
    ),
}


def glossary_symbol_markup(text: str) -> str:
    clean = normalize_text(text).replace("*", "").strip()
    return GLOSSARY_SYMBOL_MARKUP.get(clean, escape(clean))


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def table_widths(rows: list[list[str]], available: float) -> list[float]:
    column_count = len(rows[0])
    lengths = []
    for index in range(column_count):
        longest = max(len(re.sub(r"[`*]", "", row[index])) for row in rows)
        lengths.append(max(8, min(longest, 45)))
    total = sum(lengths)
    widths = [available * length / total for length in lengths]
    minimum = 27 * mm if column_count <= 3 else 20 * mm
    for _ in range(3):
        deficits = [max(0, minimum - width) for width in widths]
        required = sum(deficits)
        if required <= 0:
            break
        donor_total = sum(max(0, width - minimum) for width in widths)
        if donor_total <= 0:
            break
        widths = [
            minimum if width < minimum else width - required * (width - minimum) / donor_total
            for width in widths
        ]
    scale = available / sum(widths)
    return [width * scale for width in widths]


def make_table(rows: list[list[str]]) -> Table:
    is_glossary = (
        len(rows[0]) == 3
        and rows[0][0].strip().lower() == "symbol(s)"
    )
    rendered = []
    for row_index, row in enumerate(rows):
        rendered_row = []
        for column_index, cell in enumerate(row):
            if row_index == 0:
                rendered_row.append(
                    Paragraph(inline_markup(cell), STYLES["table_header"])
                )
            elif is_glossary and column_index == 0:
                rendered_row.append(
                    Paragraph(glossary_symbol_markup(cell), STYLES["table_math"])
                )
            else:
                rendered_row.append(
                    Paragraph(inline_markup(cell), STYLES["table"])
                )
        rendered.append(rendered_row)
    if len(rows[0]) == 3 and rows[0][0].strip().lower() == "file":
        widths = [FRAME_W * 0.24, FRAME_W * 0.40, FRAME_W * 0.36]
    elif is_glossary:
        widths = [FRAME_W * 0.30, FRAME_W * 0.50, FRAME_W * 0.20]
    else:
        widths = table_widths(rows, FRAME_W)
    table = Table(
        rendered,
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
        spaceBefore=1.5 * mm,
        spaceAfter=3 * mm,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.35, GRID),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_TEAL]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def make_code_block(text: str) -> Table:
    equation = equation_markup_for(text)
    if equation:
        return make_equation_block(equation)

    code = Preformatted(normalize_text(text.rstrip()), STYLES["code"])
    block = Table([[code]], colWidths=[FRAME_W - 5 * mm], hAlign="LEFT")
    block.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE_TEAL),
                ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    block.spaceBefore = 1 * mm
    block.spaceAfter = 3 * mm
    block._is_code_block = True
    return block


def equation_markup_for(text: str) -> str | None:
    """Translate the mathematical code blocks into compact typeset notation."""

    compact = " ".join(normalize_text(text).split())
    # Check the most specific expressions first because several formulas reuse
    # terms such as forecast_load, hedge_energy, and imbalance_volume.
    if compact.startswith("final procurement cost"):
        return (
            "C<sub>final</sub> = C<sub>futures</sub> + "
            "C<sub>residual</sub><super>DA</super> + C<sub>imb</sub>"
        )
    if compact.startswith("saving versus unhedged"):
        return (
            "Saving = C<sub>final</sub><super>unhedged</super> - "
            "C<sub>final</sub><super>strategy</super>"
        )
    if compact.startswith("imbalance premium"):
        return (
            "Premium<sub>imb</sub> = Σ<sub>t</sub> I<sub>t</sub> * "
            "(P<sub>t</sub><super>imb</super> - P<sub>t</sub><super>DA</super>)"
        )
    if compact.startswith("imbalance settlement"):
        return (
            "C<sub>imb</sub> = "
            "Σ<sub>t</sub> I<sub>t</sub> * P<sub>t</sub><super>imb</super>"
        )
    if compact.startswith("forecast procurement cost = fixed futures cost"):
        return (
            "C<sub>forecast</sub> = C<sub>futures</sub> + "
            "Σ<sub>t</sub> R<sub>t</sub><super>DA</super> * "
            "P<sub>t</sub><super>DA</super>"
        )
    if compact.startswith("forecast procurement cost = full forecast load"):
        return (
            "C<sub>forecast</sub> = "
            "Σ<sub>t</sub> L<sub>t</sub> * P<sub>t</sub><super>DA</super> - "
            "Π<sub>futures</sub>"
        )
    if compact.startswith("minimize"):
        return (
            "min<sub>x</sub> Σ<sub>t</sub> "
            "(L<sub>t</sub> - H<sub>t</sub>)<super>2</super>"
        )
    if compact.startswith("sum over t in b of hedge_energy"):
        return (
            "Σ<sub>t in b</sub> H<sub>t</sub> * HPFC<sub>t</sub> = "
            "Σ<sub>t in b</sub> L<sub>t</sub> * HPFC<sub>t</sub>"
        )
    if "total_forecast_load[t]" in compact:
        return "L<sub>t</sub> = Σ<sub>p</sub> L<sub>p,t</sub>"
    if "forecast_load[p,t]" in compact:
        return (
            "L<sub>p,t</sub> = E<sub>p</sub> * "
            "s<sub>p,t</sub> / "
            "(Σ<sub>τ</sub> s<sub>p,τ</sub>)"
        )
    if "annual_portfolio_energy[p]" in compact:
        return "E<sub>p</sub> = n<sub>p</sub> * e<sub>p</sub>"
    if compact.startswith("P_base * N_all"):
        return (
            "P<sub>base</sub> * N<sub>all</sub> = "
            "P<sub>peak</sub> * N<sub>peak</sub> + "
            "P<sub>off</sub> * N<sub>off</sub>"
        )
    if compact.startswith("P_off"):
        return (
            "P<sub>off</sub> = "
            "(P<sub>base</sub> * N<sub>all</sub> - "
            "P<sub>peak</sub> * N<sub>peak</sub>) / "
            "N<sub>off</sub>"
        )
    if "HPFC[t]" in compact:
        return (
            "HPFC<sub>t</sub> = P<sub>slice</sub> * "
            "s<sub>t</sub> / mean<sub>slice</sub>(s)"
        )
    if "day_ahead_residual[t]" in compact:
        return "R<sub>t</sub><super>DA</super> = L<sub>t</sub> - H<sub>t</sub>"
    if "hedge_energy[t]" in compact:
        return (
            "H<sub>t</sub> = Δt * Σ<sub>j</sub> "
            "x<sub>j</sub> * D<sub>j,t</sub>, "
            "with Δt = 0.25 h"
        )
    if "position_mw[j] >= 0" in compact:
        return "x<sub>j</sub> ≥ 0"
    if "imbalance_volume[t]" in compact:
        return "I<sub>t</sub> = A<sub>t</sub> - L<sub>t</sub>"
    return None


def make_equation_block(markup: str) -> Table:
    """Render a centered serif equation, matching the visual language of the xVA brief."""

    block = Table(
        [[Paragraph(markup, STYLES["equation"])]],
        colWidths=[FRAME_W - 12 * mm],
        hAlign="CENTER",
    )
    block.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    block.spaceBefore = 0.5 * mm
    block.spaceAfter = 2.5 * mm
    block._is_code_block = True
    return block


def make_quote(text: str) -> Table:
    quote = Table([[Paragraph(inline_markup(text), STYLES["quote"])]], colWidths=[FRAME_W])
    quote.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE_AMBER),
                ("LINEBEFORE", (0, 0), (0, -1), 3, AMBER),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    quote.spaceBefore = 2 * mm
    quote.spaceAfter = 3 * mm
    return quote


def make_list(items: list[str], ordered: bool) -> Table:
    """Use a two-column table so markers stay inside the body margin."""

    rows = []
    for index, item in enumerate(items, start=1):
        marker = f"{index}." if ordered else "•"
        marker_style = ParagraphStyle(
            f"list_marker_{'ordered' if ordered else 'bullet'}",
            parent=STYLES["list_marker"],
            textColor=NAVY if ordered else TEAL,
        )
        rows.append(
            [
                Paragraph(marker, marker_style),
                Paragraph(inline_markup(item), STYLES["bullet"]),
            ]
        )
    table = Table(
        rows,
        colWidths=[6 * mm, FRAME_W - 6 * mm],
        hAlign="LEFT",
        spaceBefore=0.5 * mm,
        spaceAfter=1.5 * mm,
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
            ]
        )
    )
    table._is_list = True
    return table


def url_from_line(line: str) -> str | None:
    direct = re.fullmatch(r"<(https?://[^>]+)>", line)
    if direct:
        return direct.group(1)
    markdown = re.fullmatch(r"\[[^\]]+\]\((https?://.*)\)", line)
    if markdown:
        return markdown.group(1)
    return None


def bind_formula_introductions(flowables: list) -> list:
    bound = []
    index = 0
    while index < len(flowables):
        current = flowables[index]
        following = flowables[index + 1] if index + 1 < len(flowables) else None
        follows_bound_block = (
            getattr(following, "_is_code_block", False)
            or getattr(following, "_is_list", False)
        )
        if (
            isinstance(current, Paragraph)
            and current.getPlainText().rstrip().endswith(":")
            and follows_bound_block
        ):
            bound.append(KeepTogether([current, following]))
            index += 2
            continue
        bound.append(current)
        index += 1
    return bound


def markdown_to_flowables(lines: list[str], compact: bool = False) -> list:
    flowables: list = []
    index = 0
    body_style = STYLES["body_compact"] if compact else STYLES["body"]
    while index < len(lines):
        raw = lines[index].rstrip()
        stripped = raw.strip()
        if not stripped:
            index += 1
            continue

        if stripped.startswith("```"):
            index += 1
            code_lines = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index].rstrip())
                index += 1
            index += 1
            flowables.append(make_code_block("\n".join(code_lines)))
            continue

        if stripped.startswith("### "):
            if stripped == "### Exhibit 4 - Realised market prices":
                flowables.append(PageBreak())
            if stripped == "### 5.3 Check the hedge":
                flowables.append(PageBreak())
            flowables.append(Paragraph(inline_markup(stripped[4:]), STYLES["h3"]))
            index += 1
            continue

        if stripped.startswith("## "):
            if stripped == "## 3. Your manager's briefing":
                flowables.append(PageBreak())
            if stripped == "## 2. Strategies to evaluate":
                flowables.append(PageBreak())
            if stripped == "## 11. Deliverables and evidence":
                flowables.append(PageBreak())
            flowables.append(Paragraph(inline_markup(stripped[3:]), STYLES["h2"]))
            index += 1
            continue

        if stripped.startswith("# "):
            index += 1
            continue

        if stripped.startswith("> "):
            quote_lines = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip().lstrip(">").strip())
                index += 1
            flowables.append(make_quote(" ".join(quote_lines)))
            continue

        if stripped.startswith("|"):
            table_rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = split_table_row(lines[index])
                if not is_table_separator(cells):
                    table_rows.append(cells)
                index += 1
            if table_rows:
                flowables.append(make_table(table_rows))
            continue

        bullet_match = re.match(r"^-\s+(.*)$", stripped)
        if bullet_match:
            items = []
            while index < len(lines):
                match = re.match(r"^-\s+(.*)$", lines[index].strip())
                if not match:
                    break
                items.append(match.group(1))
                index += 1
            flowables.append(make_list(items, ordered=False))
            continue

        ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ordered_match:
            items = []
            while index < len(lines):
                match = re.match(r"^\d+\.\s+(.*)$", lines[index].strip())
                if not match:
                    break
                items.append(match.group(1))
                index += 1
            flowables.append(make_list(items, ordered=True))
            continue

        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if not candidate:
                break
            if (
                candidate.startswith(("#", "```", ">", "|", "- "))
                or re.match(r"^\d+\.\s+", candidate)
                or url_from_line(candidate)
            ):
                break
            paragraph_lines.append(candidate)
            index += 1
        paragraph = " ".join(paragraph_lines)

        linked_url = None
        if index < len(lines):
            next_line = lines[index].strip()
            linked_url = url_from_line(next_line)
        if linked_url:
            url = escape(linked_url, {'"': "&quot;"})
            paragraph = (
                f'<link href="{url}" color="#334A55">'
                f"{inline_markup(paragraph)}</link>"
            )
            style = STYLES["reference"]
            index += 1
        else:
            paragraph = inline_markup(paragraph)
            style = body_style

        if paragraph.startswith("Note:"):
            paragraph = f"<b>Note:</b>{paragraph[5:]}"
        flowables.append(Paragraph(paragraph, style))

    return bind_formula_introductions(flowables)


def document_content(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    email_index = next(i for i, line in enumerate(lines) if EMAIL in line)
    return lines[email_index + 1 :]


def draw_cover_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(1.2)
    canvas.line(LEFT, 13 * mm, PAGE_W - RIGHT, 13 * mm)
    canvas.setFont(FONT, 7.5)
    canvas.setFillColor(LIGHT_TEXT)
    canvas.drawString(LEFT, 8.5 * mm, PROJECT)
    canvas.drawRightString(PAGE_W - RIGHT, 8.5 * mm, COMPANY)
    canvas.restoreState()


def draw_content_page(canvas, doc, short_title: str) -> None:
    canvas.saveState()
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(0.8)
    canvas.line(LEFT, PAGE_H - 12.5 * mm, PAGE_W - RIGHT, PAGE_H - 12.5 * mm)
    canvas.setFont(FONT_BOLD, 7.2)
    canvas.setFillColor(NAVY)
    canvas.drawString(LEFT, PAGE_H - 9.5 * mm, "POWER MARKETS")
    canvas.setFont(FONT, 7.2)
    canvas.setFillColor(LIGHT_TEXT)
    canvas.drawRightString(PAGE_W - RIGHT, PAGE_H - 9.5 * mm, short_title.upper())

    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.5)
    canvas.line(LEFT, 12.5 * mm, PAGE_W - RIGHT, 12.5 * mm)
    canvas.setFont(FONT, 7)
    canvas.setFillColor(LIGHT_TEXT)
    canvas.drawString(LEFT, 8.5 * mm, f"{AUTHOR} | {COMPANY}")
    canvas.drawCentredString(PAGE_W / 2, 8.5 * mm, EMAIL)
    canvas.drawRightString(PAGE_W - RIGHT, 8.5 * mm, str(doc.page))
    canvas.restoreState()


def cover_story(label: str, image_path: Path, tagline: str) -> list:
    image_size = 107 * mm
    return [
        Spacer(1, 7 * mm),
        Paragraph(label.upper(), STYLES["cover_kicker"]),
        Paragraph(TITLE_MAJOR, STYLES["cover_title"]),
        Paragraph(TITLE_SUBTITLE, STYLES["cover_subtitle"]),
        HRFlowable(
            width="30%",
            thickness=2.2,
            color=AMBER,
            spaceBefore=0,
            spaceAfter=8 * mm,
            hAlign="CENTER",
        ),
        Image(str(image_path), width=image_size, height=image_size, hAlign="CENTER"),
        Paragraph(tagline, STYLES["cover_tagline"]),
        Spacer(1, 5 * mm),
        Paragraph(
            f"<b>{AUTHOR}</b><br/>{ROLE}<br/>{COMPANY}<br/>{EMAIL}",
            ParagraphStyle(
                "cover_author",
                parent=STYLES["meta"],
                alignment=TA_CENTER,
                fontSize=8.2,
                leading=11,
                textColor=SLATE,
            ),
        ),
        Paragraph(f"<b>Disclaimer:</b> {DISCLAIMER}", STYLES["cover_disclaimer"]),
        PageBreak(),
    ]


def build_abstract() -> Path:
    source = DRAFTS / "01_project_abstract_and_literature.md"
    destination = OUTPUT / "Power_Markets_Abstract_and_Literature.pdf"
    content = document_content(source)
    doc = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        leftMargin=LEFT,
        rightMargin=RIGHT,
        topMargin=15 * mm,
        bottomMargin=17 * mm,
        title=TITLE_FULL,
        author=AUTHOR,
        subject="HTW Summer School project abstract and literature",
    )
    story = [
        Paragraph(PROJECT.upper(), STYLES["cover_kicker"]),
        Paragraph(TITLE_MAJOR, STYLES["abstract_title"]),
        Paragraph(TITLE_SUBTITLE, STYLES["abstract_subtitle"]),
        Paragraph(
            f"{AUTHOR} | {ROLE} | {COMPANY} | {EMAIL}",
            STYLES["meta"],
        ),
        HRFlowable(
            width="100%",
            thickness=1.1,
            color=TEAL,
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
        ),
    ]
    story.extend(markdown_to_flowables(content, compact=True))
    doc.build(
        story,
        onFirstPage=lambda canvas, current_doc: draw_content_page(
            canvas, current_doc, "Abstract and literature"
        ),
        onLaterPages=lambda canvas, current_doc: draw_content_page(
            canvas, current_doc, "Abstract and literature"
        ),
    )
    return destination


def build_with_cover(
    source_name: str,
    output_name: str,
    label: str,
    cover_image: str,
    tagline: str,
    short_title: str,
) -> Path:
    source = DRAFTS / source_name
    destination = OUTPUT / output_name
    doc = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        leftMargin=LEFT,
        rightMargin=RIGHT,
        topMargin=19 * mm,
        bottomMargin=18 * mm,
        title=f"{TITLE_FULL} - {label.title()}",
        author=AUTHOR,
        subject=f"HTW Summer School {label.lower()}",
    )
    story = cover_story(label, ASSETS / cover_image, tagline)
    story.extend(markdown_to_flowables(document_content(source)))
    doc.build(
        story,
        onFirstPage=draw_cover_footer,
        onLaterPages=lambda canvas, current_doc: draw_content_page(
            canvas, current_doc, short_title
        ),
    )
    return destination


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    outputs = [
        build_abstract(),
        build_with_cover(
            "02_data_description.md",
            "Power_Markets_Data_Description.pdf",
            "Data Description",
            "data_cover_chart_v1.png",
            (
                "Customer profiles, futures, historical price shapes, "
                "Day-Ahead prices and imbalance data for the 2024 case."
            ),
            "Data description",
        ),
        build_with_cover(
            "03_main_project_brief.md",
            "Power_Markets_Main_Project_Brief.pdf",
            "Main Project Brief",
            "main_cover_trader_v1.png",
            (
                "Build the portfolio and HPFC, design the hedge, "
                "manage delivery and advise the trading desk."
            ),
            "Main project brief",
        ),
    ]
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
