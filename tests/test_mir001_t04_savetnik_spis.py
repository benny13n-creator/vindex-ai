# -*- coding: utf-8 -*-
"""MIR001 TASK-04 (MIR-01/MIR-02) — pitanja preko više dokumenata nad celim Golden Case spisom, kroz STVARNU rutu
savetnika (`POST /api/agents/run`, `_kontekst_predmeta`, QA-08 evidencija izvora).

Deterministički deo (ovaj fajl): za svako od 7 pitanja meri se TAČNO šta model dobija — koji dokumenti, u celini ili
delimično, šta je izostavljeno — i šta server vraća pozivaocu (`izvori_predmeta`). Poziv modela je zamenjen snimačem.
Sa `MIR001_SNIMAK=<putanja.json>` snimljene poruke (system + user, bajt-identične onima koje bi otišle modelu) se
upisuju za ponovnu reprodukciju nad STVARNIM modelom van ovog procesa (sadržinski deo, scratchpad skripta).

Genome je zamenjen praznim sažetkom: savetnik vidi samo ono što je u dokumentima predmeta, pa se meri izbor izvora,
ne tuđ sažetak.
"""
import json
import os

import pytest

from tests import mir001_golden_case as gc
from tests.test_mir001_t02_prijem_spisa import _OCR, primi_spis
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401
from tests.nacrt_json_zamena import kao_json

treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — DOK-05 (sken) se ne može pročitati")

# (id, agent, pitanje, dokumenti u kojima je odgovor, opis)
PITANJA = [
    ("P1", "research", "Koliki je garantni rok za krovne radove po ugovoru stranaka?", ["DOK-01"], "samo u prvom"),
    ("P2", "research", "Do kada tuzeni treba da dostavi gradjevinski dnevnik i kada je sledece rociste?", ["DOK-07"], "samo u sedmom"),
    ("P3", "litigation", "Kako se tuzbeni zahtev menjao od tuzbe do poslednjeg rocista?", ["DOK-01", "DOK-07"], "prvi i sedmi"),
    ("P4", "litigation", "Kada je tuzeni primio reklamaciju? Sta tvrdi koja strana i cime je to potkrepljeno?",
     ["DOK-01", "DOK-02", "DOK-03"], "protivrecnost iz vise izvora"),
    ("P5", "research", "Sta pise u gradjevinskom dnevniku za jun 2025. godine?", [], "nema odgovora u spisu"),
    ("P6", "litigation", "Da li je tuzilac blagovremeno reklamirao nedostatak i kakva je pravna posledica ako nije?",
     ["DOK-01", "DOK-02", "DOK-03"], "pravna posledica na spornom osnovu"),
    ("P7", "research", "Uporedi DOK-02, DOK-05 i DOK-09 i navedi sta svaki kaze o uzroku prokisnjavanja.",
     ["DOK-02", "DOK-05"], "trazen dokument koji nije dostavljen (DOK-09 ne postoji)"),
]


def _genome_bez_narativa(pozivi):
    """Genome zamena iz TASK-03 (čita STVARAN prompt, protivrečnosti samo nad tvrdnjama koje su u njemu), bez
    narativnih polja — savetnik ne sme da dobije tuđ sažetak, samo trajne sporne tačke spisa."""
    from tests.test_mir001_t03_kontinuitet import _genome_model
    unutra = _genome_model(pozivi)

    async def _pozovi(client, combined, n):
        g = json.loads(await unutra(client, combined, n))
        for polje in ("pravna_teorija", "strategija", "najslabija_tacka", "heatmap"):
            g[polje] = {}
        for polje in ("snaga_faktori", "nedostaje", "dokazi_rang", "scenariji"):
            g[polje] = []
        return json.dumps(g, ensure_ascii=False)
    return _pozovi


@pytest.fixture
def savetnik(solo, monkeypatch):
    k, b = solo
    import app.services.retrieve as R
    import routers.case_dna as cd
    import routers.evidence as ev
    import routers.multi_agent as MA
    import shared.usage as US
    from tests.test_mir001_t03_kontinuitet import _klasifikuj
    monkeypatch.setattr(cd, "_pozovi_genome_api", _genome_bez_narativa(b.genome_pozivi))
    monkeypatch.setattr(ev, "_klasifikuj_dokument", _klasifikuj)
    pid, doks, _ = primi_spis(k, b)
    snimljeno = []

    def _snimi(client, system, user_msg):
        import types
        snimljeno.append({"system": MA._sa_granicom(system), "user": user_msg})
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="Simuliran odgovor."))])

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free", "krediti": 1}

    async def _stanje(uid, email):
        return 100
    monkeypatch.setattr(MA, "_pozovi_agent_api", _snimi)
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", kao_json(_snimi))     # C3b: nacrt iz spisa = JSON
    monkeypatch.setattr(US, "get_policy", _politika)
    monkeypatch.setattr(US.UsageService, "balance", staticmethod(_stanje))
    monkeypatch.setattr(R, "retrieve_documents", lambda *a, **kw: ([], {}))     # pravna baza: bez izvora (van opsega)
    return k, b, pid, doks, snimljeno


