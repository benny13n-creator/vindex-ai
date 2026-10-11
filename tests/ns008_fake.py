"""NS008 — sloj nad NS007 lažnom bazom (tests/ns007_fake.py) za Law Brain.

Prepisano iz SQL-a:
  • `outcome_log.predmet_id UNIQUE` (037) — upsert `on_conflict=predmet_id` menja postojeći red, INSERT pada 23505.
  • DEFAULT vrednosti `staging_memory` (088): status 'pending', is_lawyer_approved/pinecone_indexed false.
"""
from __future__ import annotations

import tests.ns006_fake as f6
import tests.ns007_fake as f7

f6.JEDINSTVENO.setdefault("outcome_log", [(("predmet_id",), None)])
f6.PODRAZUMEVANO.setdefault("outcome_log", {"presudni_faktori": [], "uzroci": []})
STAGING_PODRAZUMEVANO = {
    "status": "pending", "is_lawyer_approved": False, "pinecone_indexed": False, "confidence_score": 0.0,
    "quality_detail": {}, "approved_by": None, "approved_at": None, "pinecone_namespace": None, "naziv": ""}


def pripremi(monkeypatch, tabele=None):
    import routers.learning  # noqa: F401 — uvoz pre zamene `_get_supa`
    import services.law_brain  # noqa: F401
    k, baza = f7.pripremi(monkeypatch, tabele)
    baza.podrazumevano.setdefault("staging_memory", dict(STAGING_PODRAZUMEVANO))
    return k, baza


ocisti = f7.ocisti
zaglavlje = f7.zaglavlje
