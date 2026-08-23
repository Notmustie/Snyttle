"""Render the final research report to a PDF, embedding charts and a data-
cleaning section that the markdown alone doesn't carry.

Deliberately does NOT try to be a general markdown->PDF converter — the
Writer's output follows a known, narrow structure (# / ## headers, "- " bullets,
**bold**, [text](#anchor) links), so a small dedicated parser is more robust than
pulling in a heavyweight markdown library for one controlled use case.
"""
from __future__ import annotations
import os
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                ListFlowable, ListItem, HRFlowable, PageBreak,
                                KeepTogether)

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_ANCHOR = re.compile(r'<a id="[^"]*"></a>')


def _inline(text: str) -> str:
    """Convert the Writer's limited inline markdown to ReportLab's mini-XML."""
    text = _ANCHOR.sub("", text)
    # Render citation links as a visibly bracketed, colored marker rather than
    # bare text — stripping to plain text made citations read as run-on typos
    # ("...contract holders Data Analysis. External research...").
    text = _LINK.sub(r'<font color="#8B6F47">[\1]</font>', text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    return text.strip()


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1c", parent=ss["Heading1"], spaceBefore=6, spaceAfter=10,
                          textColor=colors.HexColor("#2B2118")))
    ss.add(ParagraphStyle("H2c", parent=ss["Heading2"], spaceBefore=14, spaceAfter=6,
                          textColor=colors.HexColor("#3D3024")))
    ss.add(ParagraphStyle("H3c", parent=ss["Heading3"], spaceBefore=10, spaceAfter=4,
                          textColor=colors.HexColor("#4A3B2C")))
    ss.add(ParagraphStyle("Bodyc", parent=ss["BodyText"], spaceAfter=8, leading=15))
    ss.add(ParagraphStyle("Small", parent=ss["BodyText"], fontSize=9,
                          textColor=colors.HexColor("#6B5D4F")))
    return ss


def _markdown_flowables(md: str, styles) -> list:
    """Turn the Writer's markdown body into flowables (headers/paragraphs/bullets).
    Skips a '## References' section — references are rendered separately with
    real hyperlinks, since the markdown version only has anchor placeholders."""
    flow, bullets = [], []

    def flush_bullets():
        nonlocal bullets
        if bullets:
            flow.append(ListFlowable(
                [ListItem(Paragraph(_inline(b), styles["Bodyc"])) for b in bullets],
                bulletType="bullet", leftIndent=18))
            bullets = []

    skip_section = False
    for line in md.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("<a id="):
            continue
        if s.startswith("# "):
            flush_bullets(); skip_section = False
            flow.append(Paragraph(_inline(s[2:]), styles["H1c"]))
        elif s.startswith("## "):
            flush_bullets()
            skip_section = s[3:].strip().lower().startswith("reference")
            if not skip_section:
                flow.append(Paragraph(_inline(s[3:]), styles["H2c"]))
        elif s.startswith("### "):
            if skip_section:
                continue
            flush_bullets()
            flow.append(Paragraph(_inline(s[4:]), styles["H3c"]))
        elif s.startswith(("- ", "* ")):
            if skip_section:
                continue
            bullets.append(s[2:])
        else:
            if skip_section:
                continue
            flush_bullets()
            flow.append(Paragraph(_inline(s), styles["Bodyc"]))
    flush_bullets()
    return flow


def _link(url: str, text: str) -> str:
    """A visibly-styled clickable link — underline + color, so it reads as a
    link rather than plain text (a bare <link> tag is clickable but invisible)."""
    if not url:
        return text
    return f'<link href="{url}"><u><font color="#3B6EA5">{text}</font></u></link>'


