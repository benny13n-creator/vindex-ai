# Mission 001 — Fix Log

### Fix 1 — `routers/zastarelost.py::guardian_scan` (closes `LIVINGSYS-DEBT-037`)

```python
predmeti_r = await asyncio.to_thread(
    lambda: supa.table("predmeti").select("id,status").eq("user_id", uid).execute()
)
arhivirani_ids = {p["id"] for p in (predmeti_r.data or []) if p.get("status") in ("zatvoren", "arhiviran", "odbijen")}
...
rokovi = [r for r in (rokovi_r.data or []) if r.get("predmet_id") not in arhivirani_ids]
```

### Fix 2 — `routers/matter_intel.py::get_matter_intel` (closes `LIVINGSYS-DEBT-048`)

```python
asyncio.to_thread(lambda: supa.table("rocista").select(
    "sud,datum,status"
).eq("predmet_id", predmet_id).eq("status", "zakazano").order("datum").execute()),
```

### Fix 3 — `routers/kalendar.py::_aggr_events` (closes `LIVINGSYS-DEBT-038`, leak part)

```python
asyncio.to_thread(lambda: supa.table("predmeti")
    .select("id, naziv, status")   # was: "id, naziv"
    .eq("user_id", uid)
    .execute()),
...
arhivirani_ids = {p["id"] for p in pred_r.data if p.get("status") in ("zatvoren", "arhiviran", "odbijen")}
...
# in the rocista loop:
if pid in arhivirani_ids:
    continue
...
# in the predmet_hronologija loop:
if pid in arhivirani_ids:
    continue
```

### Fix 4 — `routers/case_actions.py::get_worklist` (closes `LIVINGSYS-DEBT-036`)

```python
predmeti_r = await asyncio.to_thread(
    lambda: supa.table("predmeti").select("id,naziv").eq("user_id", uid)
        .not_.in_("status", ["zatvoren", "arhiviran", "odbijen"]).execute()
)
```

## Reuse discipline

Every fix reuses one of exactly two already-canonical patterns:
1. The 3-value exclusion set `("zatvoren", "arhiviran", "odbijen")`, first established in
   `routers/dashboard.py`, already reused this week by `email_notif.py`/`dashboard.py`'s own
   Operation Living System fixes.
2. The `.eq("status", "zakazano")` hearing filter, first established in `dashboard.py`/
   `health_index.py`.

Zero new constants, zero new tables, zero new migrations, zero new algorithms.
