import json
import re
import unicodedata
from pathlib import Path


# ─── Patterns ────────────────────────────────────────────────────────────────

PAGE_RE = re.compile(r'<<<PAGE (\d+)>>>\n')

# Protocol header table — always at the top of a new protocol's first page.
# Format (from extraction):
#   |  | SPECIALTY | Version : N\nValidation : ...\nDate : YYYY |
#   | --- | --- | --- |
#   |  | Protocol Name |  |
HEADER_TABLE_RE = re.compile(
    r'^\|\s*\|\s*(?P<specialty>.+?)\s*\|\s*Version\s*:\s*(?P<version>\d+)\s*\n'
    r'Validation\s*:.*?\n'
    r'Date\s*:\s*(?P<date>\d{4})\s*\|\s*\n'
    r'\|\s*---.*?\n'
    r'\|\s*\|\s*(?P<protocol>[\s\S]+?)\s*\|\s*',  # [\s\S] to handle multiline protocol names
    re.MULTILINE,
)

# Page footer — "Guide des Protocoles - 2025<page_num>" in various spacings
FOOTER_RE = re.compile(r'Guide des Protocoles\s*-\s*\d{4}\s*\d*', re.IGNORECASE)

# Separator pages (full-page section dividers like PÉDIATRIE, MÉDECINE ADULTE)
SEPARATOR_RE = re.compile(
    r'^(PÉDIATRIE|MÉDECINE[\s\n]+ADULTE|DENTAIRE)\s*$',
    re.IGNORECASE,
)

# Section headers — more specific patterns first to avoid partial matches
SECTION_PATTERNS = [
    r"CE QU'IL NE FAUT PAS FAIRE",
    r"CE QU'IL FAUT EXPLIQUER",
    r"CE QU'I[lL] FAUT FAIRE",   # handles mixed-case variant in document
    r"CE QU'IL FAUT SAVOIR",
    r"RECOMMANDATIONS THERAPEUTIQUES",
    r"RECOMMANDATIONS",
    r"TRAITEMENT SYMPTOMATIQUE IMMEDIAT",
    r"TRAITEMENT A ENVISAGER SELON[^\n]*",
    r"TRAITEMENT SELON[^\n]*",
    r"ORIENTATION DIAGNOSTIQUE[^\n]*",
    r"RECONNAITRE ET TRAITER[^\n]*",
    r"SITUATIONS OÙ[^\n]*",
    r"QUI ET COMMENT INFORMER[^\n]*",
    r"DENTS DE LAIT[^\n]*",
    r"DENTS DEFINITIVES[^\n]*",
    r"AUTRES URGENCES[^\n]*",
    r"ARBRE DECISONNEL",
]

SECTION_RE = re.compile(
    r'^(' + '|'.join(SECTION_PATTERNS) + r')\s*$',
    re.MULTILINE | re.IGNORECASE,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    # Manual substitutions for chars that NFKD won't decompose to ASCII
    text = text.replace('Œ', 'OE').replace('œ', 'oe').replace('Æ', 'AE').replace('æ', 'ae')
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r"['\s]+", '_', text.lower())
    text = re.sub(r'[^a-z0-9_]', '', text)
    return re.sub(r'_+', '_', text).strip('_')


def normalize_specialty(raw: str) -> str:
    upper = raw.strip().upper().replace('\n', ' ')
    if 'DIATRIE' in upper:
        return 'Pédiatrie'
    if 'DECINE' in upper and 'ADULTE' in upper:
        return 'Médecine Adulte'
    if 'DENTAIRE' in upper:
        return 'Dentaire'
    return raw.strip().title()


