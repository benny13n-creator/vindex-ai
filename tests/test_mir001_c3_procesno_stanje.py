# -*- coding: utf-8 -*-
"""MIR001 FINAL CLOSURE — TASK-C3: nacrt svestan procesnog stanja.

Golden Case kroz STVARNU rutu `POST /api/agents/run` (agent `drafting`), stvaran spis (OCR), staging pregled. Model je
zamenjen nacrtom zadatog teksta (snimač poruke); sadržaj STVARNOG modela meri `docs/v2-execution/mir001_c3_model/`.
C3b STRUCTURAL (zamenilo C3 blok i oznaku na mestu): (1) procesno stanje servera (`shared/procesno_stanje`) ide u poruku,
u granici poverenja, pre zahteva, a pravila u sistemsku poruku. C3b FINAL CLOSURE TASK-00: leksička kapija teksta za
sud je povučena (GATE-03 C3B_FAIL) — tekst modela je AI RADNI PREDLOG, ceo i bez brisanja (i protivrečna rečenica i
upozorenje AI ostaju vidljivi advokatu), a DOCX ga ne izvozi ni posle izmene.
Čiste provere `_protivreci_odlukama` (C3) ispod ostaju — funkcija postoji, ali nacrt iz spisa je više ne koristi.
"""
import json
import os
import types
from unittest.mock import MagicMock, patch

import pytest

from tests import mir001_golden_case as gc
from tests.test_mir001_t06_nacrt_iz_spisa import NACRT, ZADATAK, _nacrti, _pisi, nacrt, treba_ocr  # noqa: F401
from tests.test_mir001_t04_savetnik_spis import savetnik  # noqa: F401
from tests.test_osb002_solo_tok import A, _do_kraja_dogadjaja, solo  # noqa: F401
from tests.test_vcr002_t03_visedokumentni_predmet import _atomsko_rpc, _brisanje_rpc
from tests.nacrt_json_zamena import kao_json

PROTIVRECAN = ("PRIVREDNOM SUDU U PRIMERGRADU\nBroj predmeta: P 9901/2026\n"
               "Tuzilac osporava navode tuzenog (DOK-06). Tuzilac smatra da dopuna vestacenja nije potrebna.\n"
               "Smatramo da dodatni uvid u gradjevinski dnevnik nije neophodan.\n"
               "Tuzilac predlaze da se na rocistu 18.11.2026. donese odluka.\n"
               "⚠️ Ovaj nacrt generisala je AI i mora ga pregledati i potpisati ovlašćeni advokat pre podnošenja sudu.")
DOSLEDAN = ("PRIVREDNOM SUDU U PRIMERGRADU\nBroj predmeta: P 9901/2026\n"
            "Sud je vec prihvatio predlog za dopunu vestacenja (DOK-07). Tuzilac se ne protivi dopuni vestacenja.\n"
            "Tuzilac se protivi tvrdnjama tuzenog da vestak nije izvrsio uvid u gradjevinski dnevnik.\n"
            "Tuzilac ce se izjasniti po izvrsenju naloga suda.\n"
            "⚠️ Ovaj nacrt generisala je AI i mora ga pregledati i potpisati ovlašćeni advokat pre podnošenja sudu.")


def _model_vraca(monkeypatch, snimljeno, tekst):
    import routers.multi_agent as MA

    def _model(client, system, user_msg):
        snimljeno.append({"system": MA._sa_granicom(system), "user": user_msg})
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=tekst))])
    monkeypatch.setattr(MA, "_pozovi_agent_api", _model)
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", kao_json(_model))     # C3b: nacrt iz spisa = JSON


