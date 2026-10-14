# -*- coding: utf-8 -*-
"""VCR002 Task 03 — Bojan B6/B8/B9/B11/B12: JEDAN predmet, VIŠE međusobno povezanih dokumenata, kroz STVARNE rute.

Lanac: predmet → tri dokumenta kroz Smart Intake (stvaran worker, pypdf) → tvrdnje (Evidence Vault, kanonski pisac)
→ Genome (STVARNO osvežavanje kroz dispečer; zamenjen je samo model) → protivrečnost nad STVARNIM tvrdnjama dva
dokumenta → hronologija sa identitetom izvora → rok iz dokumenta „čeka potvrdu“ → Case Action → potvrda advokata
→ pravno pitanje u kontekstu predmeta → istorija → brisanje izvora (SourceInvalidated).

Izmišljen spor (bez stvarnih lica): Zlatibor Fiktivić protiv Primer Gradnja DOO, broj P 4711/2026.
Namerna protivrečnost: tužba kaže da je rešenje uručeno 17.03.2025, dostavnica kaže 25.03.2025.
Nedostaje: ugovor o radu. Rok: zapisnik određuje rok za izjašnjenje.

Šta je simulirano: prijava (token), modeli (klasifikacija tvrdnji = rečenice sa datumom iz STVARNOG teksta; Genome
= deterministički izlaz koji koristi STVARNE oznake DOK-NN i CLAIM-NNN iz prompta), embedding/Pinecone.
"""
import asyncio
import copy
import json
import re
import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from tests import ns006_realni_predmet as rp
from tests.test_osb002_solo_tok import A, B, _do_kraja_dogadjaja, _pdf, _prijem_dokumenta, solo  # noqa: F401

ROK = (date.today() + timedelta(days=14)).isoformat()
TUZBA = ["OSNOVNI SUD U KRAGUJEVCU", "Broj predmeta: P 4711/2026",
         "Tuzilac: Zlatibor Fiktivic iz Kraljeva", "Tuzeni: Primer Gradnja DOO iz Cacka",
         "Resenje o otkazu je uruceno tuziocu 17.03.2025. godine."]
DOSTAVNICA = ["POSTA - DOSTAVNICA", "Broj predmeta: P 4711/2026", "Primalac: Zlatibor Fiktivic, Kraljevo",
              "Posiljka je urucena primaocu dana 25.03.2025. godine."]
ZAPISNIK = ["ZAPISNIK SA PRIPREMNOG ROCISTA", "Broj predmeta: P 4711/2026",
            "Sud nalaze tuzenom da se izjasni o navodima tuzbe.",
            f"Rok za izjasnjenje istice {date.fromisoformat(ROK).strftime('%d.%m.%Y')}. godine."]


def _genome_model(pozivi):
    """Model Genome-a (zamena). Čita STVARAN prompt: oznake dokumenata `[DOK-NN: ime` i tvrdnji `CLAIM-NNN: tekst`,
    i vraća hronologiju/rok/protivrečnost koje se pozivaju SAMO na te oznake — server ih razrešava u identitete."""
    async def _pozovi(client, combined, n):
        pozivi.append(combined)
        dok = {ime: oz for oz, ime in re.findall(r"\[(DOK-\d+): ([^\]|]+?)(?: \||\])", combined)}
        claim = dict(re.findall(r"(CLAIM-\d+): ([^\n]+)", combined))
        g = copy.deepcopy(rp._genome(0, False, 0, 0))
        for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(polje, None)
        g["stranke"] = [{"uloga": "tuzilac", "ime": "Zlatibor Fiktivic"}, {"uloga": "tuzeni", "ime": "Primer Gradnja DOO"}]
        g["datumi_kljucni"] = []
        g["rokovi_kriticni"] = []
        g["kontradikcije"] = []
        g["nedostaje"] = [{"dokument": "Ugovor o radu", "hitnost": "kriticno", "opis": "Potreban za visinu zarade."}]
        if "Tuzba.pdf" in dok:
            g["datumi_kljucni"].append({"opis": "Rešenje o otkazu uručeno (po tužbi)", "datum": "2025-03-17", "znacaj": "kriticno",
                                        "lokacija": dok["Tuzba.pdf"]})
        if "Dostavnica.pdf" in dok:
            g["datumi_kljucni"].append({"opis": "Pošiljka uručena (po dostavnici)", "datum": "2025-03-25", "znacaj": "kriticno",
                                        "lokacija": dok["Dostavnica.pdf"]})
        if "Zapisnik.pdf" in dok:
            g["rokovi_kriticni"].append({"naziv": "Rok za izjašnjenje tuženog", "datum": ROK, "status": "aktivan",
                                         "opis": "Propuštanje vodi presudi zbog izostanka", "lokacija": dok["Zapisnik.pdf"]})
        c17 = [c for c, t in claim.items() if "17.03.2025" in t]
        c25 = [c for c, t in claim.items() if "25.03.2025" in t]
        if c17 and c25:
            g["kontradikcije"].append({"issue_label": "datum uručenja rešenja o otkazu", "claim_refs": [c17[0], c25[0]],
                                       "relation_type": "cinjenica_cinjenica", "opis": "Tužba: 17.03.2025; dostavnica: 25.03.2025.",
                                       "lokacija_1": dok.get("Tuzba.pdf", ""), "lokacija_2": dok.get("Dostavnica.pdf", ""), "tezina": "kriticna"})
        return json.dumps(g, ensure_ascii=False)
    return _pozovi


