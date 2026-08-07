# Mission 010 — Fix Log

### New file — `shared/drafting_grounding.py`
```python
def izvori_kontekst(docs: list[str], limit: int = 4) -> str: ...
CRITIQUE_SYSTEM = """..."""  # identical text previously duplicated nowhere -- new canonical home
```

### `routers/drafting.py`
```python
from shared.drafting_grounding import izvori_kontekst as _izvori_kontekst, CRITIQUE_SYSTEM as _CRITIQUE_SYSTEM
```
(removed the local `_izvori_kontekst`/`_CRITIQUE_SYSTEM` definitions)
```python
def _normalizuj_rezultat(rezultat, credits_remaining=None) -> dict:
    ...
    if isinstance(rezultat, dict) and "critique_applied" in rezultat:
        resp["critique_applied"] = rezultat["critique_applied"]
    return resp
```

### `drafting/router.py`
```python
try:
    from app.services.retrieve import retrieve_documents
    _RAG_AVAILABLE = True
except Exception:
    retrieve_documents = None
    _RAG_AVAILABLE = False

def _call_openai(system, user, max_tokens=2000, response_format: dict | None = None) -> str:
    ...  # response_format now optionally forwarded

def _kriticki_pregled(nacrt: str, kontekst: str, tip_naziv: str) -> tuple[str, bool]:
    ...  # sync port of _critique_and_refine_draft, same prompt/schema/fallback

def generate_draft(vrsta: str, opis: str, user_id: str = "") -> dict:
    ...
    # 0.5 RAG pretraga
    kontekst = ""
    if _RAG_AVAILABLE:
        try:
            rag_upit = f"{tpl['label']}: {opis[:400]}"
            docs, _retrieval_meta = retrieve_documents(rag_upit, 5)
            kontekst = izvori_kontekst(docs)
        except Exception as exc:
            logger.warning(...)
            kontekst = ""

    # 1. Ekstrakcija -- kontekst injected into user_p when present
    ...

    # 5. Popuni šablon (unchanged)
    nacrt_tekst = _popuni_sablon(sablon, fields_ready)

    # 6. Critique pass -- BEFORE compliance report is appended
    nacrt_tekst, critique_applied = _kriticki_pregled(nacrt_tekst, kontekst, tpl["label"])

    # 7. Compliance check (unchanged, deterministic)
    ...
    return {"status": "success", "data": nacrt_tekst + compliance_tekst, "critique_applied": critique_applied}
```

### `static/vindex.js`
Comment-only update (Mission 009's banner trigger was already endpoint-agnostic).

### `static/sw.js`
`CACHE_NAME` bumped `"vindex-v102"` → `"vindex-v103"`.

### `tests/unit/test_drafting.py`
5 `generate_draft` tests gained `patch("drafting.router._RAG_AVAILABLE", False)` to avoid a real
network call; no assertion weakened.

## Reuse discipline

Both `izvori_kontekst` and the critique prompt are now literally the same object
(`is`-identity, proven in the new test suite) across both drafting surfaces — zero drift risk.
The critique pass reuses the exact prompt/schema/fallback logic already proven in production by
`/api/podnesak`; only the async→sync transport differs, required by `generate_draft`'s existing
execution model. Zero new algorithms, zero migrations.
