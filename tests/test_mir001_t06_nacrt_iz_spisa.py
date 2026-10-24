# -*- coding: utf-8 -*-
"""MIR001 TASK-06 (MIR-03) — nacrt podneska iz spisa kroz POSTOJEĆE delove: savetnik „Pisanje podnesaka“
(`POST /api/agents/run`, agent `drafting`, ceo spis + sporne tačke posle TASK-04) → POSTOJEĆI pregled nacrta
(`staging_memory`, V2 kartica Nacrt: `GET /api/staging/predmet/{id}`, `PATCH /tekst`, `approve`/`reject`) → DOCX.

Šablonski `/api/podnesak` ima zatvoren spisak od 12 vrsta (tužbe, žalbe, predlozi…) bez izjašnjenja na nalaz veštaka,
pa za Miroslavljev slučaj nije upotrebljiv; ovde se meri uzemljen put. Model je zamenjen snimačem (deterministički);
sadržaj stvarnog modela meri scratchpad skripta nad snimljenom porukom (`MIR001_SNIMAK`).
"""
import asyncio
import io
import json
import os
import types
from unittest.mock import MagicMock, patch

import pytest

from tests import mir001_golden_case as gc
from tests.test_mir001_t04_savetnik_spis import _OCR, savetnik  # noqa: F401
from tests.test_osb002_solo_tok import A, B, _do_kraja_dogadjaja, solo  # noqa: F401
from tests.test_vcr002_t03_visedokumentni_predmet import _atomsko_rpc, _brisanje_rpc
from tests.nacrt_json_zamena import kao_json

treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — DOK-05 (sken) se ne može pročitati")

ZADATAK = ("Sastavi podnesak tuzioca kojim se izjasnjava na nalaz i misljenje vestaka (DOK-05) i na izjasnjenje tuzenog "
           "na nalaz (DOK-06), za rociste zakazano za 18.11.2026.")
NACRT = ("PRIVREDNOM SUDU U PRIMERGRADU\nBroj predmeta: P 9901/2026\nTuzilac: Alfa Fiktiv DOO, [PROVERITI: adresa]\n"
         "PODNESAK — izjasnjenje na nalaz vestaka\nVestak u nalazu navodi da je uzrok neodgovarajuce izvedena hidroizolacija "
         "na spoju atike (DOK-05). Tuzeni osporava nalaz (DOK-06). Pozivamo se na cl. 999 ZOO.\n"
         "⚠️ Ovaj nacrt generisala je AI i mora ga pregledati i potpisati ovlašćeni advokat pre podnošenja sudu.")


@pytest.fixture
def nacrt(savetnik, monkeypatch):
    k, b, pid, doks, snimljeno = savetnik
    import routers.multi_agent as MA
    import services.quality_gate as QG

    def _model(client, system, user_msg):
        snimljeno.append({"system": MA._sa_granicom(system), "user": user_msg})
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=NACRT))])

    async def _kvalitet(tekst, tip):
        return {"confidence_score": 0.5, "detail": {}}                # ispod praga: odobrenje bez upisa u bazu znanja
    monkeypatch.setattr(MA, "_pozovi_agent_api", _model)
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", kao_json(_model))     # C3b: nacrt iz spisa = JSON
    monkeypatch.setattr(QG, "evaluate_draft_quality", _kvalitet)
    # Deterministički: korutina koju ruta predaje `asyncio.create_task` se hvata i izvršava eksplicitno (TestClient bez
    # `with` ne garantuje da pozadinski zadatak stigne da se izvrši). Negativni testovi mere „nijedan zadatak nije zakazan“.
    b.odlozeni = []

    class _Asyncio:
        def __getattr__(self, ime):
            return getattr(asyncio, ime)

        def create_task(self, coro):
            b.odlozeni.append(coro)
    monkeypatch.setattr(MA, "asyncio", _Asyncio())
    # DEFAULT-i iz migracije 088 (baza u memoriji ih inače ne zna)
    b.podrazumevano.setdefault("staging_memory", {}).update({"status": "pending", "is_lawyer_approved": False,
                                                            "pinecone_indexed": False, "quality_detail": {}, "naziv": ""})
    return k, b, pid, doks, snimljeno


