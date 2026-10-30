# -*- coding: utf-8 -*-
"""Operation Bojan BA-01 — identitet kandidata roka između Smart Intake-a i Genome-a (Task 5, BA-05/BA-06/BA-08).

Ugovor: BA01-SPRINT-EVIDENCE/DEADLINE_IDENTITY_CONTRACT.md. Klasa = (izvorni dokument, datum); broj kandidata klase
ograničava dokaz iz teksta dokumenta; tekst modela (`naziv`, `opis`) nikad nije identitet; postojeći red se ne menja.

Stvarne rute, stvaran prijem i stvaran sync; baza u memoriji (`lanac`). Genome model je zamenjen SKRIPTOVANIM izlazom
(isti dokument, isti rokovi, različite formulacije) — to je upravo ono što stvaran model radi između osvežavanja.
"""
import asyncio
import copy
import json
from datetime import timedelta

import pytest

import routers.case_dna as cd
from routers.email_notif import _danas_beograd
import tests.test_osb002_solo_tok as osb
from tests.test_n1_zlatni_prijem import _do_kraja, _pdf
from tests.test_n7_azuriranje_predmeta import lanac  # noqa: F401 — fixture
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401 — fixture
from tests.test_osb002_solo_tok import _do_kraja_dogadjaja

# Datumi su relativni prema `_danas_beograd()` (sintetički): `/api/rokovi/kandidati` gleda [danas, danas+30], pa bi
# fiksan datum posle nekoliko dana ispao iz prozora (lekcija CI pada MIR001 T07).
_D = _danas_beograd()
DA, DB, DC, DX, DY = ((_D + timedelta(days=n)).isoformat() for n in (6, 21, 28, 25, 26))
SA, SB, SC = ((_D + timedelta(days=n)).strftime("%d.%m.%Y.") for n in (6, 21, 28))
SO, SP = ((_D - timedelta(days=n)).strftime("%d.%m.%Y.") for n in (8, 9))
ZAGLAVLJE = ["OSNOVNI SUD U BEOGRADU", "Posl. br. P 7714/2026 (SINTETICKI)", "Tuzilac: Petar Goldenovic iz Beograda",
             "Tuzeni: Golden Gradnja DOO Beograd", "PRESUDA", f"Presuda je doneta {SP} godine."]
D01 = ZAGLAVLJE + ["Obavezuje se tuzeni da tuziocu isplati 350.000,00 dinara.",
                   f"Rok za izjavljivanje zalbe istice {SA} godine.",
                   f"Rok za dobrovoljno ispunjenje istice {SB} godine.", f"U Beogradu, dana {SO}"]
ISTI_DAN = ZAGLAVLJE + [f"Rok za izjavljivanje zalbe istice {SA} godine.",
                        f"Rok za uplatu sudske takse istice {SA} godine."]
TAKSA = ["OBAVESTENJE O TAKSI", "Posl. br. P 7714/2026", f"Rok za uplatu sudske takse istice {SA} godine."]
D05 = ["OBAVESTENJE", "Posl. br. P 7714/2026", f"Rok za odgovor na zalbu istice {SC} godine."]


def _rok(naziv, datum, opis, lok="DOK-01"):
    return {"naziv": naziv, "datum": datum, "opis": opis, "status": "aktivan", "lokacija": lok}


ZALBA = [_rok("Rok za izjavljivanje zalbe", DA, "Propustanje onemogucava zalbu"),
         _rok("Rok za dobrovoljno ispunjenje", DB, "Moguce prinudno izvrsenje")]
ZALBA_PREFORMULISANO = [_rok("Rok za izjavljivanje žalbe", DA, "Propuštanje roka onemogućava žalbu"),
                        _rok("Dobrovoljno ispunjenje", DB, "Nakon isteka moguće je prinudno izvršenje")]
ZALBA_TRECE = [_rok("Žalbeni rok", DA, "Pravosnažnost"), _rok("Ispunjenje", DB, "Izvršenje")]


class Model:
    """Skriptovan Genome: vraća `self.izlaz` (menja ga test između osvežavanja)."""
    def __init__(self, izlaz):
        self.izlaz, self.pozivi = izlaz, 0

    async def __call__(self, client, combined, n):
        self.pozivi += 1
        g = copy.deepcopy(osb.rp._genome(0, False, 0, 0))
        for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(polje, None)
        g["rokovi_kriticni"] = copy.deepcopy(self.izlaz)
        return json.dumps(g, ensure_ascii=False)


def _predmet(k, h=A, ime="Petar"):
    kid = k.post("/klijenti", json={"tip": "fizicko_lice", "ime": ime, "prezime": "Goldenovic"}, headers=h).json()["klijent"]["id"]
    return k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "BA01", "opis": "Sinteticki"}, headers=h).json()["predmet_id"]


