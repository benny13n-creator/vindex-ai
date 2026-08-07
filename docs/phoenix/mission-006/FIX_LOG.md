# Mission 006 — Fix Log

### Fix 1 — `routers/evidence.py::_klasifikuj_dokument` (closes `LIVINGSYS-DEBT-009` part 1, `-022`)
```python
rezultat = json.loads(raw)
if isinstance(rezultat, dict):
    _pouzdanost = rezultat.get("pouzdanost")
    if _pouzdanost not in ("visoka", "srednja", "niska"):
        _pouzdanost = "niska"
    if not isinstance(rezultat.get("ai_tags"), dict):
        rezultat["ai_tags"] = {}
    rezultat["ai_tags"]["_klasifikacija_pouzdanost"] = _pouzdanost
return rezultat
...
except Exception as exc:
    ...
    return {
        "tip_dokaza": "ostalo", "pravni_elementi": [],
        "ai_tags": {"_klasifikacija_greska": True}, "kljucne_cinjenice": [],
    }
```
Prompt (`_CLASSIFY_SYSTEM`) gained `"pouzdanost": "visoka" | "srednja" | "niska"`.

### Fix 2 — `routers/evidence.py::klasifikuj_i_sacuvaj` (closes `LIVINGSYS-DEBT-009` part 2)
```python
def klasifikuj_i_sacuvaj(...) -> dict:  # was -> None
    ...
    return rezultat  # new, at the end of the function
```

### Fix 3 — `routers/evidence.py::reklasifikuj` (closes `LIVINGSYS-DEBT-009` part 2)
```python
rezultat = await asyncio.to_thread(klasifikuj_i_sacuvaj, ...)  # was asyncio.create_task fire-and-forget
_greska = bool((rezultat or {}).get("ai_tags", {}).get("_klasifikacija_greska"))
if _greska:
    return {"ok": False, "poruka": "Reklasifikacija nije uspela (AI greška)..."}
await UsageService.consume(...)
return {"ok": True, "poruka": "Reklasifikacija završena."}
```
Frontend (`static/vindex.js::evidence_reklasifikuj`) updated to read the real response and show
the correct success/failure toast, instead of a generic "started" assumption.

### Fix 4 — `services/case_evolution.py::_consequence_evidence_classify` (closes `LIVINGSYS-DEBT-009` part 3)
```python
_klas_rezultat = await asyncio.to_thread(klasifikuj_i_sacuvaj, ...)
...
if isinstance(_klas_rezultat, dict) and _klas_rezultat.get("ai_tags", {}).get("_klasifikacija_greska"):
    logger.warning("[CASE_EVOLUTION] evidence_classification: AI klasifikacija neuspešna za dokument=%s ...", dokument_id)
```

## Reuse discipline

The confidence-enum-guard fail-safe direction (`"niska"` for unrecognized) matches every
sibling GPT-confidence guard already established in this engagement (`client_twin.py`'s own
`pouzdanost`, CIO's top-level `pouzdanost`, etc.). No new algorithm, no migration.
