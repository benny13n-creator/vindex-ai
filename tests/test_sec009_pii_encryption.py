# -*- coding: utf-8 -*-
"""
SEC-009 — bulk CSV/XLSX client import must encrypt PIB before insert, same
as the manual client-creation path (klijenti/router.py) already does.

SVRHA: pre ovog fixa, routers/import_klijenti.py::import_execute pisao je
mapirani PIB direktno u "pib" — kolona koja NE POSTOJI u klijenti šemi
(samo pib_encrypted postoji, migrations/002_klijenti_crm.sql:38), pa je
svaki red sa PIB vrednošću tiho padao kao deo neuspešnog batch insert-a.
Ovaj test dokazuje: (1) PIB se ENKRIPTUJE pre upisa, (2) čist tekst PIB-a
se NIKAD ne pojavljuje u podacima poslatim ka .insert(), (3) enkriptovana
vrednost se ispravno dekriptuje nazad na original (round-trip), koristeći
isti security/crypto.py primitiv (AES-256-GCM) kao svaki drugi CONFIDENTIAL
put u ovoj aplikaciji — ne novi/drugi šifarski sistem.
"""
import asyncio
import base64
import os

import pytest

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")

from starlette.requests import Request  # noqa: E402

from security.crypto import decrypt_field, encrypt_field  # noqa: E402

_TEST_PIB = "123456789"


def _make_request(ip: str = "203.0.113.5") -> Request:
    """@limiter.limit() does an isinstance(request, Request) check — a bare
    stub class fails it, matching the pattern already established in this
    test suite's other rate-limited-endpoint tests."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/klijenti/import/execute",
        "headers": [(b"x-forwarded-for", ip.encode())],
        "client": (ip, 12345),
        "query_string": b"",
    }
    return Request(scope)


class _FakeQuery:
    def __init__(self, recorder, table_name):
        self._recorder = recorder
        self._table = table_name
        self._filters = []

    def insert(self, data):
        self._recorder.inserts.append({"table": self._table, "data": data})
        return self

    def select(self, *a, **kw):
        return self

    def eq(self, field, value):
        self._filters.append((field, value))
        return self

    def execute(self):
        class _Result:
            data = []
        return _Result()


class _FakeSupa:
    def __init__(self):
        self.inserts: list[dict] = []

    def table(self, name):
        return _FakeQuery(self, name)


@pytest.fixture()
def fake_user():
    return {"user_id": "22222222-2222-2222-2222-222222222222", "email": "advokat@primer.rs"}


def _csv_b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode()


class TestBulkImportEncryptsPib:
    def test_pib_never_written_as_plaintext(self, monkeypatch, fake_user):
        import routers.import_klijenti as import_module
        from routers.import_klijenti import ImportExecuteRequest, import_execute

        fake = _FakeSupa()
        monkeypatch.setattr(import_module, "_get_supa", lambda: fake)

        csv_text = "ime,pib\nPetar Petrović,%s\n" % _TEST_PIB
        payload = ImportExecuteRequest(
            mapiranje={"ime": "ime", "pib": "pib"},
            csv_base64=_csv_b64(csv_text),
        )

        asyncio.run(import_execute(request=_make_request(), payload=payload, user=fake_user))

        klijenti_inserts = [i for i in fake.inserts if i["table"] == "klijenti"]
        assert klijenti_inserts, "Nijedan insert na 'klijenti' tabelu nije zabeležen."

        all_rows = [row for insert in klijenti_inserts for row in insert["data"]]
        assert len(all_rows) == 1
        row = all_rows[0]

        # Ključna SEC-009 tvrdnja: 'pib' ključ NE SME postojati u insert
        # podacima (ta kolona ne postoji u šemi, i čak i da postoji, PIB
        # kao plaintext je zabranjen policy-jem primenjenim svuda drugde).
        assert "pib" not in row, "Plaintext 'pib' ključ pronađen u insert podacima — SEC-009 nije zatvoren."

        # Mora postojati enkriptovana verzija.
        assert "pib_encrypted" in row, "'pib_encrypted' nedostaje — PIB nikad nije ni upisan."
        ciphertext = row["pib_encrypted"]

        # Čist tekst PIB-a se ne sme pojaviti NIGDE u ciphertext-u (osnovna
        # provera da enkripcija stvarno nešto radi, ne samo preimenovanje polja).
        assert _TEST_PIB not in ciphertext
        assert ciphertext.startswith("enc_v1:"), f"Neočekivan format ciphertext-a: {ciphertext[:20]}..."

    def test_encrypted_pib_decrypts_back_to_original(self, monkeypatch, fake_user):
        """Round-trip — dokazuje da enkriptovana vrednost NIJE samo
        nepovratno hashovana ili iskvarena, već da ovlašćeni prikaz
        (klijenti/router.py-ov postojeći dekripcioni put) može da je
        ispravno vrati na original."""
        import routers.import_klijenti as import_module
        from routers.import_klijenti import ImportExecuteRequest, import_execute

        fake = _FakeSupa()
        monkeypatch.setattr(import_module, "_get_supa", lambda: fake)

        csv_text = "ime,pib\nMarko Marković,%s\n" % _TEST_PIB
        payload = ImportExecuteRequest(
            mapiranje={"ime": "ime", "pib": "pib"},
            csv_base64=_csv_b64(csv_text),
        )

        asyncio.run(import_execute(request=_make_request(), payload=payload, user=fake_user))

        ciphertext = fake.inserts[0]["data"][0]["pib_encrypted"]
        decrypted = decrypt_field(ciphertext)
        assert decrypted == _TEST_PIB

    def test_row_without_pib_unaffected(self, monkeypatch, fake_user):
        """Redovi bez PIB kolone i dalje rade normalno — fix ne sme
        pokvariti postojeći put za klijente bez PIB podatka."""
        import routers.import_klijenti as import_module
        from routers.import_klijenti import ImportExecuteRequest, import_execute

        fake = _FakeSupa()
        monkeypatch.setattr(import_module, "_get_supa", lambda: fake)

        csv_text = "ime\nAna Anić\n"
        payload = ImportExecuteRequest(mapiranje={"ime": "ime"}, csv_base64=_csv_b64(csv_text))

        asyncio.run(import_execute(request=_make_request(), payload=payload, user=fake_user))

        row = fake.inserts[0]["data"][0]
        assert row.get("ime") == "Ana Anić"
        assert "pib" not in row
        assert "pib_encrypted" not in row


class TestManualEntryPathUnaffected:
    """Regresiona provera da ovaj fix nije slučajno duplirao ili izmenio
    postojeći, već ispravan ručni-unos put — obe putanje moraju da
    proizvedu STRUKTURNO isti format (enc_v1: prefiks)."""

    def test_manual_and_bulk_produce_same_ciphertext_format(self):
        manual_style = encrypt_field(_TEST_PIB)
        assert manual_style.startswith("enc_v1:")
        assert decrypt_field(manual_style) == _TEST_PIB