def _prikaci(k, b, pid, redovi, ime, h=A):
    r = k.post("/api/smart-intake/documents", files=[("files", (ime, _pdf(redovi), "application/pdf"))], headers=h)
    jid = r.json()["rezultati"][0]["job_id"]
    _do_kraja()
    if k.get(f"/api/smart-intake/jobs/{jid}", headers=h).json()["job"]["status"] == "awaiting_review":
        k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=h)
        _do_kraja()
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid, "klijent_strana": "plaintiff"}, headers=h)
    assert f.status_code == 200, f.text
    _do_kraja_dogadjaja(b)
    return jid


def _rokovi(b, pid):
    return [h for h in b.tabele["predmet_hronologija"] if h["predmet_id"] == pid and h.get("datum_iso")]


def _po_datumu(b, pid):
    out = {}
    for h in _rokovi(b, pid):
        out[h["datum_iso"]] = out.get(h["datum_iso"], 0) + 1
    return out


def _osvezi(pid, uid="uid-A"):
    asyncio.run(cd._run_genome_background(pid, uid, trigger="ba01"))


def _stanja(k, pid, h=A):
    return {r["id"]: r["stanje_odluke"] for r in k.get(f"/api/rokovi/kandidati?predmet_id={pid}", headers=h).json()["rokovi"]}


# ── 1, 5, 6: ista obaveza — preformulisano, SI + Genome, posle potvrde ──────────────────────────────────────────────

def test_ista_obaveza_jedan_kandidat_kroz_preformulacije_i_potvrdu(lanac, monkeypatch):
    k, b = lanac
    model = Model(ZALBA)
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci(k, b, pid, D01, "01 Presuda digitalna.pdf")
    assert _po_datumu(b, pid) == {DA: 1, DB: 1}, _rokovi(b, pid)        # 5: SI + Genome = jedan
    si = next(h for h in _rokovi(b, pid) if h["akter"] == "Smart Intake")
    assert si["datum_iso"] == DA
    for izlaz in (ZALBA, ZALBA_PREFORMULISANO, ZALBA_TRECE):                                   # 1: identično i preformulisano
        model.izlaz = izlaz
        _osvezi(pid)
        assert _po_datumu(b, pid) == {DA: 1, DB: 1}, [h["dogadjaj"] for h in _rokovi(b, pid)]
    assert model.pozivi >= 4
    ids_pre = sorted(h["id"] for h in _rokovi(b, pid))
    assert k.post(f"/api/rokovi/{si['id']}/potvrdi", json={}, headers=A).status_code == 200
    g = next(h for h in _rokovi(b, pid) if h["datum_iso"] == DB)
    assert k.post(f"/api/rokovi/{g['id']}/odbij", json={"napomena": "nije rok"}, headers=A).status_code == 200
    model.izlaz = ZALBA_PREFORMULISANO
    _osvezi(pid)                                                                                 # 6: posle odluka
    assert sorted(h["id"] for h in _rokovi(b, pid)) == ids_pre
    st = _stanja(k, pid)
    assert st[si["id"]] == "CONFIRMED" and st[g["id"]] == "REJECTED", st                        # odluke na istim id
    # ponovna obrada istog dokumenta (nov posao, isti tekst) ne vraća odbijen ni potvrđen rok kao nov kandidat
    _prikaci(k, b, pid, D01, "01 Presuda digitalna.pdf")
    assert _po_datumu(b, pid) == {DA: 1, DB: 1}


# ── 2: isti dokument, dve obaveze, ISTI datum ──────────────────────────────────────────────────────────────────

def test_dve_obaveze_istog_datuma_ostaju_dve(lanac, monkeypatch):
    k, b = lanac
    model = Model([_rok("Rok za zalbu", DA, "a"), _rok("Rok za taksu", DA, "b")])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci(k, b, pid, ISTI_DAN, "02 Resenje dve obaveze.pdf")
    assert _po_datumu(b, pid) == {DA: 2}, _rokovi(b, pid)
    model.izlaz = [_rok("Žalba", DA, "x"), _rok("Taksa", DA, "y")]
    _osvezi(pid)
    assert _po_datumu(b, pid) == {DA: 2}
    # model tvrdi TRI obaveze tog dana — tekst dokazuje dve; ograničenje dokazom
    model.izlaz = [_rok("A", DA, "1"), _rok("B", DA, "2"), _rok("C", DA, "3")]
    _osvezi(pid)
    assert _po_datumu(b, pid) == {DA: 2}


