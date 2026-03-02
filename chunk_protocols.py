import json
import re
import sys
import unicodedata
from pathlib import Path

PAGE_RE = re.compile(r'<<<PAGE (\d+)>>>\n')
FOOTER_RE = re.compile(r'Guide des Protocoles\s*-\s*\d{4}\s*\d*', re.I)
SEPARATOR_RE = re.compile(r'^(PÉDIATRIE|MÉDECINE[\s\n]+ADULTE|DENTAIRE)\s*$', re.I)
HEADER_RE = re.compile(
    r'^\|\s*\|\s*(?P<specialty>.+?)\s*\|\s*Version\s*:\s*(?P<version>\d+)\s*\n'
    r'Validation\s*:.*?\nDate\s*:\s*(?P<date>\d{4})\s*\|\s*\n'
    r'\|\s*---.*?\n\|\s*\|\s*(?P<protocol>[\s\S]+?)\s*\|[^\n]*',
    re.MULTILINE,
)
SECTION_RE = re.compile(
    r"^(CE QU'IL NE FAUT PAS FAIRE|CE QU'IL FAUT EXPLIQUER|CE QU'I[lL] FAUT FAIRE"
    r"|CE QU'IL FAUT SAVOIR|RECOMMANDATIONS THERAPEUTIQUES|RECOMMANDATIONS"
    r"|TRAITEMENT SYMPTOMATIQUE IMMEDIAT|TRAITEMENT A ENVISAGER SELON[^\n]*"
    r"|TRAITEMENT SELON[^\n]*|ORIENTATION DIAGNOSTIQUE[^\n]*"
    r"|RECONNAITRE ET TRAITER[^\n]*|SITUATIONS OÙ[^\n]*"
    r"|QUI ET COMMENT INFORMER[^\n]*|DENTS DE LAIT[^\n]*"
    r"|DENTS DEFINITIVES[^\n]*|AUTRES URGENCES[^\n]*|ARBRE DECISONNEL)"
    r"[\s:]*$",
    re.MULTILINE | re.I,
)


def slugify(text):
    text = text.replace('Œ', 'OE').replace('œ', 'oe').replace('Æ', 'AE').replace('æ', 'ae')
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'_+', '_', re.sub(r'[^a-z0-9_]', '', re.sub(r"['\s]+", '_', text.lower()))).strip('_')


_SPECIALTY_MAP = {
    'PÉDIATRIE':       'Pédiatrie',
    'MÉDECINE ADULTE': 'Médecine Adulte',
    'DENTAIRE':        'Dentaire',
}

def normalize_specialty(raw):
    return _SPECIALTY_MAP.get(raw.strip(), raw.strip().title())


def clean(text):
    text = text.replace('\u2019', "'").replace('\u2018', "'") 
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    return re.sub(r'\n{3,}', '\n\n', FOOTER_RE.sub('', text)).strip()


def parse_header(content):
    """Returns (meta, stripped_body) or None if not a protocol header page."""
    m = HEADER_RE.match(content)
    if not m:
        return None
    meta = {
        'specialty': normalize_specialty(m.group('specialty')),
        'version': m.group('version'),
        'date': m.group('date'),
        'protocol': re.sub(r'\s+', ' ', m.group('protocol')).strip().replace('\u2019', "'").replace('\u2018', "'"),
    }
    return meta, content[m.end():].strip()


def group_protocols(pages):
    protocols, current = [], None
    for num in sorted(pages):
        content = pages[num]
        result = parse_header(content)
        if result:
            if current:
                protocols.append(current)
            meta, body = result
            current = {'meta': meta, 'p_start': num, 'p_end': num, 'body': clean(body)}
        elif current and not SEPARATOR_RE.match(FOOTER_RE.sub('', content).strip()):
            if cont := clean(content):
                current['body'] += '\n\n' + cont
            current['p_end'] = num
    if current:
        protocols.append(current)
    return protocols


def split_sections(body):
    matches = list(SECTION_RE.finditer(body))
    if not matches:
        return [('body', body.strip())]
    sections = []
    if intro := body[:matches[0].start()].strip():
        sections.append(('body', intro))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        if section_body := body[m.end():end].strip():
            sections.append((m.group(1).strip(), section_body))
    return sections


def build_chunks(protocols):
    chunks = []
    for p in protocols:
        sp, pr = p['meta']['specialty'], p['meta']['protocol']
        for header, body in split_sections(p['body']):
            cid = f"{slugify(sp)}__{slugify(pr)}__{slugify(header)}"
            chunks.append({
                'page_content': f"[Spécialité: {sp} | Protocole: {pr} | Section: {header}]\n\n{body}",
                'metadata': {**p['meta'], 'section': slugify(header), 'section_header': header,
                             'page_start': p['p_start'], 'page_end': p['p_end'], 'chunk_id': cid},
            })
    return chunks


def main(inp='extracted.txt', out='chunks.json'):
    text = Path(inp).read_text(encoding='utf-8')
    parts = PAGE_RE.split(text)
    pages = {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts), 2)}
    print(f"Pages: {len(pages)}")

    protocols = group_protocols(pages)
    print(f"Protocols: {len(protocols)}")
    for p in protocols:
        print(f"  [{p['meta']['specialty']:>15}] {p['meta']['protocol']:<35} pages {p['p_start']}–{p['p_end']}")

    chunks = build_chunks(protocols)
    print(f"\nChunks: {len(chunks)}")
    for c in chunks:
        print(f"  {c['metadata']['chunk_id']}")

    Path(out).write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\nOutput: {out}")


if __name__ == '__main__':
    main(*sys.argv[1:3])