@pytest.fixture
def predmet(solo, monkeypatch):
    k, b = solo
    import routers.case_dna as cd
    monkeypatch.setattr(cd, "_pozovi_genome_api", _genome_model(b.genome_pozivi))
    import shared.audit_immutable as audit
    from api import _get_supa

    async def _log(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
        r = _get_supa().table("audit_immutable").insert({"action": action, "user_id": user_id, "resource_type": resource_type,
                                                       "resource_id": resource_id, "metadata": metadata or {}}).execute()
        return (r.data or [{}])[0].get("id") or "ok"
    monkeypatch.setattr(audit, "log_action", _log)
    from shared import rokovi
    rokovi._resetuj_sondu()
    kl = k.post("/klijenti", json={"ime": "Zlatibor", "prezime": "Fiktivic"}, headers=A)
    p = k.post("/api/predmeti", json={"naziv": "Fiktivic protiv Primer Gradnja", "tip": "Radni spor", "opis": "Nezakonit otkaz"}, headers=A)
    assert kl.status_code == 200 and p.status_code == 200, (kl.text, p.text)
    pid = p.json()["predmet"]["id"]
    assert k.post(f"/api/predmeti/{pid}/confirm-links", json={"klijent_ids": [kl.json()["klijent"]["id"]], "uloga": "tuzilac"},
                  headers=A).status_code == 200
    doks = {}
    for ime, redovi in (("Tuzba.pdf", TUZBA), ("Dostavnica.pdf", DOSTAVNICA), ("Zapisnik.pdf", ZAPISNIK)):
        _, fin = _prijem_dokumenta(k, b, pid, sadrzaj=_pdf(redovi), ime=ime)
        assert fin["predmet_id"] == pid and fin["dokumenata_povezano"] == 1, fin
        _do_kraja_dogadjaja(b, najvise=10)
        doks[ime] = next(d["id"] for d in b.tabele["predmet_dokumenti"] if d["naziv_fajla"] == ime and d["predmet_id"] == pid)
    yield k, b, pid, doks
    rokovi._resetuj_sondu()


def _rok_akcije(b, pid, status="open"):
    return [a for a in b.tabele["case_actions"] if a["predmet_id"] == pid and a["status"] == status
            and (a.get("dokaz") or {}).get("izvor") == "predmet_hronologija"]


def _rokovi(b, pid):
    return [h for h in b.tabele["predmet_hronologija"] if h["predmet_id"] == pid and h.get("vrsta") == "rok"]


# ── B6: više dokumenata, jedan predmet, stabilni identiteti ────────────────────────────────────────────────────
def test_B6_tri_dokumenta_jedan_predmet_stabilni_identiteti_i_tvrdnje_po_izvoru(predmet):
    k, b, pid, doks = predmet
    assert len(set(doks.values())) == 3
    assert all(d["predmet_id"] == pid for d in b.tabele["predmet_dokumenti"])            # ništa nije napravilo drugi predmet
    assert len([p for p in b.tabele["predmeti"] if p["user_id"] == "uid-A"]) == 1
    tvrdnje = [t for t in b.tabele["predmet_dokazi"] if t["predmet_id"] == pid]
    po_dok = {ime: [t["tvrdnja"] for t in tvrdnje if t["dokument_id"] == did] for ime, did in doks.items()}
    assert any("17.03.2025" in t for t in po_dok["Tuzba.pdf"]) and any("25.03.2025" in t for t in po_dok["Dostavnica.pdf"])
    assert not any("25.03.2025" in t for t in po_dok["Tuzba.pdf"])                     # tvrdnja ne „preskače“ dokument
    # identitet je stabilan: detalj predmeta posle svih osvežavanja vraća iste dokumente
    d = k.get(f"/api/predmeti/{pid}", headers=A).json()
    assert sorted(x["id"] for x in d["dokumenti"]) == sorted(doks.values())


# ── B8 / B12: hronologija i Genome nose identitet izvora, ne samo ime fajla ────────────────────────────────────
def test_B8_B12_hronologija_i_genome_nose_dokument_id(predmet):
    k, b, pid, doks = predmet
    red = next(p for p in b.tabele["predmeti"] if p["id"] == pid)
    assert (red.get("case_dna") or {}).get("verzija", 0) >= 3                              # Genome osvežen posle svakog dokumenta
    assert "Zapisnik.pdf" in b.genome_pozivi[-1] and "Tuzba.pdf" in b.genome_pozivi[-1]   # poslednje osvežavanje vidi SVE
    g = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A)
    assert g.status_code == 200, g.text
    stavke = g.json()["hronologija"]["stavke"]
    izvori = {s["vrednost"]: (s.get("lokacija") or {}).get("dokument_id") for s in stavke}
    assert izvori["Rešenje o otkazu uručeno (po tužbi)"] == doks["Tuzba.pdf"]
    assert izvori["Pošiljka uručena (po dostavnici)"] == doks["Dostavnica.pdf"]


