"""NS006 — sloj nad NS005 lažnim Supabase-om (tests/ns005_harness.py), bez izmene NS005 harness-a.

Dodaje tačno ono što Case Evolution lanac traži od baze, prepisano iz migracija:

  • `events.id` PRIMARY KEY (073) — `emit_durable(..., event_id=)` koristi
    `insert(..., ignore_duplicates=True)` = `ON CONFLICT (id) DO NOTHING`;
  • `case_evolution_consequences UNIQUE (event_id, consequence_name)` (096) —
    `_try_claim_consequence` koristi `upsert(..., on_conflict=..., ignore_duplicates=True)`;
  • `case_actions` delimičan UNIQUE `(predmet_id, dedupe_key) WHERE status='open'` (099);
  • RPC `claim_pending_events` (091): `UPDATE events SET claimed_at=now() WHERE dispatched_at IS NULL
    AND (claimed_at IS NULL OR claimed_at < now()-stale) ORDER BY created_at LIMIT n RETURNING *`;
  • PostgREST `.not_.in_(...)` / `.not_.is_(...)` / `.not_.eq(...)` (negacija sledećeg filtera).

Konflikt bez `ignore_duplicates` pri INSERT-u podiže 23505 kao Postgres.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import tests.ns005_harness as h5

# (tabela) -> lista (kolone, uslov) ; uslov(red) True = red učestvuje u jedinstvenosti
JEDINSTVENO = {
    "events": [(("id",), None)],
    "case_evolution_consequences": [(("event_id", "consequence_name"), None)],
    "case_actions": [(("predmet_id", "dedupe_key"), lambda r: r.get("status", "open") == "open")],
    "v2_mutation_idempotency": [(("user_id", "idempotency_key"), None)],
}

PODRAZUMEVANO = {
    "case_evolution_consequences": {"status": "pending"},
    "case_actions": {"status": "open", "closed_at": None, "izvor_dokumenti": []},
    "events": {"dispatched_at": None, "claimed_at": None, "dispatch_attempts": 0, "last_error": None},
    "predmet_dokazi": {"deleted_at": None, "snaga": "srednja"},
}


class _Negacija:
    def __init__(self, upit):
        self._u = upit

    def __call__(self, *a, **k):          # stari oblik `.not_()` iz NS005 harness-a — bez efekta
        return self._u

    def in_(self, k, v):
        return self._u._f("not_in", k, list(v))

    def is_(self, k, v):
        return self._u._f("not_is", k, None if str(v).lower() == "null" else v)

    def eq(self, k, v):
        return self._u._f("not_eq", k, v)


class Upit6(h5._Upit):
    @property
    def not_(self):                         # noqa: D401 — PostgREST svojstvo, ne metoda
        return _Negacija(self)

    def insert(self, red, *a, **k):
        self.opcije = dict(k)
        return super().insert(red, *a, **k)

    def upsert(self, red, *a, **k):
        self.opcije = dict(k)
        return super().upsert(red, *a, **k)

    @staticmethod
    def _poklapa(r, op, k, v):
        if op == "not_in":
            return not h5._Upit._poklapa(r, "in", k, v)
        if op == "not_is":
            return not h5._Upit._poklapa(r, "is", k, v)
        if op == "not_eq":
            return not h5._Upit._poklapa(r, "eq", k, v)
        return h5._Upit._poklapa(r, op, k, v)

    def _sudar(self, r):
        for kolone, uslov in JEDINSTVENO.get(self.t, []):
            if uslov and not uslov(r):
                continue
            for x in self.b.tabele.get(self.t, []):
                if x is r or (uslov and not uslov(x)):
                    continue
                if all(x.get(c) == r.get(c) for c in kolone) and all(r.get(c) is not None for c in kolone):
                    return x
        return None

    def execute(self):
        vrsta, telo = self.radnja
        if vrsta not in ("insert", "upsert") or self.t not in JEDINSTVENO:
            if vrsta == "update" and self.t in JEDINSTVENO and self.t not in self.b.greske:
                return self._update_sa_proverom()
            return super().execute()
        self.b.dnevnik.append({"tabela": self.t, "radnja": vrsta, "filteri": []})
        if self.t in self.b.greske:
            raise self.b.greske[self.t]
        opc = getattr(self, "opcije", {})
        ignorisi = bool(opc.get("ignore_duplicates"))
        ubaceni = []
        for r in (telo if isinstance(telo, list) else [telo]):
            r = copy.deepcopy(r)
            r.setdefault("id", str(h5.uuid.uuid4()))
            r.setdefault("created_at", h5._sada())
            r.setdefault("updated_at", r["created_at"])
            r.setdefault("_rb", next(h5._brojac))
            for kol, vr in {**PODRAZUMEVANO.get(self.t, {}), **self.b.podrazumevano.get(self.t, {})}.items():
                r.setdefault(kol, copy.deepcopy(vr))
            postojeci = self._sudar(r)
            if postojeci is not None:
                if ignorisi:
                    continue                    # ON CONFLICT DO NOTHING — red se ne vraća
                if vrsta == "insert":
                    raise Exception('{"code": "23505", "message": "duplicate key value violates unique constraint"}')
                postojeci.update({k: v for k, v in r.items() if k not in ("id", "_rb", "created_at")})
                ubaceni.append(copy.deepcopy(postojeci))
                continue
            self.b.tabele.setdefault(self.t, []).append(r)
            ubaceni.append(copy.deepcopy(r))
        return h5._Rez(data=ubaceni, count=len(ubaceni))

    def _update_sa_proverom(self):
        """UPDATE koji bi prekršio jedinstvenost (npr. ponovno otvaranje akcije) pada kao u Postgres-u."""
        self.b.dnevnik.append({"tabela": self.t, "radnja": "update", "filteri": [(o, k) for o, k, _ in self.filt]})
        pogodjeni = self._filtrirani()
        for r in pogodjeni:
            probni = {**r, **copy.deepcopy(self.radnja[1])}
            for kolone, uslov in JEDINSTVENO.get(self.t, []):
                if uslov and not uslov(probni):
                    continue
                for x in self.b.tabele.get(self.t, []):
                    if x is r or (uslov and not uslov(x)):
                        continue
                    if all(x.get(c) == probni.get(c) for c in kolone):
                        raise Exception('{"code": "23505", "message": "duplicate key value violates unique constraint"}')
        for r in pogodjeni:
            r.update(copy.deepcopy(self.radnja[1]))
            if "updated_at" not in self.radnja[1]:
                r["updated_at"] = h5._sada() + "#" + str(next(h5._brojac))
        return h5._Rez(data=[copy.deepcopy(r) for r in pogodjeni], count=len(pogodjeni))


def _claim_pending_events(baza, p):
    granica = (datetime.now(timezone.utc) - timedelta(seconds=int(p.get("p_stale_claim_seconds") or 30))).isoformat()
    kandidati = [r for r in baza.tabele.get("events", [])
                 if r.get("dispatched_at") is None and (r.get("claimed_at") is None or str(r["claimed_at"]) < granica)]
    kandidati.sort(key=lambda r: (str(r.get("created_at")), r.get("_rb", 0)))
    out = []
    for r in kandidati[: int(p.get("p_batch_size") or 25)]:
        r["claimed_at"] = datetime.now(timezone.utc).isoformat()
        out.append(copy.deepcopy(r))
    return out


class Baza6(h5.Baza):
    def __init__(self, tabele=None):
        super().__init__(tabele)
        self.rpc_impl["claim_pending_events"] = _claim_pending_events

    def table(self, ime):
        return Upit6(self, ime)

    def from_(self, ime):
        return Upit6(self, ime)


def pripremi(monkeypatch, tabele=None):
    """Kao `ns005_harness.pripremi`, ali nad `Baza6`. Uvozi Case Evolution module PRE zamene
    `_get_supa`, da i oni dobiju lažnu bazu (harness menja samo već uvezene module)."""
    import api  # noqa: F401 — isti redosled uvoza kao produkcija (event_bus pre case_evolution)
    import services.event_bus  # noqa: F401
    import services.case_evolution  # noqa: F401
    import services.v2_projection  # noqa: F401
    import routers.evidence  # noqa: F401
    import routers.case_dna  # noqa: F401
    monkeypatch.setattr(h5, "Baza", Baza6)
    return h5.pripremi(monkeypatch, tabele)


def dispecuj(puta: int = 1) -> list[dict]:
    """Pokreće STVARNI `dispatch_pending_events` (isti koji DispatchLoop zove na 3 s)."""
    import asyncio
    from services.event_bus import dispatch_pending_events
    return [asyncio.run(dispatch_pending_events()) for _ in range(puta)]


ocisti = h5.ocisti
zaglavlje = h5.zaglavlje