def _nacrti(b, pid):
    """Izvrši zakazane zadatke rute (upis na pregled), pa vrati nacrte predmeta."""
    while b.odlozeni:
        asyncio.run(b.odlozeni.pop(0))
    return [s for s in b.tabele["staging_memory"] if s.get("predmet_id") == pid]


def _pisi(k, pid, h=A, zadatak=ZADATAK):
    r = k.post("/api/agents/run", json={"agent": "drafting", "task": zadatak, "predmet_id": pid}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


@treba_ocr
def test_nacrt_iz_spisa_ide_na_pregled_izmena_odobrenje_docx(nacrt):
    k, b, pid, doks, snimljeno = nacrt
    o = _pisi(k, pid)
    poruka = snimljeno[-1]
    # nacrt se piše iz AKTUELNOG spisa: svi dokumenti, sporne tačke, pravila (izvor, [PROVERITI], sporno ostaje sporno)
    tekst = poruka["user"].rsplit("Zahtev:", 1)[0]
    assert o["izvori_predmeta"]["svi_dokumenti_u_celini"] is True
    assert all(gc.NAVODI[n]["tekst"] in tekst for n in ("N-09", "N-11", "N-04", "N-15")) and "SPORNE TAČKE PREDMETA" in tekst
    for pravilo in ("ISKLJUČIVO iz dokumenata", "[PROVERITI: …]", "ono što je SPORNO ostaje sporno i u nacrtu",
                    "[PROVERITI član zakona]"):
        assert pravilo in poruka["system"], pravilo
    # → na pregled (staging), sa serverskom napomenom; čuvar citata označio izmišljen član
    assert o["provera_citata"]["status"] == "NEPROVERENI"
    [st] = _nacrti(b, pid)
    assert st["status"] == "pending" and st["tip"] == "nacrt_iz_spisa" and st["user_id"] == "uid-A"
    # C3b: AI radni predlog (ceo) | serverska granica | interne napomene (provera, procesno stanje)
    from shared.nacrt_za_sud import GRANICA
    assert st["tekst"].count(GRANICA) == 1
    tekst_sud, napomena = st["tekst"].split(GRANICA)
    assert tekst_sud.strip() == NACRT == o["predlog_teksta"]
    assert "PROVERA PRE UPOTREBE" in napomena
    assert "čl. 999" in napomena and "NIJE pročitao: nema" in napomena
    # deterministički signal procesnog stanja: doslovni izvodi iz spisa, sa oznakom dokumenta (interno)
    assert "(DOK-07, zapisnik sa rocista (sinteticki predmet), 15.07.2026.: „Sud prihvata predlog za dopunu vestacenja.“)" in napomena
    assert "„Sud nalaze tuzenom da dostavi gradjevinski dnevnik u roku od 15 dana.“" in napomena
    assert "„Sledece rociste zakazano je za 18.11.2026. godine.“" in napomena
    # V2 kartica Nacrt: AI predlog na listi; ne menja se i ne odobrava (C3b FINAL CLOSURE)
    lista = k.get(f"/api/staging/predmet/{pid}", headers=A).json()["stavke"]
    assert [x["id"] for x in lista] == [st["id"]]
    assert k.patch(f"/api/staging/{st['id']}/tekst", json={"tekst": "Izmena."}, headers=A).status_code == 409
    assert k.post(f"/api/staging/{st['id']}/approve", headers=A).status_code == 409
    # → dokument za sud: usvojene stavke S-01..S-05 (bez upozorenja AI), advokat ispravlja izmišljen član, odluke o
    # procesnim tačkama, odobrenje tačnog teksta, DOCX = odobren tekst (bez naslova i podnožja sistema)
    from tests import c3b_usvajanje_pomoc as U
    assert [s["id"] for s in U.predlog(k, A, st["id"])["predlog"]["stavke"]] == [f"S-0{i}" for i in range(1, 7)]
    dok, d = U.ceo_tok(k, A, st["id"], ["S-01", "S-02", "S-03", "S-04", "S-05"],
                       izmeni=lambda t: U.bez_oznaka(t).replace("Pozivamo se na cl. 999 ZOO.", "Pozivamo se na cl. 154 ZOO.")
                       .replace("[PROVERITI: adresa]", "Primergrad, Fiktivna 1"))
    assert d.status_code == 200, d.text
    red = next(s for s in b.tabele["staging_memory"] if s["id"] == dok["id"])
    assert red["is_lawyer_approved"] is True and red["approved_by"] == "uid-A" and red["tip"] == "dokument_za_sud"
    pasusi = [p for p in U.docx_pasusi(d.content) if p.strip()]
    assert pasusi == [p for p in red["tekst"].split("\n") if p.strip()]                  # DOCX = odobren tekst
    assert "hidroizolacija na spoju atike" in red["tekst"] and "DOK-" not in red["tekst"] and "999" not in red["tekst"] and "⚠️" not in red["tekst"]
    assert "Vindex" not in U.docx_podnozje(d.content) and "NACRT IZ SPISA" not in "\n".join(pasusi)
    # opšti izvoz teksta iz pregledača za nacrt iz spisa / dokument za sud → 409 (GATE-00 N1)
    for tip in ("nacrt_iz_spisa", "dokument_za_sud"):
        r = k.post("/api/nacrti/export/docx", json={"tekst": red["tekst"], "naslov": "X", "tip": tip}, headers=A)
        assert r.status_code == 409


@treba_ocr
def test_odbijen_nacrt_nije_odobren_i_tudj_korisnik_ne_odlucuje(nacrt):
    k, b, pid, doks, snimljeno = nacrt
    _pisi(k, pid)
    [st] = _nacrti(b, pid)
    assert k.post(f"/api/staging/{st['id']}/approve", headers=B).status_code == 404
    assert k.post(f"/api/staging/{st['id']}/dokument-za-sud", headers=B).status_code == 404
    assert k.get(f"/api/staging/predmet/{pid}", headers=B).json().get("stavke", []) == []
    assert k.post(f"/api/staging/{st['id']}/reject", headers=A).status_code == 200
    red = next(s for s in b.tabele["staging_memory"] if s["id"] == st["id"])
    assert red["status"] == "rejected" and not red.get("is_lawyer_approved")
    assert k.post(f"/api/staging/{st['id']}/approve", headers=A).status_code == 409           # AI predlog se ne odobrava
    assert k.post(f"/api/staging/{st['id']}/dokument-za-sud", headers=A).status_code == 409   # odbačen predlog
    assert not next(s for s in b.tabele["staging_memory"] if s["id"] == st["id"]).get("is_lawyer_approved")


@treba_ocr
def test_bez_predmeta_ili_drugi_savetnik_nema_nacrta_i_nema_spoljnog_slanja(nacrt):
    k, b, pid, doks, snimljeno = nacrt
    from tests.ns005_harness import SPOLJNI_POKUSAJI
    n0 = len(SPOLJNI_POKUSAJI)
    r = k.post("/api/agents/run", json={"agent": "drafting", "task": ZADATAK}, headers=A)
    assert r.status_code == 200
    r = k.post("/api/agents/run", json={"agent": "research", "task": ZADATAK, "predmet_id": pid}, headers=A)
    assert r.status_code == 200
    _pisi(k, pid, h=B)                                             # B traži A-ov predmet: ništa se ne upisuje
    assert b.odlozeni == []                                        # nijedan upis na pregled nije ni zakazan
    assert _nacrti(b, pid) == []
    assert len(SPOLJNI_POKUSAJI) == n0                            # nema slanja sudu/trećem licu (nijedna spoljna veza)


@treba_ocr
def test_obrisan_dokument_se_ne_koristi_kao_aktuelan(nacrt):
    k, b, pid, doks, snimljeno = nacrt
    did = doks["DOK-06"]["id"]
    from shared.vector_deletion import Ishod, Rezultat
    b.rpc_impl["invalidate_dokument_relational_and_emit_event"] = _brisanje_rpc
    b.rpc_impl["invalidate_dokument_and_ai_claims_and_emit_event"] = _atomsko_rpc
    with patch("shared.vector_deletion.obrisi_vektore_dokumenta", lambda *a, **kw: Rezultat(Ishod.DELETED, obrisano=1, ocekivano=1)), \
            patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()):
        assert k.delete(f"/api/predmeti/{pid}/dokumenti/{did}", headers=A).status_code == 200
    _do_kraja_dogadjaja(b, najvise=20)
    o = _pisi(k, pid)
    tekst = snimljeno[-1]["user"].rsplit("Zahtev:", 1)[0]
    assert gc.NAVODI["N-11"]["tekst"] not in tekst                  # obrisan izvor nije u kontekstu nacrta
    assert o["izvori_predmeta"]["dokumenata_u_predmetu"] == 6
    # DOK-06 je tražen u zadatku, a više ne postoji: prijavljeno, i ide u napomenu nacrta na pregledu
    assert [x["oznaka"] for x in o["izvori_predmeta"]["trazeni_nisu_dostavljeni"]] == ["DOK-06"]
    [st] = _nacrti(b, pid)
    assert "Tražen u zadatku, a NIJE dostavljen: DOK-06" in st["tekst"].split("PROVERA PRE UPOTREBE")[1]
    put = os.environ.get("MIR001_SNIMAK")
    if put:
        with open(put, "w", encoding="utf-8") as f:
            json.dump({"N_brisan": {"agent": "drafting", "pitanje": ZADATAK, "poruka": snimljeno[-1]}}, f, ensure_ascii=False, indent=1)