# ── B7/B12: protivrečnost nad STVARNIM tvrdnjama dva različita dokumenta ───────────────────────────────────────
def test_protivrecnost_pokazuje_na_stvarne_tvrdnje_razlicitih_dokumenata(predmet):
    k, b, pid, doks = predmet
    red = next(p for p in b.tabele["predmeti"] if p["id"] == pid)
    [kon] = red["case_dna"]["kontradikcije"]
    tvrdnje = {t["id"]: t for t in b.tabele["predmet_dokazi"] if t["predmet_id"] == pid}
    ids = kon["claim_ids"]
    assert len(ids) == 2 and all(i in tvrdnje for i in ids), kon                           # razrešeno u STVARNE redove
    assert {tvrdnje[i]["dokument_id"] for i in ids} == {doks["Tuzba.pdf"], doks["Dostavnica.pdf"]}
    assert "CLAIM-" not in json.dumps(kon.get("claim_ids"))                                # efemerna oznaka nije sačuvana kao identitet


# ── B9 / B11: rok iz dokumenta → obaveza čeka potvrdu → potvrda; bez duplikata ─────────────────────────────────
def test_B9_B11_rok_iz_dokumenta_ceka_potvrdu_jedna_akcija_i_potvrda_je_zatvara(predmet):
    """N03-FD7 (2026-10-14): Smart Intake rok sada IZJAVLJUJE `vrsta=rok`, pa je i on kandidat u pregledu. Genome i
    Smart Intake su dva proizvođača; da li je to ista obaveza, postojeći identifikatori NE dokazuju (Smart Intake red
    nema `dokument_id`, identitet odluke je id reda) — zato su to DVA kandidata, svaki sa svojom akcijom pregleda, i
    potvrda jednog NE zatvara drugi (N03-FD2: nema izvođenja ekvivalencije iz datuma/naziva)."""
    k, b, pid, doks = predmet
    rokovi = _rokovi(b, pid)
    [rok] = [r for r in rokovi if r.get("akter") == "Genome (AI)"]
    [si] = [r for r in rokovi if r.get("akter") == "Smart Intake"]
    assert len(rokovi) == 2
    assert rok["datum_iso"] == ROK and rok["dokument_id"] == doks["Zapisnik.pdf"] and rok["izvor"] == "AI_AUTONOMOUS"
    assert si["datum_iso"] == ROK and si["izvor"] == "AI_AUTONOMOUS" and si["dokument_naziv"] == "Zapisnik.pdf"
    akc = {a["dokaz"]["hronologija_id"]: a for a in _rok_akcije(b, pid)}
    assert set(akc) == {rok["id"], si["id"]} and all(a["tip"] == "PLANIRATI_ROKOVE" for a in akc.values())
    assert akc[rok["id"]]["dokaz"]["dokument_id"] == doks["Zapisnik.pdf"]
    assert all(a["dokaz"]["stanje_odluke"] == "UNCONFIRMED" and "čeka vašu potvrdu" in a["razlog"] for a in akc.values())
    # isti zaključeni rok ponovo izveden (ponovljeno osvežavanje Genome-a i dispečera) — ni treći rok ni treća akcija
    from services.event_bus import EventType, emit_durable
    asyncio.run(emit_durable(EventType.MANUAL_CORRECTION_APPLIED, "uid-A", pid, {"trigger": "test"}))
    assert k.post(f"/api/predmeti/{pid}/case-dna/refresh", headers=A).status_code in (200, 202, 409)
    _do_kraja_dogadjaja(b, najvise=10)
    assert len(_rokovi(b, pid)) == 2 and len(_rok_akcije(b, pid)) == 2
    # potvrda advokata se trajno beleži i zatvara akciju TOG roka; drugi kandidat i dalje čeka odluku
    r = k.post(f"/api/rokovi/{rok['id']}/potvrdi", json={}, headers=A)
    assert r.status_code == 200 and r.json()["stanje_odluke"] == "CONFIRMED", r.text
    _do_kraja_dogadjaja(b)
    assert [a["dokaz"]["hronologija_id"] for a in _rok_akcije(b, pid)] == [si["id"]]
    assert len(_rok_akcije(b, pid, "closed")) == 1
    assert any(a.get("action") and "rok" in str(a.get("action")).lower() for a in b.tabele["audit_immutable"])
    # B ne može da potvrdi/odbije tuđ rok
    assert k.post(f"/api/rokovi/{rok['id']}/odbij", json={}, headers=B).status_code in (403, 404)