def clean_content(content: str) -> str:
    content = FOOTER_RE.sub('', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()


def is_protocol_header(content: str) -> bool:
    return bool(HEADER_TABLE_RE.match(content))


def is_separator_page(content: str) -> bool:
    cleaned = FOOTER_RE.sub('', content).strip()
    return bool(SEPARATOR_RE.match(cleaned))


# ─── Parsing ─────────────────────────────────────────────────────────────────

def parse_pages(text: str) -> dict[int, str]:
    parts = PAGE_RE.split(text)
    return {
        int(parts[i]): parts[i + 1].strip()
        for i in range(1, len(parts), 2)
    }


def parse_header_metadata(content: str) -> dict:
    m = HEADER_TABLE_RE.match(content)
    if not m:
        return {}
    return {
        'specialty': normalize_specialty(m.group('specialty')),
        'version': m.group('version'),
        'date': m.group('date'),
        'protocol': re.sub(r'\s+', ' ', m.group('protocol')).strip(),
    }


def strip_header_table(content: str) -> str:
    m = HEADER_TABLE_RE.match(content)
    return content[m.end():].strip() if m else content


# ─── Grouping ────────────────────────────────────────────────────────────────

def group_pages_into_protocols(pages: dict[int, str]) -> list[dict]:
    """
    Groups pages into protocols. Each protocol = its header page + all
    following continuation pages until the next protocol header page.
    Separator pages (PÉDIATRIE, MÉDECINE ADULTE, DENTAIRE) are skipped.
    """
    protocols = []
    current = None

    for page_num in sorted(pages.keys()):
        content = pages[page_num]

        if is_protocol_header(content):
            if current is not None:
                protocols.append(current)
            meta = parse_header_metadata(content)
            current = {
                'metadata': meta,
                'page_start': page_num,
                'page_end': page_num,
                'body': clean_content(strip_header_table(content)),
            }

        elif is_separator_page(content) or current is None:
            # Skip section divider pages and pre-protocol pages (cover, ToC)
            continue

        else:
            continuation = clean_content(content)
            if continuation:
                current['body'] += '\n\n' + continuation
            current['page_end'] = page_num

    if current is not None:
        protocols.append(current)

    return protocols


# ─── Section splitting ────────────────────────────────────────────────────────

def split_into_sections(body: str) -> list[tuple[str, str]]:
    """
    Splits a protocol body into (section_header, content) pairs.
    Content before the first recognized header → ('body', content).
    """
    matches = list(SECTION_RE.finditer(body))
    if not matches:
        return [('body', body.strip())]

    sections = []
    intro = body[:matches[0].start()].strip()
    if intro:
        sections.append(('body', intro))

    for i, match in enumerate(matches):
        header = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_body = body[start:end].strip()
        if section_body:
            sections.append((header, section_body))

    return sections


# ─── Chunk building ───────────────────────────────────────────────────────────

def build_chunks(protocols: list[dict]) -> list[dict]:
    chunks = []

    for proto in protocols:
        meta = proto['metadata']
        specialty = meta.get('specialty', '')
        protocol_name = meta.get('protocol', '')

        for section_header, section_body in split_into_sections(proto['body']):
            section_slug = slugify(section_header)
            chunk_id = (
                f"{slugify(specialty)}__{slugify(protocol_name)}__{section_slug}"
            )

            # Context prefix makes every chunk self-contained when retrieved
            # in isolation — the LLM always knows which protocol it's reading.
            prefix = (
                f"[Spécialité: {specialty} | "
                f"Protocole: {protocol_name} | "
                f"Section: {section_header}]"
            )

            chunks.append({
                'page_content': f"{prefix}\n\n{section_body}",
                'metadata': {
                    'specialty': specialty,
                    'protocol': protocol_name,
                    'section': section_slug,
                    'section_header': section_header,
                    'version': meta.get('version', ''),
                    'date': meta.get('date', ''),
                    'page_start': proto['page_start'],
                    'page_end': proto['page_end'],
                    'chunk_id': chunk_id,
                },
            })

    return chunks


# ─── Main ─────────────────────────────────────────────────────────────────────

def chunk_pdf_text(input_path: str, output_path: str) -> None:
    input_path = Path(input_path)
    output_path = Path(output_path)

    print(f"Reading: {input_path.name}")
    text = input_path.read_text(encoding='utf-8')

    pages = parse_pages(text)
    print(f"Pages parsed: {len(pages)}")

    protocols = group_pages_into_protocols(pages)
    print(f"Protocols identified: {len(protocols)}")
    for p in protocols:
        print(
            f"  [{p['metadata'].get('specialty', '?'):>15}] "
            f"{p['metadata'].get('protocol', '?'):<35} "
            f"pages {p['page_start']}–{p['page_end']}"
        )

    chunks = build_chunks(protocols)
    print(f"\nChunks produced: {len(chunks)}")
    for c in chunks:
        m = c['metadata']
        print(f"  {m['chunk_id']}")

    output_path.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f"\nOutput written to: {output_path}")


if __name__ == '__main__':
    import sys
    inp = sys.argv[1] if len(sys.argv) > 1 else 'extracted.txt'
    out = sys.argv[2] if len(sys.argv) > 2 else 'chunks.json'
    chunk_pdf_text(inp, out)
