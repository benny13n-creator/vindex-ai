# -*- coding: utf-8 -*-
"""
Regresioni test za DELETE /api/gdpr/account.

SVRHA: ovo je test za PRAVNI MODEL, ne za pokrivenost koda. Javna
dokumentacija (privacy.html, static/security.html, static/dpa.html,
static/bezbednosni-list.html) tvrdi da brisanje naloga:
  1. anonimizuje IDENTIFIKACIONE podatke naloga (profiles: email, full_name)
  2. NE dodiruje predmete, klijente niti dokumente klijenata

Ako neko za 6 meseci doda cascade delete na "predmeti"/"klijenti"/
"klijent_dokumenti" u ovaj endpoint (namerno ili slučajno refaktorišući),
semantika brisanja se menja i sve četiri javne stranice postaju netačne.
Ovaj test to hvata pre nego što stigne u produkciju — vidi
SECURITY_CLAIMS_TRACEABILITY.md, red "Brisanje naloga NE briše
predmete/klijente/dokumente/Pinecone".
"""
import os

import pytest
from fastapi.testclient import TestClient


class _FakeQuery:
    """Minimalni fake postgrest-py query builder — beleži akcije, ne dodiruje mrežu."""

    def __init__(self, recorder, table_name):
        self._recorder = recorder
        self._table = table_name

    def update(self, data):
        self._recorder.calls.append({"op": "update", "table": self._table, "data": data})
        return self

    def upsert(self, data, on_conflict=None):
        self._recorder.calls.append({"op": "upsert", "table": self._table, "data": data})
        return self

    def insert(self, data):
        self._recorder.calls.append({"op": "insert", "table": self._table, "data": data})
        return self

    def select(self, *a, **kw):
        self._recorder.calls.append({"op": "select", "table": self._table})
        return self

    def delete(self):
        self._recorder.calls.append({"op": "delete", "table": self._table})
        return self

    def eq(self, *a, **kw):
        return self

    def is_(self, *a, **kw):
        return self

    def order(self, *a, **kw):
        return self

    def limit(self, *a, **kw):
        return self

    def maybe_single(self):
        return self

    def single(self):
        return self

    def execute(self):
        class _Result:
            data = [{"id": "fake-row-id"}]
        return _Result()


class _FakeSupa:
    """Beleži SVAKU tabelu na koju se poziva .table(name) — dokaz šta je dodirnuto."""

    def __init__(self):
        self.calls = []

    @property
    def tables_touched(self) -> set:
        return {c["table"] for c in self.calls}

    def table(self, name):
        return _FakeQuery(self, name)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
    os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
    os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
    os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
    os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
    os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")
    from api import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def fake_user():
    return {"user_id": "11111111-1111-1111-1111-111111111111", "email": "test.user@example.com"}


@pytest.fixture()
def fake_supa(monkeypatch, fake_user):
    """Patch-uje _get_supa isključivo u routers.gdpr namespace-u i override-uje auth."""
    import routers.gdpr as gdpr_module
    from shared.deps import get_current_user
    from api import app

    fake = _FakeSupa()
    monkeypatch.setattr(gdpr_module, "_get_supa", lambda: fake)

    async def _fake_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = _fake_get_current_user
    yield fake
    app.dependency_overrides.pop(get_current_user, None)


# Tabele koje SME da dodirne. Sve ostalo je regresija.
_ALLOWED_TABLES = {"profiles", "korisnik_email_notif"}

# Tabele koje predstavljaju stvarne poslovne/pravne podatke klijenta —
# ako se ijedna od ovih pojavi u .calls, dokumentacija laže.
_MUST_STAY_UNTOUCHED = {"predmeti", "klijenti", "klijent_dokumenti", "predmet_dokumenti"}