# ── pravno pitanje u kontekstu predmeta + istorija ─────────────────────────────────────────────────────────────
def test_pravno_pitanje_vidi_predmet_i_cuva_istoriju_a_tudj_korisnik_ne(predmet):
    k, b, pid, doks = predmet
    import api
    upiti = []

    async def _pokreni(fn, pitanje_za_agenta, *a, **kw):
        upiti.append(pitanje_za_agenta)
        return {"status": "success", "data": "--- PRAVNI ZAKLJUČAK\nOdgovor.", "confidence": "HIGH", "top_score": 0.8,
                "confidence_detail": {"nivo": "HIGH"}, "izvori": [{"zakon": "zakon o radu", "clan": "Član 185"}]}
    with patch.object(api, "pokreni", _pokreni):
        q = k.post("/api/pitanje", json={"pitanje": "Koji datum uručenja je merodavan?", "predmet_id": pid}, headers=A)
        qb = k.post("/api/pitanje", json={"pitanje": "Koji datum uručenja je merodavan?", "predmet_id": pid}, headers=B)
    assert q.status_code == 200 and q.json()["kontekst_predmeta"] is True, q.text
    for iz_dokumenta in ("17.03.2025", "25.03.2025", "Rok za izjasnjenje"):          # tvrdnje SVA TRI dokumenta
        assert iz_dokumenta in upiti[0], iz_dokumenta
    assert "VINDEX_NEPOVERLJIVO" in upiti[0]                                             # u granici poverenja
    assert qb.json()["kontekst_predmeta"] is False and "17.03.2025" not in upiti[1]
    ist = [h for h in b.tabele["predmet_istorija"] if h["predmet_id"] == pid and h["pitanje"].startswith("Koji datum")]
    assert len(ist) == 1 and ist[0]["user_id"] == "uid-A"


