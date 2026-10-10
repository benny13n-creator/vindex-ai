"""NS008 — sloj nad NS007 lažnom bazom (tests/ns007_fake.py) za Law Brain.

Prepisano iz SQL-a:
  • `outcome_log.predmet_id UNIQUE` (037) — upsert `on_conflict=predmet_id` menja postojeći red, INSERT pada 23505.
"""
from __future__ import annotations

import tests.ns006_fake as f6
import tests.ns007_fake as f7

f6.JEDINSTVENO.setdefault("outcome_log", [(("predmet_id",), None)])
f6.PODRAZUMEVANO.setdefault("outcome_log", {"presudni_faktori": [], "uzroci": []})


def pripremi(monkeypatch, tabele=None):
    import routers.learning  # noqa: F401 — uvoz pre zamene `_get_supa`
    import services.law_brain  # noqa: F401
    return f7.pripremi(monkeypatch, tabele)


ocisti = f7.ocisti
zaglavlje = f7.zaglavlje