def _sources_flowables(state: dict, styles) -> list:
    """Build a real, clickable reference list from state (not from the markdown,
    which only has placeholder anchors)."""
    flow = [Paragraph("References", styles["H2c"])]
    n = 0
    for w in state.get("research_results", []):
        n += 1
        url = w.get("source_url", "")
        title = w.get("title") or url or "Untitled source"
        flow.append(Paragraph(f'{n}. {_link(url, title)}', styles["Bodyc"]))
    for p in state.get("literature_results", []):
        n += 1
        authors = ", ".join(p.get("authors", [])[:3]) or "Unknown authors"
        year = p.get("year", "n.d.")
        doi = p.get("doi", "")
        cite = f'{authors} ({year}). {p.get("title","")}.'
        if doi:
            cite += f' {_link(doi, doi)}'
        flow.append(Paragraph(f'{n}. {cite}', styles["Bodyc"]))
    for r in state.get("retrieved_context", []):
        n += 1
        flow.append(Paragraph(f'{n}. {r.get("doc_name","document")}, p.{r.get("page","?")} '
                              f'(uploaded document)', styles["Bodyc"]))
    if n == 0:
        flow.append(Paragraph("No external sources were used in this run.", styles["Small"]))
    return flow


def export_report_pdf(state: dict, out_path: str) -> str:
    """Build the PDF. Returns out_path. Never raises on missing optional data —
    a run with no charts or no cleaning still produces a complete report."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(out_path, pagesize=letter,
                            topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                            leftMargin=0.9 * inch, rightMargin=0.9 * inch)
    story = []

    # --- Title block ---
    story.append(Paragraph("Research Report", styles["H1c"]))
    story.append(Paragraph(_inline(state.get("user_query", "")), styles["Small"]))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#D8CBB8"),
                            spaceBefore=6, spaceAfter=14))

    # --- Writer's narrative (Summary + Findings; References section skipped here) ---
    report_md = state.get("final_report") or ""
    # The Writer's own output starts with "# Research Report" — drop that single
    # leading H1 so it doesn't duplicate the title block rendered above.
    lines = report_md.splitlines()
    if lines and lines[0].strip().startswith("# "):
        report_md = "\n".join(lines[1:])
    story += _markdown_flowables(report_md, styles)

    # --- Data cleaning / preprocessing (only if a dataset was analyzed) ---
    ana = state.get("analysis_results") or {}
    cleaning = ana.get("cleaning_notes") or []
    ds = state.get("dataset_info")
    if ds:
        story.append(PageBreak())
        story.append(Paragraph("Data Preparation", styles["H2c"]))
        story.append(Paragraph(
            f'Dataset: {os.path.basename(ds.get("path",""))} — '
            f'{ds["shape"][0]} rows x {ds["shape"][1]} columns. '
            f'{ds.get("duplicates", 0)} duplicate row(s) detected before cleaning.',
            styles["Bodyc"]))
        if ds.get("missing"):
            miss = ", ".join(f"{k}: {v}" for k, v in ds["missing"].items())
            story.append(Paragraph(f"Missing values by column — {miss}", styles["Bodyc"]))
        if cleaning:
            story.append(Paragraph("Cleaning steps applied:", styles["H3c"]))
            story.append(ListFlowable(
                [ListItem(Paragraph(_inline(c), styles["Bodyc"])) for c in cleaning],
                bulletType="bullet", leftIndent=18))
        else:
            story.append(Paragraph("No cleaning steps were reported for this run.",
                                   styles["Small"]))

    # --- Charts / figures ---
    charts = [c for c in (ana.get("chart_paths") or []) if os.path.exists(c)]
    if charts:
        story.append(PageBreak())
        story.append(Paragraph("Charts & Figures", styles["H2c"]))
        avail_w = doc.width
        for c in charts:
            try:
                img = Image(c)
                scale = min(avail_w / img.imageWidth, 1.0)
                # Also cap height so a tall chart can't overflow the page and be
                # force-split by KeepTogether's own pagination fallback.
                max_h = doc.height * 0.8
                if img.imageHeight * scale > max_h:
                    scale = max_h / img.imageHeight
                img.drawWidth = img.imageWidth * scale
                img.drawHeight = img.imageHeight * scale
                title = Paragraph(os.path.basename(c).rsplit(".", 1)[0]
                                  .replace("_", " ").title(), styles["H3c"])
                # Title and image must not be split across a page break.
                story.append(KeepTogether([title, img, Spacer(1, 12)]))
            except Exception:  # noqa: BLE001 — a bad image must not kill the PDF
                story.append(Paragraph(f"[chart unavailable: {os.path.basename(c)}]",
                                       styles["Small"]))

    # --- References (built from structured state, not the markdown anchors) ---
    story.append(PageBreak())
    story += _sources_flowables(state, styles)

    doc.build(story)
    return out_path