@treba_ocr
def test_snimak_za_stvaran_model(nacrt):
    k, b, pid, doks, snimljeno = nacrt
    _pisi(k, pid)
    put = os.environ.get("MIR001_SNIMAK_NACRT")
    if put:
        with open(put, "w", encoding="utf-8") as f:
            json.dump({"N": {"agent": "drafting", "pitanje": ZADATAK, "poruka": snimljeno[-1]}}, f, ensure_ascii=False, indent=1)


@treba_ocr
def test_odobren_nacrt_iz_spisa_ne_postaje_izvor_ni_znanje_kancelarije(nacrt, monkeypatch):
    """I sa ocenom kvaliteta iznad praga: odobren AI nacrt iz spisa ne ide u bazu znanja ni u dokumente predmeta."""
    k, b, pid, doks, snimljeno = nacrt
    import services.quality_gate as QG

    async def _visoka(tekst, tip):
        return {"confidence_score": 0.95, "detail": {}}
    monkeypatch.setattr(QG, "evaluate_draft_quality", _visoka)
    _pisi(k, pid)
    [st] = _nacrti(b, pid)
    dok_pre = len(b.tabele["predmet_dokumenti"])
    # GATE-00 N3: promocija se BROJI (ruta guta izuzetak, pa `side_effect=AssertionError` ne bi ništa dokazao)
    import routers.drafting as D
    promocije = []

    async def _promocija(supa, red):
        promocije.append(red.get("id"))
        return True
    monkeypatch.setattr(D, "_promote_staged_draft_to_pinecone", _promocija)
    r = k.post(f"/api/staging/{st['id']}/approve", headers=A)
    assert r.status_code == 409 and r.json()["detail"]["razlog"] == "AI_RADNI_PREDLOG", r.text   # predlog se ne odobrava
    from tests import c3b_usvajanje_pomoc as U
    dok, d = U.ceo_tok(k, A, st["id"], ["S-02"])
    assert d.status_code == 200 and promocije == [] and len(b.tabele["predmet_dokumenti"]) == dok_pre
    red = next(s for s in b.tabele["staging_memory"] if s["id"] == dok["id"])
    assert red["status"] == "approved" and red["confidence_score"] == 0 and not red.get("pinecone_indexed")
    # ni ponovnim upisom: V2 ne nudi dugme, a ruta odbija PRE preuzimanja — ni predlog ni dokument za sud
    assert all(x["ponovni_upis_moguc"] is False for x in k.get(f"/api/staging/predmet/{pid}", headers=A).json()["stavke"])
    for sid in (st["id"], dok["id"]):
        r = k.post(f"/api/staging/{sid}/ponovi-upis", headers=A)
        assert r.status_code == 409 and r.json()["detail"]["razlog"] == "NACRT_IZ_SPISA", r.text
    assert promocije == [] and len(b.tabele["predmet_dokumenti"]) == dok_pre
