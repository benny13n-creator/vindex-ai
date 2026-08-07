# Mission 005 — Fix Log

### Fix 1 — `routers/smart_intake.py::resolve_job_review`/`reject_job_review` (closes `LIVINGSYS-DEBT-010`)
```python
if result["review_resolved_now"]:
    try:
        from services.event_bus import EventType, emit_durable
        await emit_durable(EventType.REVIEW_ACCEPTED, ...)  # (or REVIEW_REJECTED)
    except Exception as _ee:
        logger.warning(...)
```

### Fix 2 — `routers/rocista.py::kreiraj_rociste` (closes `LIVINGSYS-DEBT-043`)
```python
_dup_r = await asyncio.to_thread(
    lambda: supa.table("rocista").select("*")
        .eq("predmet_id", body.predmet_id).eq("user_id", uid)
        .eq("sud", payload["sud"]).eq("datum", payload["datum"])
        .gte("created_at", (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat())
        .execute()
)
_existing = next(
    (r for r in (_dup_r.data or []) if (r.get("vreme") or None) == payload["vreme"]), None
)
if _existing:
    return {"rociste": _existing, "ok": True}
```

## Reuse discipline

Fix 1 reuses the existing `review_resolved_now` boolean, already computed and returned by
`resolve_review()`/`reject_review()`. Fix 2 reuses only existing columns (`predmet_id`, `sud`,
`datum`, `vreme`, `created_at`, `user_id`) — no migration.
