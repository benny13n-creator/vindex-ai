"""BA-01 Task 7 — STVARNI odgovor `GET /api/predmeti/{id}` (sa `procesni_dogadjaji`) za
frontend-v2-ng/tests/live-ba01-hronologija.mjs.

Pokretanje: `python tests/ba01_ui_fixture.py` → JSON na stdout (jedan red, prefiks `@@`). Tok je stvaran (klijent → predmet →
Smart Intake otpremanje → worker → finalize → DOCUMENT_ACCEPTED → genome_refresh → ruta detalja); zamenjen je samo izlaz
Genome modela (skriptovani `datumi_kljucni`) da bi stanje bilo ponovljivo. Dokumenti su digitalni PDF-ovi (bez OCR-a).
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k, _v in (("OPENAI_API_KEY", "sk-fake-ba01"), ("PINECONE_API_KEY", "fake"), ("PINECONE_HOST", "https://fake.pinecone.io"),
               ("FOUNDER_EMAILS", "ci@example.com"), ("SUPABASE_URL", "https://fake.supabase.co"), ("SUPABASE_SERVICE_KEY", "x"),
               ("SUPABASE_ANON_KEY", "x"), ("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok"),
               ("FIELD_ENCRYPTION_KEY", "a" * 64)):
    os.environ.setdefault(_k, _v)

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

DATUMI = [
    {"opis": "Presuda doneta", "datum": "2026-10-20", "znacaj": "kriticno", "lokacija": "DOK-01"},
    {"opis": "Presuda uručena tuženom", "datum": "2026-10-23", "znacaj": "bitno", "lokacija": "DOK-02"},
    {"opis": "Ročište održano", "datum": "2026-10-25", "znacaj": "bitno", "lokacija": "DOK-01"},          # izvor ga ne navodi
    {"opis": "Podnesak primljen", "datum": "2026-10-26", "znacaj": "informativno", "lokacija": "DOK-07"},  # nepostojeći izvor
]


def main() -> dict:
    mp = pytest.MonkeyPatch()
    from tests.ns006_fake import ocisti, zaglavlje
    try:
        import routers.case_dna as cd
        import shared.audit_immutable as AUD
        import tests.test_osb002_solo_tok as osb
        from tests.test_ba01_rok_identitet import _predmet, _prikaci
        k, b = osb.postavi_solo(mp)

        async def _audit(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
            return "ok"
        mp.setattr(AUD, "log_action", _audit)
        pozivi = []

        async def _model(client, combined, n):
            pozivi.append(n)
            g = copy.deepcopy(osb.rp._genome(0, False, 0, 0))
            for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
                g.pop(polje, None)
            g["rokovi_kriticni"], g["datumi_kljucni"] = [], copy.deepcopy(DATUMI)
            return json.dumps(g, ensure_ascii=False)
        mp.setattr(cd, "_pozovi_genome_api", _model)
        pid = _predmet(k)
        _prikaci(k, b, pid, ["OSNOVNI SUD U BEOGRADU", "PRESUDA", "Presuda je doneta 20.10.2026. godine."], "01 Presuda digitalna.pdf")
        _prikaci(k, b, pid, ["POTVRDA O DOSTAVI", "Presuda je urucena tuzenom 23.10.2026. godine."], "02 Dostava.pdf")
        n = len(pozivi)
        out = {"P": pid, "odgovori": {}}
        for kor in ("A", "B"):
            r = k.get(f"/api/predmeti/{pid}", headers=zaglavlje(kor))
            out["odgovori"][kor] = {"status": r.status_code, "telo": r.json()}
        out["model_pozvan_pri_citanju"] = len(pozivi) - n
        return out
    finally:
        ocisti()
        mp.undo()


if __name__ == "__main__":
    print("@@" + json.dumps(main(), ensure_ascii=False, default=str))
