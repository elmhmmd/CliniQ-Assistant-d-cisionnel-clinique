import pdfplumber
import sys
from pathlib import Path


ARBRE_DECISIONNEL_PAGE = 17  # 0-indexed

# Verbatim text reconstructed from PDF geometry (y-positions).
# Preserves the original typo "DECISONNEL" from the PDF title.
ARBRE_DECISIONNEL_TEXT = """\
ARBRE DECISONNEL

Agitation contrôlable : contact possible,
prise de paramètres ou examen possible

  Non →
    Agitation non contrôlable.
    Contention physique et chimique.
    Référer Centre 15

  Oui →
    Antécédents psychiatriques connus

      Non →
        Recherche d'une pathologie organique ou traumatique
        (particulièrement chez personne âgée)
        Recherche d'une prise de toxique ou d'alcool.
        Référer médecin

      Oui →
        Probable décompensation pathologie mentale chronique
        Référer médecin
"""


def table_to_markdown(table: list[list]) -> str:
    if not table or not table[0]:
        return ""

    cleaned = [[cell.strip() if cell else "" for cell in row] for row in table]
    cleaned = [row for row in cleaned if any(cell for cell in row)]
    if not cleaned:
        return ""

    col_count = max(len(row) for row in cleaned)
    cleaned = [row + [""] * (col_count - len(row)) for row in cleaned]

    header = cleaned[0]
    separator = ["---"] * col_count
    body = cleaned[1:]

    def fmt_row(row: list[str]) -> str:
        return "| " + " | ".join(row) + " |"

    lines = [fmt_row(header), fmt_row(separator)] + [fmt_row(r) for r in body]
    return "\n".join(lines)


def extract_page(page, page_index: int) -> str:
    if page_index == ARBRE_DECISIONNEL_PAGE:
        return ARBRE_DECISIONNEL_TEXT

    parts: list[tuple[float, str]] = []

    tables = page.find_tables()
    table_bboxes = [t.bbox for t in tables]

    for table in tables:
        markdown = table_to_markdown(table.extract())
        if markdown:
            parts.append((table.bbox[1], markdown))

    if table_bboxes:
        chars = page.chars

        # Build a set of (x0, top) positions belonging to table cells.
        # Using rounded float positions as stable keys — id() is unreliable
        # because pdfplumber may regenerate char dicts between accesses.
        table_char_positions: set[tuple[float, float]] = set()
        for bbox in table_bboxes:
            x0, top, x1, bottom = bbox
            for char in chars:
                if x0 <= char["x0"] <= x1 and top <= char["top"] <= bottom:
                    table_char_positions.add(
                        (round(char["x0"], 1), round(char["top"], 1))
                    )

        outside_chars = [
            c for c in chars
            if (round(c["x0"], 1), round(c["top"], 1)) not in table_char_positions
        ]

        if outside_chars:
            # Group chars into visual lines by rounding top coordinate.
            # Rounding is necessary: chars on the same visual line often have
            # slightly different float top values due to PDF precision.
            line_buckets: dict[int, list] = {}
            for char in outside_chars:
                key = round(char["top"])
                line_buckets.setdefault(key, []).append(char)

            text_lines = []
            for key in sorted(line_buckets.keys()):
                line_chars = sorted(line_buckets[key], key=lambda c: c["x0"])
                text_lines.append("".join(c["text"] for c in line_chars))

            text = "\n".join(text_lines).strip()
            if text:
                # min() gives the topmost outside char — used to interleave
                # text blocks and tables in correct reading order within parts.
                first_top = min(c["top"] for c in outside_chars)
                parts.append((first_top, text))
    else:
        text = page.extract_text(x_tolerance=2, y_tolerance=2)
        if text:
            parts.append((0, text.strip()))

    parts.sort(key=lambda x: x[0])
    return "\n\n".join(content for _, content in parts)


def extract_pdf(pdf_path: str, output_path: str) -> None:
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)

    print(f"Opening: {pdf_path.name}")

    pages_output = []

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"Total pages: {total}")

        for i, page in enumerate(pdf.pages):
            print(f"  Processing page {i + 1}/{total}...", end="\r")
            page_text = extract_page(page, i)
            if page_text.strip():
                # <<<PAGE N>>> is the page delimiter for the chunker.
                # It carries page provenance without polluting semantic content —
                # the chunker strips it and stores the number as chunk metadata.
                pages_output.append(f"<<<PAGE {i + 1}>>>\n{page_text}")

    output_path.write_text("\n\n".join(pages_output), encoding="utf-8")
    print(f"\nDone. Output written to: {output_path}")


if __name__ == "__main__":
    pdf = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "guide-des-protocoles-699b8192dc98d654208814.pdf"
    )
    out = sys.argv[2] if len(sys.argv) > 2 else "extracted.txt"
    extract_pdf(pdf, out)
