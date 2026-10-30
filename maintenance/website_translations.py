"""Persistent source/translation pairs, shared by website builds and normal data tools."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

from doxygenue.cpp import SafeError
from doxygenue.doxygen import dump_atomic


def source_hash(text):
    return hashlib.sha256(re.sub(r'\s+', ' ', text).strip().encode('utf-8')).hexdigest()


class TranslationMemory:
    def __init__(self, path, language):
        self.path = Path(path)
        self.language = language
        rows = json.loads(self.path.read_text('utf-8-sig')) if self.path.exists() else []
        if not isinstance(rows, list) or any(not isinstance(r, dict) or not r.get('id') for r in rows):
            raise SafeError('翻译记忆应为带 id 的 JSON 记录数组。')
        self.rows = {r['id']: dict(r) for r in rows}
        if len(self.rows) != len(rows):
            raise SafeError('翻译记忆含重复 id。')
        self.matches = {}
        self.counts = dict(hits=0, reused=0, seeded=0, missing=0, stale=0)
        self.by_source = {r['source_hash']: r for r in rows if r.get('translation') and
                          r.get('translated_source_hash') == r.get('source_hash')}

    def text(self, key, source, *, metadata=None, seed=''):
        if not source:
            return ''
        if key in self.matches:
            return self.matches[key]['text']
        digest = source_hash(source)
        row = self.rows.get(key)
        if row is None:
            row = dict(id=key, translation='', translated_source_hash='', reviewed=False)
            if seed:
                row.update(translation=seed, translated_source_hash=digest)
                status = 'seeded'
            elif digest in self.by_source:
                old = self.by_source[digest]
                row.update(translation=old['translation'], translated_source_hash=digest,
                           reviewed=old.get('reviewed', False))
                status = 'reused'
            else:
                status = 'missing'
        elif row.get('translation') and row.get('translated_source_hash') == digest:
            status = 'hits'
        elif not row.get('translation') and seed:
            row.update(translation=seed, translated_source_hash=digest)
            status = 'seeded'
        else:
            status = 'stale' if row.get('translation') else 'missing'
        row.update(metadata or {})
        row.update(source_text=source, source_hash=digest)
        self.rows[key] = row
        translated = bool(row.get('translation')) and row.get('translated_source_hash') == digest
        if translated:
            self.by_source[digest] = row
        value = row['translation'] if translated else source
        self.counts[status] += 1
        self.matches[key] = dict(status=status, text=value, source_hash=digest)
        return value

    def save(self):
        dump_atomic(self.path, sorted(self.rows.values(), key=lambda r: r['id']))
        pending = [key for key, match in self.matches.items() if match['status'] in {'missing', 'stale'}]
        return dict(language=self.language, **self.counts, active=len(self.matches),
                    pending=pending, memory=str(self.path))