# ── 3 i 4: različiti datumi; dva dokumenta sa istim datumom se ne spajaju ──────────────────────────────────────

def test_dva_dokumenta_isti_datum_nisu_ista_obaveza(lanac, monkeypatch):
    k, b = lanac
    model = Model([_rok("Rok za zalbu", DA, "a", "DOK-01")])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci(k, b, pid, ISTI_DAN[:-1], "01 Presuda.pdf")
    model.izlaz = [_rok("Rok za zalbu", DA, "a", "DOK-01"), _rok("Rok za taksu", DA, "b", "DOK-02")]
    _prikaci(k, b, pid, TAKSA, "02 Taksa.pdf")
    r = _rokovi(b, pid)
    assert sorted(h["dokument_naziv"] for h in r) == ["01 Presuda.pdf", "02 Taksa.pdf"], r
    _osvezi(pid)
    assert len(_rokovi(b, pid)) == 2


# ── 7: nerazrešen izvor — jednakost se NE pretpostavlja (samo tačan tekst); nikad spojen sa ručnim redom ──────────

def test_nerazresen_izvor_odvojena_klasa(lanac, monkeypatch):
    k, b = lanac
    model = Model([_rok("Rok bez izvora", DX, "x", lok="")])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    b.tabele["predmet_hronologija"].append({"id": "rucni-1", "predmet_id": pid, "user_id": "uid-A", "dogadjaj": "Ručni rok",
                                            "datum_iso": DX, "datum": DX, "akter": "advokat",
                                            "izvor": "HUMAN_DIRECT", "vrsta": "rok"})
    _prikaci(k, b, pid, D05, "05 Obavestenje.pdf")
    nerazreseni = [h for h in _rokovi(b, pid) if h["datum_iso"] == DX and h["akter"] == "Genome (AI)"]
    assert len(nerazreseni) == 1 and not nerazreseni[0].get("dokument_id") and not nerazreseni[0].get("dokument_naziv")
    _osvezi(pid)                                                                                  # isti tekst → isti red
    assert len([h for h in _rokovi(b, pid) if h["datum_iso"] == DX]) == 2              # ručni + jedan Genome
    model.izlaz = [_rok("Drugačije rečeno", DX, "y", lok="")]
    _osvezi(pid)                                                                                  # bez izvora: ne spaja se
    assert len([h for h in _rokovi(b, pid) if h["datum_iso"] == DX]) == 3


# ── 8: izvor uklonjen posle potvrde — istorija i odluka ostaju ─────────────────────────────────────────────────

def test_uklonjen_izvor_cuva_odluku(lanac, monkeypatch):
    k, b = lanac
    # rok koji tekst ne dokazuje (npr. izračunat od dostave) predlaže samo Genome — on nosi `dokument_id`
    model = Model(ZALBA + [_rok("Rok za izvrsenje", DY, "racunato od dostave")])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci(k, b, pid, D01, "01 Presuda digitalna.pdf")
    g = next(h for h in _rokovi(b, pid) if h["akter"] == "Genome (AI)")
    assert g["datum_iso"] == DY and g.get("dokument_id")
    assert k.post(f"/api/rokovi/{g['id']}/potvrdi", json={}, headers=A).status_code == 200
    dok = next(d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid)
    b.tabele["predmet_dokumenti"].remove(dok)
    for h in _rokovi(b, pid):                      # FK ON DELETE SET NULL (migracija 126)
        if h.get("dokument_id") == dok["id"]:
            h["dokument_id"] = None
    model.izlaz = []
    _osvezi(pid)
    st = k.get(f"/api/rokovi/kandidati?predmet_id={pid}", headers=A).json()["rokovi"]
    red = next(r for r in st if r["id"] == g["id"])
    assert red["stanje_odluke"] == "CONFIRMED" and red["izvor_povucen"] is True, red


# ── ponovljen dispatch, retry, pad čitanja, istovremenost, dva korisnika ───────────────────────────────────────

def test_ponovljen_dispatch_i_retry_finalize_bez_duplikata(lanac, monkeypatch):
    k, b = lanac
    model = Model(ZALBA_PREFORMULISANO)
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    jid = _prikaci(k, b, pid, D01, "01 Presuda digitalna.pdf")
    pre = sorted(h["id"] for h in _rokovi(b, pid))
    pozivi_pre = model.pozivi
    model.izlaz = ZALBA_TRECE
    # ponovna isporuka DocumentAccepted (outbox replay) i ponovno izvršenje posledice genome_refresh
    for e in b.tabele["events"]:
        if e["event_type"] == "DocumentAccepted":
            e["dispatched_at"] = None
            e["claimed_at"] = None
    b.tabele["case_evolution_consequences"] = [c for c in b.tabele["case_evolution_consequences"]
                                               if c["consequence_name"] != "genome_refresh"]
    _do_kraja_dogadjaja(b)
    assert model.pozivi > pozivi_pre, "replay nije ponovo pokrenuo Genome"
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    assert f.status_code == 200
    _do_kraja_dogadjaja(b)
    assert sorted(h["id"] for h in _rokovi(b, pid)) == pre