def _pitaj(k, pid, agent, pitanje, h=A):
    r = k.post("/api/agents/run", json={"agent": agent, "task": pitanje, "predmet_id": pid}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _oznake(lista):
    return sorted(x["oznaka"] for x in lista)


@treba_ocr
def test_sta_model_stvarno_dobija_za_sedam_pitanja(savetnik):
    k, b, pid, doks, snimljeno = savetnik
    rez = {}
    for pid_, agent, pitanje, _, _ in PITANJA:
        o = _pitaj(k, pid, agent, pitanje)
        rez[pid_] = (o, snimljeno[-1])
    sve = [f"DOK-0{i}" for i in range(1, 8)]
    for pid_, (o, poruka) in rez.items():
        iz = o["izvori_predmeta"]
        # ceo spis (7 kratkih dokumenata) staje u isti budžet od 12.500 znakova — svaki dokument u celini
        assert iz["dokumenata_u_predmetu"] == 7 and _oznake(iz["ukljuceni"]) == sve, (pid_, _oznake(iz["ukljuceni"]))
        assert iz["izostavljenih_ukupno"] == 0 and iz["svi_dokumenti_u_celini"] is True, pid_
        assert sum(u["znakova_dostavljeno"] for u in iz["ukljuceni"]) <= 12_500
        dokumenti = poruka["user"].rsplit("Zahtev:", 1)[0]
        for nid in ("N-02", "N-04", "N-05", "N-15"):              # stari i najnoviji navodi, oba strane, u poruci modelu
            assert gc.NAVODI[nid]["tekst"] in dokumenti, (pid_, nid)
    # P7: traženi prvi, po rednom broju; nepostojeći DOK-09 je prijavljen, ne izmišljen
    iz7 = rez["P7"][0]["izvori_predmeta"]
    assert [u["oznaka"] for u in iz7["ukljuceni"][:2]] == ["DOK-02", "DOK-05"] and all(u["trazen"] for u in iz7["ukljuceni"][:2])
    assert [(x["oznaka"], x["razlog"]) for x in iz7["trazeni_nisu_dostavljeni"]] == [("DOK-09", "NE_POSTOJI")]
    assert "DOK-09 — ne postoji u ovom predmetu" in rez["P7"][1]["user"]
    # Sporne tačke spisa: obe strane K-01 i K-02 stižu modelu označene kao SPORNO (P6: pravna posledica na spornom osnovu)
    p6 = rez["P6"][1]["user"]
    assert "SPORNE TAČKE PREDMETA" in p6 and "nijedna nije sudski utvrđena činjenica" in p6
    for x in gc.PROTIVRECNOSTI:
        assert x["pitanje"] in p6, x["id"]
        for n in x["strane"]:
            red = next(r for r in p6.splitlines() if gc.NAVODI[n]["tekst"] in r and r.lstrip().startswith("- ["))
            assert "SPORNO" in red and x["pitanje"] in red, (x["id"], n)
    # P5: odgovora nema ni u jednom dokumentu — ni u poruci modelu
    assert "jun 2025" not in rez["P5"][1]["user"].rsplit("Zahtev:", 1)[0].lower()
    put = os.environ.get("MIR001_SNIMAK")
    if put:
        with open(put, "w", encoding="utf-8") as f:
            json.dump({p[0]: {"agent": p[1], "pitanje": p[2], "odgovor_u": p[3], "opis": p[4],
                              "izvori_predmeta": rez[p[0]][0]["izvori_predmeta"], "poruka": rez[p[0]][1]} for p in PITANJA},
                      f, ensure_ascii=False, indent=1)


@treba_ocr
def test_korisnik_b_ne_dobija_spis_a_kroz_savetnika(savetnik):
    k, b, pid, doks, snimljeno = savetnik
    r = k.post("/api/agents/run", json={"agent": "research", "task": "Koliki je garantni rok?", "predmet_id": pid}, headers=B)
    assert r.status_code in (403, 404) or (r.status_code == 200 and not r.json().get("izvori_predmeta")), r.text
    assert not any(gc.TUZENI in s["user"] or "08.09.2025" in s["user"] for s in snimljeno)


@treba_ocr
def test_greska_citanja_spornih_tacaka_je_izricita(savetnik, monkeypatch):
    k, b, pid, doks, snimljeno = savetnik
    import services.v2_projection as VP

    async def _pada(*a, **kw):
        raise RuntimeError("statement timeout")
    monkeypatch.setattr(VP, "ucitaj_v2_kontradikcije_za_prikaz", _pada)
    _pitaj(k, pid, "litigation", PITANJA[5][2])
    p = snimljeno[-1]["user"]
    assert "SPORNE TAČKE PREDMETA: NEPOZNATO" in p and "SPORNO —" not in p