@treba_ocr
def test_procesno_stanje_servera_je_u_poruci_a_pravila_u_sistemskoj(nacrt):
    """C3b STRUCTURAL: blok PROCESNO STANJE piše server iz `shared/procesno_stanje` (oznake [[PS-nn]], doslovni izvodi u
    granici poverenja, posle spisa, pred zahtevom); pravila formata i procesnih tvrdnji su u SISTEMSKOJ poruci."""
    from shared.nacrt_za_sud import PRAVILA_ZA_MODEL
    k, b, pid, doks, snimljeno = nacrt
    _pisi(k, pid)
    u, sistem = snimljeno[-1]["user"], snimljeno[-1]["system"]
    natpis = "PROCESNO STANJE IZ SPISA — utvrdio SISTEM"
    assert u.rfind(natpis) > u.rfind("[KRAJ DOKUMENATA]") and u.rfind(natpis) < u.rfind("Zahtev:")
    blok = u.split(natpis, 1)[1].split("\n\nZahtev:", 1)[0]
    granica = blok.split("<VINDEX_NEPOVERLJIVO_DOKUMENT_ILI_OCR_", 1)[1].split("</VINDEX_NEPOVERLJIVO", 1)[0]
    assert "DOK-07 | akter po tekstu: SUD | vrsta (kandidat): SUD_PRIHVATA | izvod: Sud prihvata predlog za dopunu vestacenja." in granica
    assert "[[PS-" in granica and "NIJE UTVRĐENO: DOK-07: da li je postupljeno po nalogu" in granica
    assert PRAVILA_ZA_MODEL in sistem.split("GRANICA INSTRUKCIONOG AUTORITETA")[0] and PRAVILA_ZA_MODEL not in u
    assert "PRAVILO ZA OVAJ NACRT" not in u                                    # stari blok C3 više ne ide u poruku


@treba_ocr
def test_bez_odluke_u_spisu_protivljenje_dopuni_ostaje_u_tekstu_za_sud(nacrt, monkeypatch):
    """Negativni scenario: DOK-07 (jedini dokument sa odlukom suda) nije u predmetu → nacrt koji se protivi dopuni je
    ceo u AI predlogu; procesno stanje kaže da sudski dokument nije prepoznat."""
    from shared.nacrt_za_sud import GRANICA
    k, b, pid, doks, snimljeno = nacrt
    from shared.vector_deletion import Ishod, Rezultat
    b.rpc_impl["invalidate_dokument_relational_and_emit_event"] = _brisanje_rpc
    b.rpc_impl["invalidate_dokument_and_ai_claims_and_emit_event"] = _atomsko_rpc
    with patch("shared.vector_deletion.obrisi_vektore_dokumenta", lambda *a, **kw: Rezultat(Ishod.DELETED, obrisano=1, ocekivano=1)), \
            patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()):
        assert k.delete(f"/api/predmeti/{pid}/dokumenti/{doks['DOK-07']['id']}", headers=A).status_code == 200
    _do_kraja_dogadjaja(b, najvise=20)
    _model_vraca(monkeypatch, snimljeno, PROTIVRECAN)
    o = _pisi(k, pid)
    assert "SUD_PRIHVATA" not in snimljeno[-1]["user"]
    assert o["predlog_teksta"] == PROTIVRECAN and o["status_teksta"] == "AI_RADNI_PREDLOG"
    put = os.environ.get("MIR001_C3_SNIMAK_NEG")                        # poruka za merenje stvarnim modelom
    if put:
        with open(put, "w", encoding="utf-8") as f:
            json.dump({"N": {"agent": "drafting", "pitanje": ZADATAK, "poruka": snimljeno[-1]}}, f, ensure_ascii=False, indent=1)
    [st] = _nacrti(b, pid)
    sud, interno = st["tekst"].split(GRANICA)
    assert sud.strip() == PROTIVRECAN
    assert "nema dokumenta prepoznatog kao sudski" in interno


