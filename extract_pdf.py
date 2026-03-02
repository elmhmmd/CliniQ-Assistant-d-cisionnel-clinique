import pdfplumber
import sys
from pathlib import Path


ARBRE_DECISIONNEL_PAGE = 17  # 0-indexed — the single decision tree page (Agitation)
ARBRE_DECISIONNEL_TEXT = """[ARBRE DÉCISIONNEL — Agitation]

Si agitation NON contrôlable (contact impossible, examen impossible) :
  → Contention physique et chimique → Référer Centre 15

Si agitation contrôlable (contact possible, examen possible) :
  → Antécédents psychiatriques connus ?
      OUI → Probable décompensation de pathologie mentale chronique → Référer médecin
      NON → Recherche d'une pathologie organique ou traumatique (particulièrement chez personne âgée),
             recherche d'une prise de toxique ou d'alcool → Référer médecin
"""


def table_to_markdown(table: list[list]) -> str:
    if not table or not table[0]:
        return ""

    # Clean None cells
    cleaned = [[cell.strip() if cell else "" for cell in row] for row in table]

    # Remove fully empty rows
    cleaned = [row for row in cleaned if any(cell for cell in row)]
    if not cleaned:
        return ""

    col_count = max(len(row) for row in cleaned)

    # Pad rows to same column count
    cleaned = [row + [""] * (col_count - len(row)) for row in cleaned]

    header = cleaned[0]
    separator = ["---"] * col_count
    body = cleaned[1:]

    def fmt_row(row):
        return "| " + " | ".join(row) + " |"

    lines = [fmt_row(header), fmt_row(separator)] + [fmt_row(r) for r in body]
    return "\n".join(lines)


def extract_page(page, page_index: int) -> str:
    if page_index == ARBRE_DECISIONNEL_PAGE:
        return ARBRE_DECISIONNEL_TEXT

    parts = []  # list of (top_y, text)

    tables = page.find_tables()
    table_bboxes = [t.bbox for t in tables]

    # Extract tables as markdown
    for table in tables:
        markdown = table_to_markdown(table.extract())
        if markdown:
            parts.append((table.bbox[1], markdown))  # bbox[1] = top y

    # Extract text outside table regions
    if table_bboxes:
        # Crop out table areas and extract remaining text
        remaining = page
        for bbox in table_bboxes:
            # Expand bbox slightly to avoid capturing table borders as stray text
            x0, top, x1, bottom = bbox
            # Crop: keep everything above the first table and below the last

        # Use pdfplumber's chars filtered by position
        chars = page.chars
        table_chars = set()
        for bbox in table_bboxes:
            x0, top, x1, bottom = bbox
            for char in chars:
                if (x0 <= char["x0"] <= x1 and top <= char["top"] <= bottom):
                    table_chars.add(id(char))

        outside_chars = [c for c in chars if id(c) not in table_chars]

        if outside_chars:
            # Group chars into lines by rounding top position
            lines: dict[int, list] = {}
            for char in outside_chars:
                key = round(char["top"])
                lines.setdefault(key, []).append(char)

            text_lines = []
            for key in sorted(lines.keys()):
                line_chars = sorted(lines[key], key=lambda c: c["x0"])
                text_lines.append("".join(c["text"] for c in line_chars))

            text = "\n".join(text_lines).strip()
            if text:
                # Use the y position of the first char for ordering
                first_top = outside_chars[0]["top"] if outside_chars else 0
                parts.append((first_top, text))
    else:
        # No tables — extract full page text
        text = page.extract_text(x_tolerance=2, y_tolerance=2)
        if text:
            parts.append((0, text.strip()))

    # Sort parts top to bottom
    parts.sort(key=lambda x: x[0])
    return "\n\n".join(content for _, content in parts)


def extract_pdf(pdf_path: str, output_path: str) -> None:
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)

    print(f"Opening: {pdf_path.name}")

    full_text = []

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"Total pages: {total}")

        for i, page in enumerate(pdf.pages):
            print(f"  Processing page {i + 1}/{total}...", end="\r")
            page_text = extract_page(page, i)
            if page_text.strip():
                full_text.append(f"[PAGE {i + 1}]\n{page_text}")

    output = "\n\n{'='*80}\n\n".join(full_text)

    output_path.write_text(output, encoding="utf-8")
    print(f"\nDone. Output written to: {output_path}")


if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "guide-des-protocoles-699b8192dc98d654208814.pdf"
    out = sys.argv[2] if len(sys.argv) > 2 else "extracted.txt"
    extract_pdf(pdf, out)
