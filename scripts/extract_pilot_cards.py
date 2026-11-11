import hashlib
import json
import random
from pathlib import Path

from langid import classify


def card_language(item: dict) -> str | None:
    language = classify("\n".join(item.values()))[0]
    if language not in {"en", "zh"}:
        return None
    if any(classify(value)[0] not in {"en", "zh"} for value in item.values() if len(value) >= 80):
        return None
    return language

source = Path('/mnt/sv0/d2l/vanilla_v3_20260831_ad_dislike_card.jsonl')
cache = Path('/mnt/sv0/sean/Ludens/research/out/role_cards_2000_20261015')
output = Path('/mnt/sv0/sean/Ludens/research/out/role_cards_2000_en_zh_20261015')
output.mkdir(parents=True, exist_ok=False)
size = source.stat().st_size
rng = random.Random(20261015)
window_bytes, record_bytes = 8 * 1024**2, 2 * 1024**2
seen_ids, seen_content, records, locations = set(), set(), [], []
read_bytes, rejected = 0, {'oversized': 0, 'missing_fields': 0, 'duplicate': 0, 'language': 0}
metadata = json.loads((cache / 'sources.json').read_text())
with (cache / 'candidates.jsonl').open() as stream:
    for line, location in zip(stream, metadata['records'], strict=True):
        item = json.loads(line)
        seen_ids.add(location['prompt_id']); seen_content.add(location['sha256'])
        language = card_language(item)
        if language is None:
            rejected['language'] += 1
            continue
        records.append(item)
        locations.append({**location, 'row': len(records) - 1, 'language': language})
print(f'Reused {len(records)} English/Chinese cards from the existing 2000', flush=True)
last_offset = max(row['offset'] for row in metadata['records'])
with source.open('rb') as stream:
    for window in range(128):
        start = rng.randrange(window * size // 128, (window + 1) * size // 128)
        if (window + 1) * size // 128 <= last_offset:
            continue
        stream.seek(max(start, last_offset))
        fragment = stream.readline(record_bytes)
        read_bytes += len(fragment)
        if not fragment.endswith(b'\n'):
            rejected['oversized'] += 1
            continue
        end = start + window_bytes
        while stream.tell() < end and len(records) < 2000:
            offset = stream.tell()
            line = stream.readline(min(record_bytes, end - offset))
            read_bytes += len(line)
            if not line or not line.endswith(b'\n'):
                rejected['oversized'] += 1
                break
            row = json.loads(line)
            card = row.get('character_card') or {}
            prompt = card.get('PromptCharacterCard') or {}
            item = {'personality': prompt.get('personality'), 'scenario': prompt.get('scenario') or '', 'welcomeMessage': card.get('WelcomeMessage')}
            if not all(isinstance(v, str) and len(v) <= 24000 for v in item.values()) or not item['personality'] or not item['welcomeMessage']:
                rejected['missing_fields'] += 1
                continue
            key = prompt.get('promptId') or row.get('conv_prompt_id')
            digest = hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if (key and key in seen_ids) or digest in seen_content:
                rejected['duplicate'] += 1
                continue
            seen_ids.add(key); seen_content.add(digest)
            language = card_language(item)
            if language is None:
                rejected['language'] += 1
                continue
            records.append(item)
            locations.append({'row': len(records) - 1, 'prompt_id': key, 'offset': offset, 'sha256': digest, 'language': language})
        if len(records) == 2000:
            break
(output / 'candidates.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records))
(output / 'sources.json').write_text(json.dumps({'source': str(source), 'source_bytes': size, 'read_bytes': read_bytes, 'count': len(records), 'selection': '128 stratified byte windows; not a uniform role-card sample; semantic screening pending', 'rejected': rejected, 'records': locations}, ensure_ascii=False, indent=2))
print(json.dumps({'count': len(records), 'read_bytes': read_bytes, 'rejected': rejected, 'output': str(output)}, ensure_ascii=False))