def test_pad_citanja(lanac, monkeypatch):
    """Pad čitanja hronologije → nijedan upis (klasa se ne može proveriti). Pad čitanja dokumenata → B8: rok ulazi i
    bez naziva, ali bez poklapanja po imenu fajla — moguć dupli kandidat, nikad spajanje ni izmišljen naziv."""
    k, b = lanac
    pid = _predmet(k)
    pravo = b.table
    pada = {"ime": "predmet_hronologija"}

    def _tabela(ime):
        if ime == pada["ime"]:
            raise RuntimeError("istek upita")
        return pravo(ime)
    monkeypatch.setattr(b, "table", _tabela)
    g = {"rokovi_kriticni": [dict(r, dokument_id="dok-x") for r in ZALBA]}
    assert asyncio.run(cd._sync_rokovi_to_hronologija(b, pid, "uid-A", copy.deepcopy(g))) == 0
    assert _rokovi(b, pid) == []
    pada["ime"] = "predmet_dokumenti"
    b.tabele["predmet_hronologija"].append({"id": "si-1", "predmet_id": pid, "user_id": "uid-A", "datum_iso": DA,
                                            "dogadjaj": "Rok iz dokumenta (presuda)", "akter": "Smart Intake",
                                            "dokument_naziv": "01 Presuda digitalna.pdf", "vrsta": "rok"})
    assert asyncio.run(cd._sync_rokovi_to_hronologija(b, pid, "uid-A", copy.deepcopy(g))) == 2
    assert all(h.get("dokument_naziv") is None for h in _rokovi(b, pid) if h["akter"] == "Genome (AI)")


def test_istovremeni_sync_ne_duplira(lanac, monkeypatch):
    k, b = lanac
    pid = _predmet(k)
    g = {"rokovi_kriticni": [_rok("Bez izvora", DX, "x", lok="")]}

    async def _dva():
        return await asyncio.gather(cd._sync_rokovi_to_hronologija(b, pid, "uid-A", copy.deepcopy(g)),
                                    cd._sync_rokovi_to_hronologija(b, pid, "uid-A", copy.deepcopy(g)))
    assert sorted(asyncio.run(_dva())) == [0, 1]
    assert len(_rokovi(b, pid)) == 1


def test_drugi_korisnik_ne_utice_i_ne_vidi(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model(ZALBA))
    pa = _predmet(k)
    _prikaci(k, b, pa, D01, "01 Presuda digitalna.pdf")
    pb = _predmet(k, h=B, ime="Bojana")
    _prikaci(k, b, pb, D01, "01 Presuda digitalna.pdf", h=B)
    assert _po_datumu(b, pa) == _po_datumu(b, pb) == {DA: 1, DB: 1}
    assert {h["user_id"] for h in _rokovi(b, pb)} == {"uid-B"}
    assert k.get(f"/api/rokovi/kandidati?predmet_id={pa}", headers=B).json()["rokovi"] == []
    rid = _rokovi(b, pa)[0]["id"]
    assert k.post(f"/api/rokovi/{rid}/potvrdi", json={}, headers=B).status_code == 404


def test_dva_razlicita_dokumenta_istog_imena_obaveza_se_ne_gubi(lanac, monkeypatch):
    """Ime fajla nije dokaz: red Smart Intake-a za „scan.pdf“ ne sme da „pokrije“ obavezu DRUGOG dokumenta istog
    imena. BA05: identitet je sadržaj dokumenta, pa svaka obaveza ima tačno jedan kandidat — ni gubitak ni duplikat."""
    k, b = lanac
    model = Model([_rok("Rok za zalbu", DA, "a", "DOK-01")])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci(k, b, pid, ISTI_DAN[:-1], "scan.pdf")
    model.izlaz = [_rok("Rok za zalbu", DA, "a", "DOK-01"), _rok("Rok za taksu", DA, "b", "DOK-02")]
    _prikaci(k, b, pid, TAKSA, "scan.pdf")
    r = _rokovi(b, pid)
    assert len(r) == 2 and len({h["obaveza_kljuc"] for h in r}) == 2, r
    _osvezi(pid)
    assert len(_rokovi(b, pid)) == 2
