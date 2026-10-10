"""NS007 — sloj nad NS006 lažnom bazom (tests/ns006_fake.py) za autonomni rad (migracija 136).

Prepisano iz SQL-a:
  • `autonomy_cycles UNIQUE (window_key)`, `autonomy_work_items UNIQUE (user_id, dedupe_key)`;
  • podrazumevane vrednosti kolona iz 136;
  • RPC `autonomy_claim_work_item` — ista pravila kao plpgsql funkcija (zakup, pokušaji, rezervacija budžeta).
Vernost emulacije se dokazuje testom pariteta (tests/test_ns007_t1_t2_parity.py): isti scenario na PRAVOM
PostgreSQL-u i ovde mora dati identične ishode. Atomičnost pod konkurencijom se dokazuje SAMO na pravom Postgres-u.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import tests.ns005_harness as h5
import tests.ns006_fake as f6

f6.JEDINSTVENO.setdefault("autonomy_cycles", [(("window_key",), None)])
f6.JEDINSTVENO.setdefault("autonomy_work_items", [(("user_id", "dedupe_key"), None)])
f6.PODRAZUMEVANO.setdefault("autonomy_work_items", {
    "status": "QUEUED", "attempt_count": 0, "max_attempts": 2, "budget_units": 0, "reserved_day": None,
    "source_refs": [], "lease_owner": None, "lease_expires_at": None, "claimed_at": None, "ready_at": None,
    "resolved_at": None, "title": None, "summary": None, "content_json": None, "quality_state": None,
    "safe_error_code": None, "reviewed_by": None, "review_note": None, "kancelarija_id": None,
    "case_action_id": None, "recommendation_id": None, "source_version": None})
f6.PODRAZUMEVANO.setdefault("autonomy_cycles", {"status": "RUNNING", "finished_at": None, "counts": {}, "safe_error_code": None})


def _vreme(v):
    if not v:
        return None
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _zauzmi(baza, p):
    sada = datetime.now(timezone.utc)
    danas = sada.date().isoformat()
    if not p.get("p_owner") or p.get("p_lease_seconds") is None or not (30 <= int(p["p_lease_seconds"]) <= 3600):
        raise Exception('{"code": "22023", "message": "autonomy_claim_work_item: invalid owner/lease"}')
    redovi = baza.tabele.setdefault("autonomy_work_items", [])
    r = next((x for x in redovi if str(x.get("id")) == str(p.get("p_id"))), None)
    if r is None:
        return {"ishod": "NOT_FOUND"}
    istekao = r.get("status") == "RUNNING" and _vreme(r.get("lease_expires_at")) and _vreme(r["lease_expires_at"]) < sada
    if not (r.get("status") == "QUEUED" or istekao):
        return {"ishod": "NOT_CLAIMABLE", "status": r.get("status")}
    if r.get("attempt_count", 0) >= r.get("max_attempts", 2):
        r.update({"status": "DEAD_LETTER", "safe_error_code": "ATTEMPTS_EXHAUSTED", "lease_owner": None,
                  "lease_expires_at": None, "updated_at": sada.isoformat()})
        return {"ishod": "DEAD_LETTER"}
    placen = r.get("cost_class") == "PAID"
    if placen:
        limit = p.get("p_budget_limit")
        if limit is None or int(limit) < 0:
            return {"ishod": "BUDGET_UNKNOWN"}
        iskorisceno = sum(int(x.get("budget_units") or 0) for x in redovi
                          if x.get("budget_key") == r.get("budget_key") and x.get("reserved_day") == danas
                          and int(x.get("budget_units") or 0) > 0)
        if iskorisceno >= int(limit):
            return {"ishod": "BUDGET_EXHAUSTED", "used": iskorisceno, "limit": int(limit)}
    jedinice = r.get("budget_units") or 0
    r.update({
        "status": "RUNNING", "claimed_at": sada.isoformat(), "lease_owner": str(p["p_owner"]),
        "lease_expires_at": (sada + timedelta(seconds=int(p["p_lease_seconds"]))).isoformat(),
        "attempt_count": int(r.get("attempt_count") or 0) + 1,
        "budget_units": ((jedinice if r.get("reserved_day") == danas else 0) + 1) if placen else jedinice,
        "reserved_day": danas if placen else r.get("reserved_day"),
        "safe_error_code": None, "updated_at": sada.isoformat(),
    })
    return {"ishod": "CLAIMED", "item": copy.deepcopy(r)}


class Baza7(f6.Baza6):
    def __init__(self, tabele=None):
        super().__init__(tabele)
        self.rpc_impl["autonomy_claim_work_item"] = _zauzmi


def pripremi(monkeypatch, tabele=None):
    import api  # noqa: F401
    import services.event_bus  # noqa: F401
    import services.case_evolution  # noqa: F401
    import services.autonomy  # noqa: F401
    monkeypatch.setattr(h5, "Baza", Baza7)
    return h5.pripremi(monkeypatch, tabele)


ocisti = f6.ocisti
zaglavlje = f6.zaglavlje
