# -*- coding: utf-8 -*-
"""BA05 produkcioni defekt (P7714/2026): rok dokazan u tekstu drugog `scan.pdf` nije postao kandidat.

Smart Intake OCR rok namerno ne upisuje (pouzdanost 0,89 < prag), a Genome sync obilazi samo (dokument, datum) koje
model navede — model ga je izostavio, pa je obaveza tiho nestala. Usklađivanje iz izvora (`rokovi_iz_izvora`,
posledica DOCUMENT_ACCEPTED pre Genome-a) upisuje svaku obavezu koju parser prepozna u tekstu prihvaćenog dokumenta
kao NEPOTVRĐEN kandidat, nezavisno od modela. Prepoznavanje u tekstu nije pravna provera: kandidat nikad nije
izvršiv bez potvrde advokata, a OCR čitanje je označeno u nazivu.

Stvarne rute, stvaran OCR, stvaran Genome sync; baza u memoriji sa jedinstvenošću iz 144. Isto nad pravim
PostgreSQL-om: tests/test_ba05_migracija_144_postgres.py.
"""
import asyncio

import pytest

import routers.case_dna as cd
from tests import ns005_harness as _h  # noqa: F401
from tests.ns006_fake import dispecuj
from tests.test_ba01_rok_identitet import (A, DA, SA, Model, _osvezi, _predmet, _prikaci, _rok, _rokovi, _stanja,
                                           lanac, solo)  # noqa: F401 — fixture
from tests.test_ba01_vise_rokova import _prikaci_sken, _sken_pdf, treba_ocr
from tests.test_n1_zlatni_prijem import _do_kraja

TROSKOVI = ["RESENJE", "Posl. br. P 7714/2026 (SINTETICKI)", f"Rok za zalbu na troskove istice {SA} godine."]
TAKSA = ["RESENJE", "Posl. br. P 7714/2026 (SINTETICKI)", f"Rok za uplatu dodatne sudske takse istice {SA} godine."]


def _dokumenti(b, pid):
    return sorted((d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid), key=lambda d: d["redni_broj"])


def _po_dokumentu(b, pid):
    return {h["dokument_id"]: h for h in _rokovi(b, pid)}


def _prikaci_sken_bez_dogadjaja(k, pid, redovi, ime):
    """Kao `_prikaci_sken`, ali događaje NE prazni (test sam meri ishod posledica, i kada Genome pada)."""
    r = k.post("/api/smart-intake/documents", files=[("files", (ime, _sken_pdf(redovi), "application/pdf"))], headers=A)
    jid = r.json()["rezultati"][0]["job_id"]
    _do_kraja()
    assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A).status_code == 200
    _do_kraja()
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).status_code == 200
    return jid


def _proveri_dva_kandidata(k, b, pid, ocr=True):
    dok = _dokumenti(b, pid)
    assert [d["naziv_fajla"] for d in dok] == ["scan.pdf", "scan.pdf"] and dok[0]["content_sha256"] != dok[1]["content_sha256"]
    r = _po_dokumentu(b, pid)
    assert set(r) == {dok[0]["id"], dok[1]["id"]}, [(h["dogadjaj"], h["dokument_id"]) for h in _rokovi(b, pid)]
    assert [h["datum_iso"] for h in r.values()] == [DA, DA]
    assert len({h["obaveza_kljuc"] for h in r.values()}) == 2 and None not in {h["obaveza_kljuc"] for h in r.values()}
    if ocr:
        assert "troskove" in r[dok[0]["id"]]["dogadjaj"] and "takse" in r[dok[1]["id"]]["dogadjaj"]
        assert all("OCR" in h["dogadjaj"] for h in r.values()), [h["dogadjaj"] for h in r.values()]
    assert sorted(_stanja(k, pid).values()) == ["UNCONFIRMED", "UNCONFIRMED"]
    return dok, r


# ── T1: Genome navodi samo A → B ostaje kandidat ───────────────────────────────────────────────────────────────

