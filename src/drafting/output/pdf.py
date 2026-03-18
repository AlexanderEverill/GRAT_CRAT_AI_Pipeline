"""Styled PDF export for client-facing drafting artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from loaders.client_profile import ClientProfile


PAGE_WIDTH = 595.0
PAGE_HEIGHT = 842.0
MARGIN_X = 52.0
TOP_MARGIN = 54.0
BOTTOM_MARGIN = 52.0
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN_X)

COLOR_NAVY = (24, 44, 76)
COLOR_BLUE = (43, 89, 163)
COLOR_GOLD = (197, 161, 76)
COLOR_INK = (37, 43, 52)
COLOR_MUTED = (96, 109, 126)
COLOR_PANEL = (246, 244, 238)
COLOR_RULE = (215, 220, 228)

SECTION_IGNORES = {"Generation Metadata", "Table of Contents"}

_INLINE_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
_MARKER_PATTERN = re.compile(r"[*_`]")
_INLINE_CITE_PATTERN = re.compile(
    r"\s*\(S\d{3},\s*https?://[^,]+,\s*n\.d\.\)"
)

_SOURCE_LABELS: dict[str, str] = {
    "S001": "IRC \u00a72702 \u2014 Special valuation rules",
    "S002": "26 CFR 25.2702-3 \u2014 Special valuation rules for GRATs",
    "S003": "IRC \u00a7664 \u2014 Charitable remainder trusts",
    "S004": "26 CFR 1.664-2 \u2014 Charitable remainder annuity trust",
    "S005": "IRC \u00a72501 \u2014 Imposition of gift tax",
    "S006": "IRC \u00a72033 \u2014 Property in which decedent had an interest",
    "S007": "IRC \u00a77520 \u2014 Valuation tables",
    "S008": "IRC \u00a7671 \u2014 Grantor trust rules",
    "S009": "IRC \u00a7170 \u2014 Charitable contributions deduction",
    "S010": "IRS \u2014 Estate tax overview",
    "S011": "31 CFR Part 10 \u2014 Circular 230",
}

_SOURCE_URLS: dict[str, str] = {
    "S001": "https://www.law.cornell.edu/uscode/text/26/2702",
    "S002": "https://www.law.cornell.edu/cfr/text/26/25.2702-3",
    "S003": "https://www.law.cornell.edu/uscode/text/26/664",
    "S004": "https://www.law.cornell.edu/cfr/text/26/1.664-2",
    "S005": "https://www.law.cornell.edu/uscode/text/26/2501",
    "S006": "https://www.law.cornell.edu/uscode/text/26/2033",
    "S007": "https://www.law.cornell.edu/uscode/text/26/7520",
    "S008": "https://www.law.cornell.edu/uscode/text/26/671",
    "S009": "https://www.law.cornell.edu/uscode/text/26/170",
    "S010": "https://www.irs.gov/businesses/small-businesses-self-employed/estate-tax",
    "S011": "https://www.law.cornell.edu/cfr/text/31/part-10",
}


@dataclass(frozen=True)
class ReportSection:
    title: str
    lines: list[str]


def _sanitize_text(value: str) -> str:
    cleaned = value.replace("\u2013", "-").replace("\u2014", "-")
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\u2022", "-")
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = cleaned.replace("\u00a7\u00a7", "").replace("§§", "")
    return cleaned.encode("latin-1", "replace").decode("latin-1")


def _escape_pdf_text(value: str) -> str:
    return (
        _sanitize_text(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def _strip_inline_markdown(value: str) -> str:
    linked = _INLINE_LINK_PATTERN.sub(r"\1", value)
    return _MARKER_PATTERN.sub("", linked).strip()


def _estimate_text_width(text: str, font_size: float) -> float:
    width_units = 0.0
    for char in text:
        if char == " ":
            width_units += 0.33
        elif char in "il.,:;|![]()'`":
            width_units += 0.26
        elif char in "MW@#%&":
            width_units += 0.9
        elif char.isupper():
            width_units += 0.64
        elif char.isdigit():
            width_units += 0.56
        else:
            width_units += 0.52
    return width_units * font_size


def _wrap_text(text: str, max_width: float, font_size: float) -> list[str]:
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _estimate_text_width(candidate, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _format_color(rgb: tuple[int, int, int]) -> str:
    return " ".join(f"{channel / 255:.3f}" for channel in rgb)


def _format_currency_short(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "n/a"
    absolute = abs(float(value))
    sign = "-" if value < 0 else ""
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{sign}${absolute / 1_000:.0f}K"
    return f"{sign}${absolute:,.0f}"


def _today_text() -> str:
    return datetime.now(timezone.utc).strftime("%d %b %Y")


def _truncate_to_width(text: str, max_width: float, font_size: float) -> str:
    """Truncate text to fit within max_width, adding '..' if needed."""
    if _estimate_text_width(text, font_size) <= max_width:
        return text
    while len(text) > 1 and _estimate_text_width(text + "..", font_size) > max_width:
        text = text[:-1]
    return text + ".."


def _client_snapshot_lines(client_profile: ClientProfile) -> list[str]:
    demographics = client_profile.extra.get("client_demographics", {})
    liquidity_event = client_profile.extra.get("liquidity_event", {})
    estate_context = client_profile.extra.get("estate_tax_context_2015", {})

    age = demographics.get("age", "n/a")
    marital_status = demographics.get("marital_status", "n/a")
    children = demographics.get("children", {}).get("details", "n/a")
    proceeds = _format_currency_short(liquidity_event.get("gross_proceeds_usd"))
    year = liquidity_event.get("year", "n/a")
    top_rate = estate_context.get("top_estate_tax_rate")
    top_rate_text = "n/a"
    if isinstance(top_rate, (int, float)) and not isinstance(top_rate, bool):
        top_rate_text = f"{top_rate * 100:.0f}%"

    return [
        f"Age: {age}",
        f"Marital status: {marital_status}",
        f"Children: {children}",
        f"Liquidity event: {year}, {proceeds}",
        f"Estate tax rate: {top_rate_text}",
        f"Horizon: {client_profile.horizon} years",
    ]


def _objective_lines(client_profile: ClientProfile) -> list[str]:
    goals = [goal.strip() for goal in client_profile.goals if isinstance(goal, str) and goal.strip()]
    constraints = client_profile.extra.get("constraints", [])
    lines = goals[:]
    for constraint in constraints:
        if isinstance(constraint, str) and constraint.strip():
            lines.append(constraint.strip())
    return lines


def _summary_lines(draft_manifest: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(draft_manifest, Mapping):
        return []

    summary = draft_manifest.get("summary")
    if not isinstance(summary, Mapping):
        return []

    numeric_payload = summary.get("numeric_placeholders")
    numeric_line = "Numeric bindings: n/a"
    if isinstance(numeric_payload, Mapping):
        total = numeric_payload.get("total")
        bound = numeric_payload.get("bound")
        if isinstance(total, int) and isinstance(bound, int):
            numeric_line = f"Numeric bindings: {bound}/{total}"

    warnings = summary.get("validation_warnings")
    warnings_text = str(warnings) if warnings is not None else "n/a"

    return [
        f"Sections drafted: {summary.get('sections_written', 'n/a')}",
        f"Validation warnings: {warnings_text}",
        numeric_line,
    ]


_SUPERSCRIPT_DIGITS = "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"


def _to_superscript(n: int) -> str:
    if n < 0:
        return str(n)
    return "".join(_SUPERSCRIPT_DIGITS[int(d)] for d in str(n))


def _extract_footnotes(text: str, footnotes: dict[str, int]) -> tuple[str, dict[str, int]]:
    """Remove inline citations, assign footnote numbers, return cleaned text."""
    cite_re = re.compile(r"\s*\((S\d{3}),\s*https?://[^,]+,\s*n\.d\.\)")
    for m in cite_re.finditer(text):
        source_id = m.group(1)
        if source_id not in footnotes:
            footnotes[source_id] = len(footnotes) + 1

    def _replacer(m: re.Match) -> str:
        source_id = m.group(1)
        idx = footnotes[source_id]
        return _to_superscript(idx)
    result = cite_re.sub(_replacer, text)
    return result, footnotes


def _extract_report_sections(markdown: str) -> tuple[list[ReportSection], list[str]]:
    sections: list[ReportSection] = []
    references: list[str] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines, references
        if current_title is None:
            return

        cleaned_lines: list[str] = []
        skipping_references = False
        for raw_line in current_lines:
            stripped = raw_line.strip()
            if stripped == "### References":
                skipping_references = True
                continue
            if skipping_references:
                if stripped.startswith("- ") or not stripped:
                    continue
                skipping_references = False
            cleaned_lines.append(raw_line)

        if current_title in SECTION_IGNORES:
            pass
        elif current_title == "Global References":
            references = [
                _strip_inline_markdown(line[2:].strip())
                for line in current_lines
                if line.strip().startswith("- ")
            ]
        else:
            sections.append(ReportSection(title=current_title, lines=cleaned_lines))

        current_title = None
        current_lines = []

    for line in markdown.splitlines():
        if line.startswith("## "):
            flush()
            current_title = _strip_inline_markdown(line[3:].strip())
            current_lines = []
            continue
        if current_title is None:
            continue
        current_lines.append(line)
    flush()

    return sections, references


class _PdfCanvas:
    def __init__(self, title: str) -> None:
        self.title = _sanitize_text(title)
        self._page_commands: list[str] | None = None
        self._pages: list[str] = []
        self.page_number = 0
        self.y = TOP_MARGIN

    def add_page(self) -> None:
        if self._page_commands is not None:
            self._finalize_page()
        self.page_number += 1
        self._page_commands = []
        self.y = TOP_MARGIN

    def ensure_space(self, height: float) -> None:
        if self._page_commands is None:
            self.add_page()
        if self.y + height > PAGE_HEIGHT - BOTTOM_MARGIN:
            self.add_page()

    def rect(
        self,
        x: float,
        y_top: float,
        width: float,
        height: float,
        *,
        fill: tuple[int, int, int] | None = None,
        stroke: tuple[int, int, int] | None = None,
        line_width: float = 1.0,
    ) -> None:
        if self._page_commands is None:
            self.add_page()
        y_bottom = PAGE_HEIGHT - y_top - height
        parts = ["q"]
        parts.append(f"{line_width:.2f} w")
        if fill is not None:
            parts.append(f"{_format_color(fill)} rg")
        if stroke is not None:
            parts.append(f"{_format_color(stroke)} RG")
        operator = "B" if fill is not None and stroke is not None else "f" if fill is not None else "S"
        parts.append(f"{x:.2f} {y_bottom:.2f} {width:.2f} {height:.2f} re {operator}")
        parts.append("Q")
        self._page_commands.append("\n".join(parts) + "\n")

    def line(
        self,
        x1: float,
        y1_top: float,
        x2: float,
        y2_top: float,
        *,
        color: tuple[int, int, int] = COLOR_RULE,
        line_width: float = 1.0,
    ) -> None:
        if self._page_commands is None:
            self.add_page()
        y1 = PAGE_HEIGHT - y1_top
        y2 = PAGE_HEIGHT - y2_top
        self._page_commands.append(
            "\n".join(
                [
                    "q",
                    f"{line_width:.2f} w",
                    f"{_format_color(color)} RG",
                    f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S",
                    "Q",
                ]
            )
            + "\n"
        )

    def text(
        self,
        x: float,
        y_top: float,
        text: str,
        *,
        font: str = "F1",
        size: float = 11.0,
        color: tuple[int, int, int] = COLOR_INK,
        align: str = "left",
        width: float | None = None,
    ) -> None:
        if self._page_commands is None:
            self.add_page()
        safe_text = _escape_pdf_text(text)
        if width is not None and align != "left":
            text_width = _estimate_text_width(_sanitize_text(text), size)
            if align == "center":
                x = x + max((width - text_width) / 2, 0)
            elif align == "right":
                x = x + max(width - text_width, 0)
        y = PAGE_HEIGHT - y_top
        self._page_commands.append(
            "\n".join(
                [
                    "BT",
                    f"/{font} {size:.2f} Tf",
                    f"{_format_color(color)} rg",
                    f"1 0 0 1 {x:.2f} {y:.2f} Tm",
                    f"({safe_text}) Tj",
                    "ET",
                ]
            )
            + "\n"
        )

    def paragraph(
        self,
        text: str,
        *,
        x: float = MARGIN_X,
        width: float = CONTENT_WIDTH,
        font: str = "F1",
        size: float = 10.5,
        leading: float = 14.0,
        color: tuple[int, int, int] = COLOR_INK,
    ) -> None:
        lines = _wrap_text(_strip_inline_markdown(text), width, size)
        if not lines:
            self.y += leading * 0.4
            return
        self.ensure_space((len(lines) * leading) + 4)
        for line in lines:
            self.text(x, self.y, line, font=font, size=size, color=color)
            self.y += leading
        self.y += 3

    def bullet_list(
        self,
        items: Iterable[str],
        *,
        x: float = MARGIN_X,
        width: float = CONTENT_WIDTH,
        size: float = 10.0,
        line_spacing: float = 13.0,
    ) -> None:
        for item in items:
            lines = _wrap_text(_strip_inline_markdown(item), width - 14, size)
            if not lines:
                continue
            needed_height = max(line_spacing + 1, len(lines) * line_spacing)
            self.ensure_space(needed_height)
            self.text(x, self.y, "-", font="F2", size=size, color=COLOR_BLUE)
            for idx, line in enumerate(lines):
                self.text(x + 12, self.y + (idx * line_spacing), line, size=size, color=COLOR_INK)
            self.y += len(lines) * line_spacing + 1
        self.y += 1

    def _finalize_page(self) -> None:
        if self._page_commands is None:
            return
        if self.page_number > 1:
            self.line(MARGIN_X, PAGE_HEIGHT - 34, PAGE_WIDTH - MARGIN_X, PAGE_HEIGHT - 34, color=COLOR_RULE, line_width=0.8)
            self.text(MARGIN_X, PAGE_HEIGHT - 22, self.title, size=8.5, color=COLOR_MUTED)
            self.text(PAGE_WIDTH - MARGIN_X - 42, PAGE_HEIGHT - 22, f"Page {self.page_number}", size=8.5, color=COLOR_MUTED, align="right", width=42)
        self._pages.append("".join(self._page_commands))
        self._page_commands = None

    def render(self) -> bytes:
        if self._page_commands is not None:
            self._finalize_page()

        objects: list[bytes | None] = [None]

        def add_object(payload: bytes) -> int:
            objects.append(payload)
            return len(objects) - 1

        catalog_id = add_object(b"<< /Type /Catalog /Pages 2 0 R >>")
        pages_id = add_object(b"")
        regular_font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        bold_font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        italic_font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique >>")

        page_object_ids: list[int] = []
        for page_stream in self._pages:
            content_bytes = page_stream.encode("latin-1")
            content_id = add_object(
                b"<< /Length "
                + str(len(content_bytes)).encode("ascii")
                + b" >>\nstream\n"
                + content_bytes
                + b"endstream"
            )
            page_id = add_object(
                (
                    "<< /Type /Page /Parent 2 0 R "
                    f"/MediaBox [0 0 {PAGE_WIDTH:.0f} {PAGE_HEIGHT:.0f}] "
                    "/Resources << /Font << "
                    f"/F1 {regular_font_id} 0 R /F2 {bold_font_id} 0 R /F3 {italic_font_id} 0 R "
                    ">> >> "
                    f"/Contents {content_id} 0 R >>"
                ).encode("ascii")
            )
            page_object_ids.append(page_id)

        kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
        objects[pages_id] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode("ascii")
        if catalog_id != 1:
            raise AssertionError("Unexpected catalog object number")

        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for object_id in range(1, len(objects)):
            offsets.append(len(output))
            payload = objects[object_id]
            if payload is None:
                raise AssertionError(f"Missing PDF object {object_id}")
            output.extend(f"{object_id} 0 obj\n".encode("ascii"))
            output.extend(payload)
            output.extend(b"\nendobj\n")

        xref_start = len(output)
        output.extend(f"xref\n0 {len(objects)}\n".encode("ascii"))
        output.extend(b"0000000000 65535 f \n")
        for object_id in range(1, len(objects)):
            output.extend(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))

        output.extend(
            (
                "trailer\n"
                f"<< /Size {len(objects)} /Root 1 0 R >>\n"
                f"startxref\n{xref_start}\n%%EOF\n"
            ).encode("ascii")
        )
        return bytes(output)


def _render_table(canvas: _PdfCanvas, rows: list[list[str]]) -> None:
    """Render a simple markdown-style table onto the PDF canvas."""
    if not rows:
        return
    num_cols = max(len(r) for r in rows)
    col_width = CONTENT_WIDTH / max(num_cols, 1)
    cell_pad = 6.0
    cell_text_width = col_width - 2 * cell_pad
    font_size = 9.0
    line_height = 12.0
    min_row_height = 20.0
    header_pad = 2.0

    # Pre-wrap all cells and compute row heights
    wrapped_rows: list[list[list[str]]] = []
    row_heights: list[float] = []
    for row_idx, row in enumerate(rows):
        wrapped_cells: list[list[str]] = []
        max_lines = 1
        for col_idx, cell in enumerate(row):
            text = _strip_inline_markdown(cell)
            lines = _wrap_text(text, cell_text_width, font_size)
            if not lines:
                lines = [""]
            wrapped_cells.append(lines)
            max_lines = max(max_lines, len(lines))
        # Pad to num_cols
        while len(wrapped_cells) < num_cols:
            wrapped_cells.append([""])
        wrapped_rows.append(wrapped_cells)
        h = max(min_row_height, max_lines * line_height + 8)
        row_heights.append(h)

    total_height = sum(row_heights) + 8
    canvas.ensure_space(min(total_height, 300))

    for row_idx, wrapped_cells in enumerate(wrapped_rows):
        is_header = row_idx == 0
        h = row_heights[row_idx]
        y = canvas.y

        if is_header:
            canvas.rect(MARGIN_X, y - 2, CONTENT_WIDTH, h, fill=COLOR_NAVY)
        elif row_idx % 2 == 0:
            canvas.rect(MARGIN_X, y - 2, CONTENT_WIDTH, h, fill=COLOR_PANEL)

        for col_idx, cell_lines in enumerate(wrapped_cells):
            if col_idx >= num_cols:
                break
            x = MARGIN_X + col_idx * col_width + cell_pad
            color = (255, 255, 255) if is_header else COLOR_INK
            font = "F2" if is_header else "F1"
            block_height = len(cell_lines) * line_height
            first_line_y = y - 2 + (h - block_height) / 2 + line_height * 0.75
            for line_idx, line in enumerate(cell_lines):
                canvas.text(x, first_line_y + line_idx * line_height, line, font=font, size=font_size, color=color)

        canvas.y += h

    canvas.y += 10


def _render_cover_page(
    canvas: _PdfCanvas,
    client_profile: ClientProfile,
    section_titles: list[str],
    draft_manifest: Mapping[str, Any] | None,
) -> None:
    canvas.add_page()
    canvas.rect(0, 0, PAGE_WIDTH, 196, fill=COLOR_NAVY)
    canvas.text(MARGIN_X, 100, "Client Advisory Report", font="F2", size=28, color=(255, 255, 255))
    canvas.text(MARGIN_X, 132, "Estate Planning Strategy: GRAT vs CRAT", size=15, color=(226, 232, 240))
    canvas.text(MARGIN_X, 150, "Grantor Retained Annuity Trust  |  Charitable Remainder Annuity Trust", size=10, color=(205, 214, 226))
    canvas.text(MARGIN_X, 172, f"Prepared { _today_text() }", size=10, color=(205, 214, 226))
    canvas.text(PAGE_WIDTH - MARGIN_X - 180, 172, f"Client: {client_profile.client_id}", size=10, color=(205, 214, 226), align="right", width=180)

    box_w = 230.0
    box_pad = 18.0
    box_inner_w = box_w - 2 * box_pad
    box_top = 236.0
    box_title_y = box_top + 28
    box_content_start = box_top + 52
    line_h = 14.0
    item_gap = 4.0
    font_size = 10.0

    # --- Client snapshot (left box) ---
    snap_lines_flat: list[str] = []
    for raw in _client_snapshot_lines(client_profile):
        snap_lines_flat.extend(_wrap_text(raw, box_inner_w, font_size))
    snap_box_h = (box_content_start - box_top) + len(snap_lines_flat) * line_h + box_pad

    # --- Planning objectives (right box) ---
    obj_lines_wrapped: list[list[str]] = []
    for obj in _objective_lines(client_profile)[:6]:
        obj_lines_wrapped.append(_wrap_text(f"- {obj}", box_inner_w, font_size))
    obj_total_lines = sum(len(wl) for wl in obj_lines_wrapped)
    obj_box_h = (box_content_start - box_top) + obj_total_lines * line_h + len(obj_lines_wrapped) * item_gap + box_pad

    box_h = max(snap_box_h, obj_box_h)

    canvas.rect(MARGIN_X, box_top, box_w, box_h, fill=COLOR_PANEL, stroke=COLOR_RULE, line_width=0.8)
    canvas.text(MARGIN_X + box_pad, box_title_y, "Client snapshot", font="F2", size=14, color=COLOR_NAVY)
    y = box_content_start
    for raw in _client_snapshot_lines(client_profile):
        for wl in _wrap_text(raw, box_inner_w, font_size):
            canvas.text(MARGIN_X + box_pad, y, wl, size=font_size, color=COLOR_INK)
            y += line_h
        y += item_gap

    obj_box_x = PAGE_WIDTH - MARGIN_X - box_w
    canvas.rect(obj_box_x, box_top, box_w, box_h, fill=(249, 247, 241), stroke=COLOR_RULE, line_width=0.8)
    canvas.text(obj_box_x + box_pad, box_title_y, "Planning objectives", font="F2", size=14, color=COLOR_NAVY)
    y = box_content_start
    for wrapped in obj_lines_wrapped:
        for wl in wrapped:
            canvas.text(obj_box_x + box_pad, y, wl, size=font_size, color=COLOR_INK)
            y += line_h
        y += item_gap

    scope_box_y = box_top + box_h + 20
    scope_box_h = 128
    canvas.rect(MARGIN_X, scope_box_y, CONTENT_WIDTH, scope_box_h, fill=(251, 252, 254), stroke=COLOR_RULE, line_width=0.8)
    scope_text = (
        "This report compares a Grantor Retained Annuity Trust and a "
        "Charitable Remainder Annuity Trust for the current client facts, "
        "focusing on estate-tax mitigation, family wealth transfer, "
        "charitable outcomes, and implementation tradeoffs."
    )
    scope_inner_w = CONTENT_WIDTH - 36
    scope_lines = _wrap_text(scope_text, scope_inner_w, 10.5)
    # Vertically center: title (14pt) + gap (8pt) + body lines
    title_height = 14.0
    gap_after_title = 8.0
    body_line_h = 14.0
    body_height = len(scope_lines) * body_line_h
    total_content_h = title_height + gap_after_title + body_height
    content_top = scope_box_y + (scope_box_h - total_content_h) / 2
    canvas.text(MARGIN_X + 18, content_top, "Report scope", font="F2", size=14, color=COLOR_NAVY)
    scope_y = content_top + title_height + gap_after_title
    for sl in scope_lines:
        canvas.text(MARGIN_X + 18, scope_y, sl, size=10.5, color=COLOR_INK)
        scope_y += body_line_h

    canvas.y = scope_box_y + scope_box_h + 16


def _render_contents_page(canvas: _PdfCanvas, section_titles: list[str], *, first_section_page: int = 3) -> None:
    canvas.add_page()
    canvas.rect(0, 0, PAGE_WIDTH, 86, fill=(245, 247, 251))
    canvas.rect(MARGIN_X, 64, 72, 6, fill=COLOR_GOLD)
    canvas.text(MARGIN_X, 54, "Contents", font="F2", size=22, color=COLOR_NAVY)
    canvas.y = 120
    right_edge = PAGE_WIDTH - MARGIN_X
    for index, title in enumerate(section_titles):
        canvas.ensure_space(24)
        page_num = first_section_page + index
        canvas.text(MARGIN_X, canvas.y, title, font="F2", size=12, color=COLOR_INK)
        canvas.text(right_edge - 30, canvas.y, str(page_num), font="F1", size=11, color=COLOR_MUTED, align="right", width=30)
        canvas.line(MARGIN_X, canvas.y + 8, right_edge, canvas.y + 8, color=COLOR_RULE, line_width=0.6)
        canvas.y += 26


_NEW_PAGE_SECTIONS = {
    "4. Grantor Retained Annuity Trust (GRAT)",
    "5. Charitable Remainder Annuity Trust (CRAT)",
}


def _render_section_page(canvas: _PdfCanvas, section: ReportSection) -> None:
    # Detect sections that need compact layout to fit on one page
    compact = ("Grantor Retained Annuity Trust" in section.title
               or "Charitable Remainder Annuity Trust" in section.title)

    # Spacing parameters — compact mode tightens spacing but keeps text readable
    para_size = 10.2 if compact else 10.5
    para_leading = 12.5 if compact else 14.0
    para_trail = 1.0 if compact else 3.0
    sub_size = 11.0 if compact else 11.5
    sub_trail = 16.0 if compact else 18.0
    bullet_size = 10.0 if compact else 10.0
    bullet_spacing = 11.5 if compact else 13.0
    blank_gap = 5.0 if compact else 5.0
    fn_size = 7.0 if compact else 7.5
    fn_spacing = 9.0 if compact else 11.0

    canvas.add_page()
    canvas.rect(0, 0, PAGE_WIDTH, 86, fill=(245, 247, 251))
    canvas.rect(MARGIN_X, 64, 72, 6, fill=COLOR_GOLD)
    canvas.text(MARGIN_X, 54, section.title, font="F2", size=22, color=COLOR_NAVY)
    canvas.y = 120

    footnotes: dict[str, int] = {}  # source_id -> footnote number

    lines = section.lines
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            canvas.y += blank_gap
            index += 1
            continue

        if set(stripped) <= {"-", " "}:
            index += 1
            continue

        if stripped.startswith("### "):
            canvas.ensure_space(sub_trail + 4)
            canvas.text(MARGIN_X, canvas.y, _strip_inline_markdown(stripped[4:]), font="F2", size=sub_size, color=COLOR_BLUE)
            canvas.y += sub_trail
            index += 1
            continue

        if stripped.startswith("| "):
            table_rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                row_text = lines[index].strip()
                if set(row_text.replace("|", "").strip()) <= {"-", " "}:
                    index += 1
                    continue
                cells = [c.strip() for c in row_text.strip("|").split("|")]
                table_rows.append(cells)
                index += 1
            _render_table(canvas, table_rows)
            continue

        if stripped.startswith("- "):
            items: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("- "):
                raw_item = lines[index].strip()[2:].strip()
                cleaned_item, footnotes = _extract_footnotes(raw_item, footnotes)
                items.append(cleaned_item)
                index += 1
            canvas.bullet_list(items, size=bullet_size, line_spacing=bullet_spacing)
            continue

        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if not candidate or candidate.startswith("### ") or candidate.startswith("- "):
                break
            paragraph_lines.append(candidate)
            index += 1
        raw_para = " ".join(paragraph_lines)
        cleaned_para, footnotes = _extract_footnotes(raw_para, footnotes)
        canvas.paragraph(cleaned_para, size=para_size, leading=para_leading)
        # Override trailing gap (paragraph adds 3 by default; adjust)
        canvas.y += para_trail - 3.0

    # Render footnotes at the bottom of the section
    if footnotes:
        canvas.ensure_space(len(footnotes) * fn_spacing + 12)
        canvas.line(MARGIN_X, canvas.y, MARGIN_X + 120, canvas.y, color=COLOR_RULE, line_width=0.5)
        canvas.y += 6
        for source_id, idx in sorted(footnotes.items(), key=lambda kv: kv[1]):
            label = _SOURCE_LABELS.get(source_id, source_id)
            sup = _to_superscript(idx)
            footnote_text = f"{sup} {label}"
            canvas.text(MARGIN_X, canvas.y, footnote_text, size=fn_size, color=COLOR_MUTED)
            canvas.y += fn_spacing


def _render_references_page(canvas: _PdfCanvas, references: list[str]) -> None:
    if not references:
        return
    canvas.add_page()
    canvas.rect(0, 0, PAGE_WIDTH, 86, fill=(245, 247, 251))
    canvas.text(MARGIN_X, 54, "Source Appendix", font="F2", size=22, color=COLOR_NAVY)
    canvas.text(MARGIN_X, 82, "Primary citations used across the report", size=11, color=COLOR_MUTED)
    canvas.y = 124
    canvas.bullet_list(references, width=CONTENT_WIDTH)


def write_draft_pdf(
    final_assembled_markdown: str,
    output_path: str | Path,
    *,
    client_profile: ClientProfile,
    draft_manifest: Mapping[str, Any] | None = None,
    max_pages: int = 15,
) -> Path:
    """Write a styled client-facing PDF from assembled markdown."""
    if not isinstance(final_assembled_markdown, str) or not final_assembled_markdown.strip():
        raise ValueError("final_assembled_markdown must be a non-empty string")
    if max_pages < 1:
        raise ValueError("max_pages must be >= 1")

    path = Path(output_path)
    if path.suffix.lower() != ".pdf":
        raise ValueError("output_path must point to a .pdf file")

    sections, references = _extract_report_sections(final_assembled_markdown)
    sections = [s for s in sections if "Next Steps" not in s.title]
    section_titles = [section.title for section in sections]

    canvas = _PdfCanvas(title="Client Advisory Report — GRAT / CRAT")
    _render_cover_page(canvas, client_profile, section_titles, draft_manifest)
    _render_contents_page(canvas, section_titles)
    for section in sections:
        _render_section_page(canvas, section)

    pdf_bytes = canvas.render()
    page_count = len(canvas._pages)
    if page_count > max_pages:
        raise ValueError(
            f"Rendered PDF exceeds page budget: {page_count} pages > {max_pages}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_bytes)
    return path