@treba_ocr
def test_protivrecna_recenica_ostaje_vidljiva_u_ai_predlogu_a_predlog_se_ne_izvozi(nacrt, monkeypatch):
    """Povučena kapija je ovu rečenicu brisala (čuvar mesta); sada advokat vidi CEO predlog i stanje iz spisa, a predlog
    nije dokument za sud — DOCX 409 i posle advokatove izmene."""
    from shared.nacrt_za_sud import GRANICA
    k, b, pid, doks, snimljeno = nacrt
    _model_vraca(monkeypatch, snimljeno, PROTIVRECAN)
    o = _pisi(k, pid)
    assert o["predlog_teksta"] == PROTIVRECAN and "[IZOSTAVLJENO" not in o["odgovor"]
    [st] = _nacrti(b, pid)
    predlog, interno = st["tekst"].split(GRANICA)
    assert predlog.strip() == PROTIVRECAN and "IZOSTAVLJENO IZ TEKSTA ZA SUD" not in interno
    assert "Sud prihvata predlog za dopunu vestacenja." in interno                              # stanje i dalje navedeno
    assert k.post(f"/api/staging/{st['id']}/docx", headers=A).status_code == 409
    izmena = predlog.replace("Tuzilac smatra da dopuna vestacenja nije potrebna.", "")
    assert k.patch(f"/api/staging/{st['id']}/tekst", json={"tekst": izmena + GRANICA + interno}, headers=A).status_code == 409
    assert k.post(f"/api/staging/{st['id']}/docx", headers=A).status_code == 409


@treba_ocr
def test_dosledan_nacrt_je_ceo_u_ai_predlogu(nacrt, monkeypatch):
    k, b, pid, doks, snimljeno = nacrt
    _model_vraca(monkeypatch, snimljeno, DOSLEDAN)
    o = _pisi(k, pid)
    assert o["predlog_teksta"] == DOSLEDAN


@treba_ocr
def test_drugi_savetnici_bez_bloka_i_bez_oznake(nacrt, monkeypatch):
    k, b, pid, doks, snimljeno = nacrt
    _model_vraca(monkeypatch, snimljeno, PROTIVRECAN)
    r = k.post("/api/agents/run", json={"agent": "litigation", "task": "Strategija za tuzioca.", "predmet_id": pid}, headers=A)
    assert r.status_code == 200, r.text
    assert "PROCESNO STANJE IZ SPISA" not in snimljeno[-1]["user"] and "PROCESNO STANJE — ODLUKE SUDA" not in snimljeno[-1]["user"]
    assert r.json()["odgovor"] == PROTIVRECAN and "predlog_teksta" not in r.json()              # predlog samo za nacrt


def test_ponovni_predlog_odbijenog_i_negirane_negacije():
    from routers.multi_agent import _protivreci_odlukama as p
    odbijeno = [{"oznaka": "DOK-09", "tekst": "Sud odbija predlog tuzioca za saslusanje svedoka Marka Markovica."}]
    assert p("Tuzilac predlaze saslusanje svedoka Marka Markovica.", odbijeno)
    assert not p("Sud je odbio saslusanje svedoka Marka Markovica (DOK-09), pa tuzilac ne ponavlja taj predlog.", odbijeno)
    prihvaceno = [{"oznaka": "DOK-07", "tekst": "Sud prihvata predlog za dopunu vestacenja."}]
    assert not p("Tuzilac nema primedbi na dopunu veštačenja.", prihvaceno)
    assert not p("Tužilac se neće protiviti dopuni veštačenja.", prihvaceno)
    assert not p("Tužilac se protivi navodima tuženog o dopuni veštačenja.", prihvaceno)
    assert p("Dopuna veštačenja je nepotrebna.", prihvaceno)
    assert not p("Veštak je nalaz dao, a tuženi nije potreban dokaz pružio.", prihvaceno)   # samo „veštak“ — nedovoljno
    nalog = [{"oznaka": "DOK-07", "tekst": "Sud nalaze tuzenom da dostavi gradjevinski dnevnik u roku od 15 dana."}]
    assert p("Uvid u građevinski dnevnik nije nužan.", nalog)                              # đ → dj, „nužan“