@treba_ocr
def test_genome_navodi_samo_A_obaveza_B_ostaje_kandidat(lanac, monkeypatch):
    k, b = lanac
    model = Model([_rok("Rok za žalbu na troškove", DA, "x", "DOK-01")])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci_sken(k, b, pid, TROSKOVI, "scan.pdf")
    _prikaci_sken(k, b, pid, TAKSA, "scan.pdf")
    _proveri_dva_kandidata(k, b, pid)
    _osvezi(pid)
    assert len(_rokovi(b, pid)) == 2


# ── T2: Genome ne navodi nijedan rok → oba ostaju ──────────────────────────────────────────────────────────────

@treba_ocr
def test_genome_bez_rokova_obe_obaveze_ostaju(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    _prikaci_sken(k, b, pid, TROSKOVI, "scan.pdf")
    _prikaci_sken(k, b, pid, TAKSA, "scan.pdf")
    _proveri_dva_kandidata(k, b, pid)


# ── T3: Genome pada → kandidati iz izvora su ipak trajni, a pad je vidljiv (događaj nije „obrađen“) ─────────────

@treba_ocr
def test_genome_pada_kandidati_iz_izvora_ostaju_a_pad_je_vidljiv(lanac, monkeypatch):
    k, b = lanac

    async def _pad(*a, **kw):
        raise RuntimeError("model nedostupan (test)")
    monkeypatch.setattr(cd, "_pozovi_genome_api", _pad)
    pid = _predmet(k)
    _prikaci_sken_bez_dogadjaja(k, pid, TROSKOVI, "scan.pdf")
    _prikaci_sken_bez_dogadjaja(k, pid, TAKSA, "scan.pdf")
    for _ in range(3):
        dispecuj()
    _proveri_dva_kandidata(k, b, pid)
    prihvatanja = {e["id"] for e in b.tabele["events"] if e["event_type"] == "DocumentAccepted"}
    pos = {(p["event_id"], p["consequence_name"]): p["status"] for p in b.tabele["case_evolution_consequences"]
           if p["event_id"] in prihvatanja}
    assert len(prihvatanja) == 2
    assert {s for (_, n), s in pos.items() if n == "rokovi_iz_izvora"} == {"completed"}
    assert {s for (_, n), s in pos.items() if n == "genome_refresh"} == {"failed"}
    assert not any(e.get("dispatched_at") for e in b.tabele["events"] if e["id"] in prihvatanja)    # ponavlja se


# ── T4: ponovni upload istog sadržaja, ponovljena obrada, tri osvežavanja → isti redovi, odluke netaknute ──────

@treba_ocr
def test_ponovni_upload_i_osvezavanja_ne_menjaju_kandidate_ni_odluke(lanac, monkeypatch):
    k, b = lanac
    model = Model([])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci_sken(k, b, pid, TROSKOVI, "scan.pdf")
    _prikaci_sken(k, b, pid, TAKSA, "scan.pdf")
    dok, r = _proveri_dva_kandidata(k, b, pid)
    a, t = r[dok[0]["id"]], r[dok[1]["id"]]
    assert k.post(f"/api/rokovi/{a['id']}/potvrdi", json={}, headers=A).status_code == 200
    assert k.post(f"/api/rokovi/{t['id']}/odbij", json={"napomena": "test"}, headers=A).status_code == 200
    for izlaz in ([_rok("Rok za žalbu na troškove", DA, "x", "DOK-01")],
                  [_rok("Dodatna taksa", DA, "y", "DOK-02")], []):
        model.izlaz = izlaz
        _osvezi(pid)
    _prikaci_sken(k, b, pid, TAKSA, "scan.pdf")                                   # isti sadržaj, nov posao
    for e in b.tabele["events"]:                                                   # ponovljena obrada događaja
        e["dispatched_at"] = None
    for p in b.tabele["case_evolution_consequences"]:
        if p["consequence_name"] == "rokovi_iz_izvora":
            p["status"] = "failed"
    dispecuj()
    assert sorted(h["id"] for h in _rokovi(b, pid)) == sorted([a["id"], t["id"]])
    assert _stanja(k, pid) == {a["id"]: "CONFIRMED", t["id"]: "REJECTED"}


# ── kontrola: digitalni PDF — Smart Intake upisuje, usklađivanje vidi isti ključ (nijedan duplikat) ─────────────

def test_digitalni_pdf_smart_intake_i_uskladjivanje_isti_kljuc(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([_rok("Rok za žalbu na troškove", DA, "x", "DOK-01")]))
    pid = _predmet(k)
    _prikaci(k, b, pid, TROSKOVI, "scan.pdf")
    _prikaci(k, b, pid, TAKSA, "scan.pdf")
    dok, r = _proveri_dva_kandidata(k, b, pid, ocr=False)
    assert {h["akter"] for h in r.values()} == {"Smart Intake"}


# ══ Faza 4 — suprotstavljeni slučajevi (direktno nad `uskladi_rokove_iz_izvora`, baza u memoriji) ════════════════
# Prepoznavanje u tekstu NIJE pravna provera: kada parser navod prepozna kao rok (i negiran, uslovan, istekao ili
# ukinut), on postaje samo NEPOTVRĐEN kandidat čiji naziv nosi ceo izvorni red — advokat vidi negaciju/uslov i odlučuje.
# Nikad izvršiv bez potvrde. Kada ga parser ne prepozna (običan datum, relativni rok bez datuma), kandidata nema.

import uuid as _uuid  # noqa: E402

from shared import rokovi as R  # noqa: E402
from shared.rok_potvrda import potvrdjeni_ids  # noqa: E402
from shared.vector_identity import verzija_dokumenta  # noqa: E402


def _dok(b, pid, tekst, ime="scan.pdf", uid="uid-A", posao=None):
    did = str(_uuid.uuid4())
    b.table("predmet_dokumenti").insert({"id": did, "predmet_id": pid, "user_id": uid, "naziv_fajla": ime,
                                         "tekst_sadrzaj": tekst, "content_sha256": verzija_dokumenta(tekst) if tekst else None,
                                         "source_intake_job_id": posao}).execute()
    return did


def _uskladi(supa, pid, ids=(), poslovi=(), uid="uid-A"):
    return asyncio.run(R.uskladi_rokove_iz_izvora(supa, pid, uid, dokument_ids=ids, intake_job_ids=poslovi))


PREPOZNATO = {
    "negiran": ("Rok za uplatu sudske takse ne istice {d} godine jer je tuzilac oslobodjen placanja.", "ne istice"),
    "uslovni": ("Ukoliko tuzilac ne dostavi dokaz, rok za uplatu takse istice {d} godine.", "Ukoliko"),
    "istorijski": ("Rok za zalbu je istekao {d} godine.", "istekao"),
    "ukinut": ("Ranije odredjeni rok za uplatu takse {d} godine se ukida.", "se ukida"),
}
NIJE_PREPOZNATO = {
    "obican_datum_uz_pravni_termin": "Presuda je doneta {d} godine po isteku roka za odgovor na tuzbu.",
    "obican_datum": "Rociste je odrzano {d} godine.",
    "relativni_bez_datuma": "Zalba se moze izjaviti u roku od 15 dana od dana dostavljanja.",
    "negiran_bez_rokovne_reci": "Tuzilac nije duzan da plati taksu do {d} godine.",
}


@pytest.mark.parametrize("slucaj", list(PREPOZNATO))
def test_prepoznat_navod_je_samo_nepotvrden_kandidat_sa_celim_redom(slucaj, lanac):
    k, b = lanac
    pid = _predmet(k)
    red, znak = PREPOZNATO[slucaj]
    did = _dok(b, pid, "RESENJE\n" + red.format(d=SA))
    ishod = _uskladi(b, pid, [did])
    [h] = _rokovi(b, pid)
    assert len(ishod["kreirano"]) == 1 and znak in h["dogadjaj"] and h["dokument_id"] == did, (ishod, h["dogadjaj"])
    assert _stanja(k, pid) == {h["id"]: "UNCONFIRMED"} and potvrdjeni_ids([h["id"]]) == set()


@pytest.mark.parametrize("slucaj", list(NIJE_PREPOZNATO))
def test_neprepoznat_navod_nije_kandidat_i_ishod_to_kaze(slucaj, lanac):
    k, b = lanac
    pid = _predmet(k)
    did = _dok(b, pid, "PRESUDA\n" + NIJE_PREPOZNATO[slucaj].format(d=SA))
    ishod = _uskladi(b, pid, [did])
    assert _rokovi(b, pid) == [] and ishod["bez_signala"] == [did] and ishod["kreirano"] == []


def test_necitljiv_dokument_bez_teksta_nije_kandidat_ni_greska(lanac):
    k, b = lanac
    pid = _predmet(k)
    did = _dok(b, pid, "")
    ishod = _uskladi(b, pid, [did])
    assert _rokovi(b, pid) == [] and ishod["bez_teksta"] == [did]


def test_dogadjaj_bez_identiteta_dokumenta_ne_razresava_po_imenu(lanac):
    k, b = lanac
    pid = _predmet(k)
    _dok(b, pid, "\n".join(TAKSA))
    ishod = _uskladi(b, pid)
    assert ishod.get("bez_identiteta_dokumenta") is True and _rokovi(b, pid) == []


def test_tudji_dokument_se_ne_cita_ni_upisuje(lanac):
    k, b = lanac
    pid = _predmet(k)
    tudji = _dok(b, pid, "\n".join(TAKSA), uid="uid-B")
    ishod = _uskladi(b, pid, [tudji])
    assert _rokovi(b, pid) == [] and ishod["kreirano"] == [] and ishod["bez_signala"] == []
    assert ishod["nije_pronadjeno"] == [tudji]                                    # vidljivo, ne „uspeh bez ičega“


def test_datum_koji_je_advokat_ispravio_se_ne_vraca_kao_kandidat(lanac):
    k, b = lanac
    pid = _predmet(k)
    posao, prijem = str(_uuid.uuid4()), str(_uuid.uuid4())
    did = _dok(b, pid, "\n".join(TAKSA), posao=posao)
    b.table("intake_documents").insert({"id": prijem, "intake_job_id": posao, "ocr_used": True}).execute()
    b.table("extracted_entities").insert({"id": str(_uuid.uuid4()), "document_id": prijem, "entity_type": "deadline",
                                          "value": SA, "corrected_value": "20.12.2026", "reviewed": True}).execute()
    ishod = _uskladi(b, pid, poslovi=[posao])
    assert _rokovi(b, pid) == [] and ishod["ispravljeno"] == [(did, DA)]


class _Kvar:
    """Delegira bazu; zadata operacija nad `predmet_hronologija` pada (čitanje ili n-ti upis)."""
    def __init__(self, b, citanje=False, upis_br=None):
        self.b, self.citanje, self.upis_br, self.upisa = b, citanje, upis_br, 0

    def table(self, t):
        q = self.b.table(t)
        if t != "predmet_hronologija":
            return q
        if self.citanje:
            def _sel(*a, **kw):
                raise RuntimeError("čitanje hronologije palo (test)")
            q.select = _sel
        orig = q.insert

        def _ins(red, *a, **kw):
            self.upisa += 1
            if self.upisa == self.upis_br:
                raise RuntimeError("upis pao (test)")
            return orig(red, *a, **kw)
        q.insert = _ins
        return q

    def __getattr__(self, ime):
        return getattr(self.b, ime)


def test_pad_citanja_nije_uspeh_sa_nula_kandidata(lanac):
    k, b = lanac
    pid = _predmet(k)
    did = _dok(b, pid, "\n".join(TAKSA))
    with pytest.raises(RuntimeError, match="čitanje hronologije"):
        _uskladi(_Kvar(b, citanje=True), pid, [did])
    assert _rokovi(b, pid) == []
    assert len(_uskladi(b, pid, [did])["kreirano"]) == 1                          # ponovni pokušaj dovršava


def test_delimican_upis_se_podize_a_ponovni_pokusaj_dovrsava_bez_duplikata(lanac):
    k, b = lanac
    pid = _predmet(k)
    did = _dok(b, pid, f"RESENJE\nRok za zalbu istice {SA} godine.\nRok za uplatu sudske takse istice {SA} godine.")
    with pytest.raises(RuntimeError, match="upis pao"):
        _uskladi(_Kvar(b, upis_br=2), pid, [did])
    assert len(_rokovi(b, pid)) == 1                                             # prvi upisan, drugi nije — vidljivo
    ishod = _uskladi(b, pid, [did])
    assert len(ishod["kreirano"]) == 1 and len(ishod["postoji"]) == 1 and len(_rokovi(b, pid)) == 2
    assert len(_uskladi(b, pid, [did])["postoji"]) == 2 and len(_rokovi(b, pid)) == 2


@treba_ocr
def test_posledica_ostaje_nezavrsena_kad_uskladjivanje_padne(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)

    pravi = R.uskladi_rokove_iz_izvora

    async def _pad(*a, **kw):
        raise RuntimeError("baza nedostupna (test)")
    monkeypatch.setattr(R, "uskladi_rokove_iz_izvora", _pad)
    _prikaci_sken_bez_dogadjaja(k, pid, TAKSA, "scan.pdf")
    dispecuj()
    prihvatanje = next(e for e in b.tabele["events"] if e["event_type"] == "DocumentAccepted")
    st = {p["consequence_name"]: p["status"] for p in b.tabele["case_evolution_consequences"]
          if p["event_id"] == prihvatanje["id"]}
    assert st == {"rokovi_iz_izvora": "failed"} and not prihvatanje.get("dispatched_at"), st
    monkeypatch.setattr(R, "uskladi_rokove_iz_izvora", pravi)                  # baza se vratila → ponovni pokušaj
    dispecuj()
    [h] = _rokovi(b, pid)
    assert "takse" in h["dogadjaj"] and _stanja(k, pid) == {h["id"]: "UNCONFIRMED"}


# ── odbijen nikad izvršiv, nepotvrđen nikad ne šalje; drugi korisnik ništa (lokalni SMTP, nijedna poruka napolje) ──

@treba_ocr
def test_kandidati_iz_skena_do_podsetnika_samo_potvrdjen(lanac, monkeypatch, tmp_path):
    from datetime import timedelta
    from routers.email_notif import _danas_beograd
    from tests.test_ba01_obaveze_podsetnici import _posalji, _profil
    from tests.test_n7_azuriranje_predmeta import _sr
    from tests.test_s2_smtp_transport_lokalno import LokalniSmtp, _sertifikat
    smtp = LokalniSmtp(*_sertifikat(tmp_path))
    try:
        k, b = lanac
        monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
        _profil(b, "uid-A", "advokat-a@example.invalid")
        _profil(b, "uid-B", "advokat-b@example.invalid")
        d1, d3 = _danas_beograd() + timedelta(days=1), _danas_beograd() + timedelta(days=3)
        pid = _predmet(k)
        _prikaci_sken(k, b, pid, ["RESENJE", f"Rok za zalbu na troskove istice {_sr(d1)} godine."], "scan.pdf")
        _prikaci_sken(k, b, pid, ["RESENJE", f"Rok za uplatu dodatne sudske takse istice {_sr(d3)} godine."], "scan.pdf")
        r = {h["datum_iso"]: h for h in _rokovi(b, pid)}
        assert sorted(r) == [d1.isoformat(), d3.isoformat()], r
        assert _posalji(b, smtp)["poslato"] == 0 and smtp.primljeno == []              # nepotvrđeno nikad
        ra, rb = r[d1.isoformat()], r[d3.isoformat()]
        assert k.post(f"/api/rokovi/{rb['id']}/odbij", json={"napomena": "test"}, headers=A).status_code == 200
        assert _posalji(b, smtp)["poslato"] == 0 and potvrdjeni_ids([ra["id"], rb["id"]]) == set()
        assert k.post(f"/api/rokovi/{ra['id']}/potvrdi", json={}, headers=A).status_code == 200
        rez = _posalji(b, smtp)
        assert rez["poslato"] == 1 and len(smtp.primljeno) == 1 and potvrdjeni_ids([ra["id"], rb["id"]]) == {ra["id"]}
        assert d3.isoformat() not in str(smtp.primljeno[0]["telo"])
        from tests.test_osb002_solo_tok import B
        assert k.get(f"/api/rokovi/kandidati?predmet_id={pid}", headers=B).json()["rokovi"] == []      # drugi korisnik
        assert all(h["user_id"] == "uid-A" for h in _rokovi(b, pid))
    finally:
        smtp.zatvori()


# ── nezavisni pregled: ispravka advokata se pripisuje tačnom dokumentu i tačnoj obavezi; ISO vrednost ─────────────

def _prijem(b, posao, ispravke=(), ocr=True):
    pid_ = str(_uuid.uuid4())
    b.table("intake_documents").insert({"id": pid_, "intake_job_id": posao, "ocr_used": ocr}).execute()
    for vrednost, ispravka in ispravke:
        b.table("extracted_entities").insert({"id": str(_uuid.uuid4()), "document_id": pid_, "entity_type": "deadline",
                                              "value": vrednost, "corrected_value": ispravka, "reviewed": True}).execute()
    return pid_


def test_ispravka_jednog_segmenta_ne_brise_obavezu_drugog_segmenta(lanac):
    k, b = lanac
    pid = _predmet(k)
    posao = str(_uuid.uuid4())
    p1, p2 = _prijem(b, posao, [(SA, "20.12.2026")]), _prijem(b, posao)
    s1, s2 = str(_uuid.uuid4()), str(_uuid.uuid4())
    b.table("intake_job_segments").insert({"id": s1, "intake_job_id": posao, "document_id": p1}).execute()
    b.table("intake_job_segments").insert({"id": s2, "intake_job_id": posao, "document_id": p2}).execute()
    d1 = _dok(b, pid, "\n".join(TROSKOVI), posao=posao)
    d2 = _dok(b, pid, "\n".join(TAKSA), posao=posao)
    for did, seg in ((d1, s1), (d2, s2)):
        next(d for d in b.tabele["predmet_dokumenti"] if d["id"] == did)["source_intake_job_segment_id"] = seg
    ishod = _uskladi(b, pid, poslovi=[posao])
    assert ishod["ispravljeno"] == [(d1, DA)] and [h["dokument_id"] for h in _rokovi(b, pid)] == [d2]


def test_ispravka_datuma_sa_dve_obaveze_ne_brise_nijednu(lanac):
    k, b = lanac
    pid = _predmet(k)
    posao = str(_uuid.uuid4())
    _prijem(b, posao, [(SA, "20.12.2026")])
    _dok(b, pid, f"RESENJE\nRok za zalbu istice {SA} godine.\nRok za uplatu sudske takse istice {SA} godine.", posao=posao)
    ishod = _uskladi(b, pid, poslovi=[posao])
    assert ishod["ispravljeno"] == [] and len(_rokovi(b, pid)) == 2              # ne zna se na koju se odnosi


def test_ispravka_sa_iso_vrednoscu_se_postuje(lanac):
    k, b = lanac
    pid = _predmet(k)
    posao = str(_uuid.uuid4())
    _prijem(b, posao, [(DA, "2026-12-20")])
    did = _dok(b, pid, "\n".join(TAKSA), posao=posao)
    assert _uskladi(b, pid, poslovi=[posao])["ispravljeno"] == [(did, DA)] and _rokovi(b, pid) == []


# ── nezavisni pregled #1: nastavak koji prikači NOVE dokumente dobija svoj identitet događaja ──────────────────────

def test_identitet_prihvatanja_prvi_pokusaj_isti_nastavak_sa_novim_dokumentima_svoj():
    from routers.smart_intake import _id_prihvatanja_posla as idp
    posao = str(_uuid.uuid4())
    assert idp(posao) == idp(posao, None) == idp(posao, [])                       # FRG001: ponovna emisija = no-op
    novi = idp(posao, ["d3"])
    assert novi != idp(posao) and novi == idp(posao, ["d3"])                       # deterministički po skupu
    assert idp(posao, ["d3", "d4"]) == idp(posao, ["d4", "d3"]) != novi


def test_nastavak_posle_obradjenog_dogadjaja_uskladjuje_novi_dokument(lanac, monkeypatch):
    """Posao sa dva akta; prvi pokušaj upiše samo prvi, njegov DOCUMENT_ACCEPTED se OBRADI; nastavak upiše drugi.
    Rok drugog je ispod praga (kao OCR) pa ga Smart Intake ne upisuje — mora ga usklađivanje nastavka."""
    import io
    from datetime import datetime, timedelta, timezone

    from reportlab.pdfgen import canvas

    from tests.test_osb002_solo_tok import _do_kraja_dogadjaja
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for redovi in (["OSNOVNI SUD U BEOGRADU", "RESENJE", "Posl. br. P 1111/2026", f"Rok za zalbu na troskove istice {SA} godine."],
                   ["OSNOVNI SUD U NOVOM SADU", "PRESUDA", "Posl. br. P 2222/2026",
                    f"Rok za uplatu dodatne sudske takse istice {SA} godine."]):
        for i, r in enumerate(redovi):
            c.drawString(50, 800 - 20 * i, r)
        c.showPage()
    c.save()
    r = k.post("/api/smart-intake/documents", files=[("files", ("dva.pdf", buf.getvalue(), "application/pdf"))], headers=A)
    jid = r.json()["rezultati"][0]["job_id"]
    _do_kraja()
    prijemi = [d["id"] for d in b.tabele["intake_documents"] if d["intake_job_id"] == jid]
    assert len(prijemi) == 2
    for e in b.tabele["extracted_entities"]:
        if e["document_id"] in prijemi and e["entity_type"] == "case_number":
            e["corrected_value"], e["reviewed"] = "P 1111/2026", True              # advokat: isti predmet
    seg = sorted((x for x in b.tabele["intake_job_segments"] if x["intake_job_id"] == jid), key=lambda x: x["segment_index"])
    taksa_prijem = seg[-1]["document_id"]                                       # drugi akt (taksa)
    for e in b.tabele["extracted_entities"]:
        if e["document_id"] == taksa_prijem and e["entity_type"] == "deadline":
            e["confidence"] = 0.5                                                 # kao OCR: SI ne upisuje
    if k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()["job"]["status"] == "awaiting_review":
        k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A)
        _do_kraja()
    orig = _h._Upit.execute
    stanje = {"dok": 0}

    def execute(self):                                   # drugi akt se u prvom pokušaju ne upiše (prolazna greška)
        if self.t == "predmet_dokumenti" and self.radnja[0] == "insert":
            stanje["dok"] += 1
            if stanje["dok"] == 2:
                raise RuntimeError("upis dokumenta pao (test)")
        return orig(self)
    monkeypatch.setattr(_h._Upit, "execute", execute)
    prvi = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    monkeypatch.setattr(_h._Upit, "execute", orig)
    assert prvi.status_code == 200, prvi.text
    assert len([d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]) == 1
    _do_kraja_dogadjaja(b)                               # prvi događaj OBRAĐEN — usklađen je samo prvi akt
    posao = next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)
    posao["finalizing_at"] = (datetime.now(timezone.utc) - timedelta(seconds=121)).isoformat()
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    assert f.status_code == 200, f.text
    _do_kraja_dogadjaja(b)
    dok = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]
    assert len(dok) == 2
    takse = [h for h in _rokovi(b, pid) if "takse" in (h.get("dogadjaj") or "")]
    assert len(takse) == 1 and takse[0]["dokument_id"] in {d["id"] for d in dok}, \
        [(h["dogadjaj"], h.get("dokument_id")) for h in _rokovi(b, pid)]
    prihvatanja = [e for e in b.tabele["events"] if e["event_type"] == "DocumentAccepted"]
    assert len(prihvatanja) == 2 and len({e["id"] for e in prihvatanja}) == 2