# ── brisanje izvora: ne ostaje tiho merodavan ──────────────────────────────────────────────────────────────────
def _brisanje_rpc(baza, p):
    pre = len(baza.tabele["predmet_dokumenti"])
    baza.tabele["predmet_dokumenti"][:] = [d for d in baza.tabele["predmet_dokumenti"]
                                           if not (d["id"] == p["p_dokument_id"] and d["predmet_id"] == p["p_predmet_id"]
                                                   and d["user_id"] == p["p_user_id"])]
    if len(baza.tabele["predmet_dokumenti"]) == pre:
        return [{"invalidated": False}]
    for t in ("predmet_dokazi", "predmet_hronologija"):                 # FK ... ON DELETE SET NULL (016, 126)
        for r in baza.tabele[t]:
            if r.get("dokument_id") == p["p_dokument_id"]:
                r["dokument_id"] = None
    baza.tabele["events"].append({"id": p["p_event_id"], "event_type": "SourceInvalidated", "user_id": p["p_user_id"],
                                  "predmet_id": p["p_predmet_id"], "payload": {"source_type": "dokument", "source_id": p["p_dokument_id"]},
                                  "dispatched_at": None, "claimed_at": None, "dispatch_attempts": 0, "last_error": None,
                                  "created_at": "2099-01-01T00:00:00+00:00"})
    return [{"invalidated": True}]


def _atomsko_rpc(baza, p):
    """Model funkcije iz migracije 137 (VCR002 FIX 1): AI tvrdnje dokumenta se povlače, red briše i događaj upisuje
    zajedno — sve ili ništa. Sam SQL je dokazan nad pravim PostgreSQL-om (test_vcr002_rc_fix1_migracija137_pg.py)."""
    if not any(d["id"] == p["p_dokument_id"] and d["predmet_id"] == p["p_predmet_id"] and d["user_id"] == p["p_user_id"]
               for d in baza.tabele["predmet_dokumenti"]):
        return [{"invalidated": False, "tvrdnje_povucene": 0}]
    n = 0
    for t in baza.tabele["predmet_dokazi"]:
        if (t.get("dokument_id") == p["p_dokument_id"] and t["predmet_id"] == p["p_predmet_id"]
                and t["user_id"] == p["p_user_id"] and not t.get("deleted_at")
                and (t.get("izvor_tvrdnje") == "ai_klasifikacija"
                     or (t.get("izvor_tvrdnje") is None and t.get("nacin_pronalaska") in ("egzaktan", "normalizovan")))):
            t["deleted_at"] = "2099-01-01T00:00:00+00:00"
            n += 1
    _brisanje_rpc(baza, p)
    return [{"invalidated": True, "tvrdnje_povucene": n}]


