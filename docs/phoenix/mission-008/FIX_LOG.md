# Mission 008 — Fix Log

### Fix 1 — `static/vindex.js::notif_load` (closes `LIVINGSYS-DEBT-050`)
```js
var d  = await r.json();
_notifData = d.notifications || [];
_notifData.forEach(function(n){ if (n.procitano) _notifRead.add(n.id); });
localStorage.setItem('vx_notif_read', JSON.stringify([..._notifRead]));
notif_render();
```

### Fix 2 — `routers/intelligence_timeline.py` (closes `LIVINGSYS-DEBT-051`)
```python
# step 4, while iterating hron_r.data:
if (h.get("dogadjaj") or "").startswith("Predmet zatvoren"):
    _zatvaranje_vec_u_hronologiji = True

# step 7:
if predmet.get("status") == "zatvoren" and not _zatvaranje_vec_u_hronologiji:
    ...
```

### Fix 3 — `routers/kalendar.py::_klasifikuj_dogadjaj` (closes `LIVINGSYS-DEBT-053`)
```python
_NAPOMENA_PREFIKSI = ("Predmet zatvoren", "Follow-up ročište", "Ugovor o zastupanju zaključen")

def _klasifikuj_dogadjaj(dogadjaj: str) -> str:
    d = dogadjaj.lower()
    if "zastarelost" in d or "zastarelos" in d:
        return "rok_zastarelost"
    if dogadjaj.startswith(_NAPOMENA_PREFIKSI):
        return "napomena"
    return "rok_dokument"
```
Plus the emoji branch in `_aggr_events`'s hronologija loop, the `tipCls`/grid-dot-color/
day-detail-label branches in `static/vindex.js`, and a new `.kal-ev-napomena` rule in
`static/vindex.css`.

### Fix 4 — `static/sw.js`
`CACHE_NAME` bumped `"vindex-v100"` → `"vindex-v101"` (this mission touched `vindex.js`/
`vindex.css`). `tests/test_iron_lawyer_frontend_fixes.py`'s pinned-literal assertion updated to
match.

## Reuse discipline

Fix 1 reuses the exact `procitano` field the backend already returns and already correctly
maintains — zero new backend surface. Fix 2 reuses `hron_r.data`, already fetched in step 4 —
no 2nd query, no new table access. Fix 3 reuses the classification function's existing shape
(prefix/substring matching), adding one bucket rather than a new mechanism. Zero migrations,
zero new algorithms.