def _delete_account(client, ip: str):
    """Svaki poziv sa jedinstvenim X-Forwarded-For — endpoint je rate-limited
    na 3/min po IP (shared/rate.py), a testovi u ovom fajlu inače dele isti
    TestClient i sudarali bi se na limiteru da ne razdvajamo IP po testu."""
    return client.delete(
        "/api/gdpr/account",
        headers={"Authorization": "Bearer fake-token", "X-Forwarded-For": ip},
    )


class TestGdprAccountDeleteAnonymizesOnly:
    def test_returns_200(self, client, fake_supa):
        r = _delete_account(client, "10.0.0.1")
        assert r.status_code == 200, r.text

    def test_only_touches_profile_and_email_notif_tables(self, client, fake_supa):
        _delete_account(client, "10.0.0.2")
        touched = fake_supa.tables_touched
        assert touched <= _ALLOWED_TABLES, (
            f"DELETE /api/gdpr/account je dodirnuo neočekivane tabele: "
            f"{touched - _ALLOWED_TABLES}. Ako je ovo namerno proširenje "
            f"(npr. pravi cascade delete), ažuriraj privacy.html, "
            f"static/security.html, static/dpa.html, "
            f"static/bezbednosni-list.html i SECURITY_CLAIMS_TRACEABILITY.md "
            f"PRE spajanja ove izmene, ne posle."
        )

    def test_never_touches_case_client_or_document_tables(self, client, fake_supa):
        _delete_account(client, "10.0.0.3")
        touched = fake_supa.tables_touched
        forbidden_hit = touched & _MUST_STAY_UNTOUCHED
        assert not forbidden_hit, (
            f"DELETE /api/gdpr/account je dodirnuo {forbidden_hit} — "
            f"to su predmeti/klijenti/dokumenti koji po javnoj dokumentaciji "
            f"MORAJU ostati nepromenjeni zbog zakonske obaveze advokata da "
            f"čuva spise (Zakon o advokaturi). Ako je ovo namerna promena "
            f"pravila zadržavanja, to je pravna odluka koju mora doneti "
            f"founder — ne tiha posledica refaktorisanja koda."
        )

    def test_profile_is_anonymized_not_deleted(self, client, fake_supa, fake_user):
        _delete_account(client, "10.0.0.4")
        profile_updates = [
            c for c in fake_supa.calls if c["table"] == "profiles" and c["op"] == "update"
        ]
        assert len(profile_updates) == 1, "Očekivan tačno jedan UPDATE na profiles tabeli."
        data = profile_updates[0]["data"]
        assert data["email"] != fake_user["email"], "Email mora biti zamenjen, ne obrisan red."
        assert data["email"].startswith("deleted_"), "Anonimizovan email mora imati prepoznatljiv prefiks."
        assert data["full_name"] != "", "Ime mora biti zamenjeno placeholder vrednošću, ne obrisano."
        # Nijedan DELETE poziv na profiles — ovo je anonimizacija, ne hard delete reda.
        profile_deletes = [c for c in fake_supa.calls if c["table"] == "profiles" and c["op"] == "delete"]
        assert not profile_deletes, "profiles red se anonimizuje (UPDATE), ne briše (DELETE)."

    def test_founder_account_cannot_be_deleted_via_api(self, client, monkeypatch):
        """Postojeća zaštita: FOUNDER_EMAILS ne mogu obrisati nalog preko API-ja."""
        import routers.gdpr as gdpr_module
        from shared.deps import get_current_user
        from api import app

        fake = _FakeSupa()
        monkeypatch.setattr(gdpr_module, "_get_supa", lambda: fake)
        founder_email = next(iter(gdpr_module.FOUNDER_EMAILS))

        async def _founder_user():
            return {"user_id": "founder-id", "email": founder_email}

        app.dependency_overrides[get_current_user] = _founder_user
        try:
            r = _delete_account(client, "10.0.0.5")
            assert r.status_code == 403
            assert not fake.calls, "Founder zahtev mora biti odbijen PRE bilo kakvog upisa u bazu."
        finally:
            app.dependency_overrides.pop(get_current_user, None)