def test_obrisan_izvor_nije_tiho_merodavan(predmet):
    """Obrisan dokument: nestaje iz predmeta, njegove AI tvrdnje se povlače (ne ulaze u Genome ni u kontekst pitanja),
    advokatova ručna tvrdnja koja ga navodi ostaje, a rok iz njega ostaje NEPOTVRĐEN (istorija, ne obaveza)."""
    k, b, pid, doks = predmet
    zap = doks["Zapisnik.pdf"]
    rucna = k.post(f"/api/evidence/predmeti/{pid}/dokaz", headers=A,
                   json={"tvrdnja": "Advokat: tuženi je usmeno priznao dug na ročištu.", "kategorija": "cinjenica", "dokument_id": zap})
    assert rucna.status_code == 200, rucna.text
    ai_zap = [t["id"] for t in b.tabele["predmet_dokazi"] if t["dokument_id"] == zap and t.get("izvor_tvrdnje") == "ai_klasifikacija"]
    assert ai_zap
    from shared.vector_deletion import Ishod, Rezultat
    b.rpc_impl["invalidate_dokument_relational_and_emit_event"] = _brisanje_rpc
    b.rpc_impl["invalidate_dokument_and_ai_claims_and_emit_event"] = _atomsko_rpc
    with patch("shared.vector_deletion.obrisi_vektore_dokumenta", lambda *a, **kw: Rezultat(Ishod.DELETED, obrisano=1, ocekivano=1)),             patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()):
        tudje = k.delete(f"/api/predmeti/{pid}/dokumenti/{zap}", headers=B)
        r = k.delete(f"/api/predmeti/{pid}/dokumenti/{zap}", headers=A)
    assert tudje.status_code == 404
    assert r.status_code == 200 and r.json()["tvrdnje_povucene"] == len(ai_zap), r.text
    _do_kraja_dogadjaja(b, najvise=10)
    assert zap not in [x["id"] for x in k.get(f"/api/predmeti/{pid}", headers=A).json()["dokumenti"]]
    tvrdnje = {t["id"]: t for t in b.tabele["predmet_dokazi"]}
    assert all(tvrdnje[i].get("deleted_at") for i in ai_zap)                                 # povučene, ne fizički obrisane
    zive = [t for t in b.tabele["predmet_dokazi"] if t["predmet_id"] == pid and not t.get("deleted_at")]
    assert any(t["tvrdnja"].startswith("Advokat:") for t in zive)                            # advokatov rad ostaje
    assert any("17.03.2025" in t["tvrdnja"] for t in zive)                                   # tvrdnje drugih dokumenata ostaju
    # sledeće osvežavanje Genome-a ne vidi ni dokument ni njegove tvrdnje
    n = len(b.genome_pozivi)
    k.post(f"/api/predmeti/{pid}/case-dna/refresh", headers=A)
    _do_kraja_dogadjaja(b, najvise=10)
    assert len(b.genome_pozivi) > n
    assert "Zapisnik.pdf" not in b.genome_pozivi[-1] and "izjasnjenje" not in b.genome_pozivi[-1].lower()
    # ni kontekst pravnog pitanja
    import api
    upiti = []

    async def _pokreni(fn, pitanje_za_agenta, *a, **kw):
        upiti.append(pitanje_za_agenta)
        return {"status": "success", "data": "Odgovor.", "confidence": "HIGH", "top_score": 0.8, "confidence_detail": {}, "izvori": []}
    with patch.object(api, "pokreni", _pokreni):
        assert k.post("/api/pitanje", json={"pitanje": "Koji su rokovi?", "predmet_id": pid}, headers=A).status_code == 200
    assert "izjasnjenje" not in upiti[0].lower() and "17.03.2025" in upiti[0]
    # rok iz obrisanog dokumenta: istorijski red ostaje (126: ON DELETE SET NULL), ali NIJE potvrđen ni operativan
    for rok in _rokovi(b, pid):
        assert rok.get("dokument_id") is None
    for a_ in _rok_akcije(b, pid, "open"):
        assert a_["dokaz"]["stanje_odluke"] == "UNCONFIRMED"


def test_ponovno_brisanje_istog_dokumenta_je_404_bez_dodatnih_izmena(predmet):
    k, b, pid, doks = predmet
    from shared.vector_deletion import Ishod, Rezultat
    b.rpc_impl["invalidate_dokument_relational_and_emit_event"] = _brisanje_rpc
    b.rpc_impl["invalidate_dokument_and_ai_claims_and_emit_event"] = _atomsko_rpc
    with patch("shared.vector_deletion.obrisi_vektore_dokumenta", lambda *a, **kw: Rezultat(Ishod.DELETED, obrisano=1, ocekivano=1)),             patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()):
        assert k.delete(f"/api/predmeti/{pid}/dokumenti/{doks['Tuzba.pdf']}", headers=A).status_code == 200
        pre = json.dumps(b.tabele["predmet_dokazi"], sort_keys=True, default=str)
        assert k.delete(f"/api/predmeti/{pid}/dokumenti/{doks['Tuzba.pdf']}", headers=A).status_code == 404
    assert json.dumps(b.tabele["predmet_dokazi"], sort_keys=True, default=str) == pre
