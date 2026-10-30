"""Deterministic lexical/alias/fuzzy ranking. Scores are NOT probabilities."""
from __future__ import annotations
import difflib
import re


def normalized(text: str) -> str:
    return re.sub(r"[^\w]", "", text.casefold()).replace("_", "")


def words(text: str) -> list[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return re.findall(r"[\w]+", text.casefold())


def rank(symbols, query: str, aliases: dict, scope: str = "", kind: str = ""):
    from .cpp import inside
    q, qn = query.strip().casefold(), normalized(query)
    query_words = words(query)
    # A request sentence is not a misspelled identifier. Correcting its whole
    # character sequence can rank a private field above a documented public API.
    identifier_query = bool(re.fullmatch(r"[A-Za-z_]\w*(?:::\w+)*", query.strip()))
    if not qn:
        return []
    expanded = set()
    for key, values in aliases.items():
        group = [key, *values]
        if any(v.casefold() in q or q in v.casefold() for v in group):
            expanded.update(normalized(v) for v in group)
    results = []
    for s in symbols:
        if kind and kind != s.kind or scope and not any(inside(p, scope) for p in (s.file, s.bodyfile) if p):
            continue
        leaf = s.name.rsplit("::", 1)[-1]
        full, ln = normalized(s.name), normalized(leaf)
        prose = " ".join((s.brief, s.details, s.inbody, s.comments)).casefold()
        searchable_words = set(words(s.name) + words(prose))
        score, reason, exact = 0.0, "", False
        if s.name.casefold() == q or leaf.casefold() == q:
            score, reason, exact = (1200 if s.name.casefold() == q else 1100), "exact", True
        elif qn in full:
            score, reason = 800 + 100 * len(qn) / max(1, len(full)), "name_contains"
        elif all(w in " ".join(words(s.name)) for w in words(query)):
            score, reason = 700, "name_keywords"
        elif expanded and any(e == ln for e in expanded):
            score, reason = 780, "configured_alias_exact_name"
        elif expanded and any(e in ln for e in expanded):
            score, reason = 720, "configured_alias_name"
        elif len(query_words) > 1 and all(
            w in searchable_words for w in query_words
        ):
            # Reuse the catalog's Doxygen documentation and symbol identity.
            # Terms may be split between a name and its documentation, e.g.
            # "selected entities" in GetSelectedEntitiesView and "zero-copy"
            # in its brief. No body scan or second documentation store is needed.
            score, reason = 740, "name_documentation_keywords"
        elif q in prose or all(w in prose for w in query_words):
            score, reason = 600, "comment_keywords"
        elif expanded and any(e in full or e in normalized(prose) for e in expanded):
            score, reason = 500, "configured_alias"
        else:
            similarity = difflib.SequenceMatcher(None, qn, ln, autojunk=False).ratio()
            if identifier_query and len(qn) >= 3 and similarity >= 0.48:
                score, reason = 300 * similarity, "fuzzy_spelling"
        if score:
            results.append((s, round(score, 3), reason, exact))
    results.sort(key=lambda x: (-x[1], x[0].protection != "public", x[0].name, x[0].args, x[0].file))
    return results