def test_gate_c3_ivicni_slucajevi():
    """GATE-C3: zakazivanje (jedna osnova reči) nije predmet provere; ponovljena rečenica = dve oznake na dva mesta;
    množina i „ne postoji potreba“ / „izlišna“; protivljenje navodima stranke JESTE sporno kad pominje i predlog."""
    from routers.multi_agent import _oznaci_protivrecnosti as oz
    from routers.multi_agent import _protivreci_odlukama as p
    zakazano = [{"oznaka": "DOK-07", "tekst": "Sledece rociste zakazano je za 18.11.2026. godine."}]
    assert not p("Na ročištu će se tužilac protiviti saslušanju svedoka.", zakazano)
    prihvaceno = [{"oznaka": "DOK-07", "tekst": "Sud prihvata predlog za dopunu vestacenja."}]
    tekst = "Dopuna vestacenja nije potrebna.\nDopuna vestacenja nije potrebna."             # ista rečenica dvaput
    n = p(tekst, prihvaceno)
    assert len(n) == 2
    out = oz(tekst, n)
    assert [l.count("[PROVERITI PROCESNO STANJE") for l in out.splitlines()] == [1, 1]
    assert p("Dodatna veštačenja i dopuna veštačenja nisu potrebna.", prihvaceno)
    assert p("Ne postoji potreba za dopunom veštačenja.", prihvaceno)
    assert p("Dopuna veštačenja je izlišna.", prihvaceno)
    assert p("Tužilac se protivi navodima tuženog i predlogu za dopunu veštačenja.", prihvaceno)


@treba_ocr
def test_oznaka_ne_postaje_citat_za_cuvara(nacrt, monkeypatch):
    """GATE-C3: čuvar citata radi nad tekstom MODELA; oznaka (tekst odluke iz dokumenta) ne menja njegov ishod."""
    k, b, pid, doks, snimljeno = nacrt
    _model_vraca(monkeypatch, snimljeno, PROTIVRECAN)
    import routers.multi_agent as MA
    vidjeno = []
    pravi = MA._proveri_citate_agenta

    def _cuvar(tekst, izvori):
        vidjeno.append(tekst)
        return pravi(tekst, izvori)
    monkeypatch.setattr(MA, "_proveri_citate_agenta", _cuvar)
    o = _pisi(k, pid)
    assert vidjeno == [PROTIVRECAN] and o["predlog_teksta"] == PROTIVRECAN


def test_gate_c3_iznos_datum_skracenica_i_navodi_uz_odluku():
    """GATE-C3 (2. prolaz): tačka u iznosu/datumu/skraćenici nije kraj rečenice — oznaka ne seče iznos; protivljenje
    navodima stranke uz navođenje odluke suda (val3 N1) nije sporno."""
    from routers.multi_agent import _oznaci_protivrecnosti as oz
    from routers.multi_agent import _protivreci_odlukama as p
    prihvaceno = [{"oznaka": "DOK-07", "tekst": "Sud prihvata predlog za dopunu vestacenja."}]
    t = "Dopuna vestacenja nije potrebna jer je steta od 3.150.000 dinara jasno utvrdjena. Ostalo."
    out = oz(t, p(t, prihvaceno))
    assert "3.150.000 dinara jasno utvrdjena. [PROVERITI PROCESNO STANJE" in out and "3. [PROVERITI" not in out
    assert p("Dopuna vestacenja, koju je sud prihvatio 15.07.2026, nije potrebna.", prihvaceno)
    assert p("Dopuna vestacenja iz zapisnika (str. 2) nije potrebna.", prihvaceno)
    assert p("Prema čl. 259 ZPP dopuna vestacenja nije potrebna.", prihvaceno)
    val3_n1 = ("- Tužilac se protivi tvrdnjama tuženog da veštak nije izvršio uvid u građevinski dnevnik, jer je sud već "
               "prihvatio predlog za dopunu veštačenja i naložio tuženom dostavljanje građevinskog dnevnika (DOK-07).")
    assert not p(val3_n1, prihvaceno)
