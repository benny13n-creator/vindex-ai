# -*- coding: utf-8 -*-
"""N3 — ročišta: predlozi iz teksta sudskih dokumenata (shared/rociste_iz_teksta.py) i rute
GET /api/rocista/predlozi, POST /api/rocista/predlozi/odbaci. Predlog nikad nije ročište.
Browser tok: frontend-v2-ng/tests/live-n3-rocista-e2e.mjs."""
from datetime import date, timedelta

from routers.email_notif import _danas_beograd

import pytest

from shared.rociste_iz_teksta import broj_iz_teksta, nadji_rocista, sud_iz_teksta
from tests.test_osb002_solo_tok import A, B, _otpremi, _pdf, _radnik, solo  # noqa: F401


@pytest.fixture
def lanac(solo, monkeypatch):
    """`log_action` upisuje u bazu u memoriji, ALI uz stvarnu proveru `AUDITABLE_ACTIONS` (harness za browser je preskače)."""
    import shared.audit_immutable as AUD
    k, b = solo

    async def _upis(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
        if action not in AUD.AUDITABLE_ACTIONS:
            return None
        r = b.table("audit_immutable").insert({"action": action, "user_id": user_id, "resource_type": resource_type,
                                               "resource_id": resource_id, "metadata": metadata or {}}).execute()
        return (r.data or [{}])[0].get("id") or "ok"
    monkeypatch.setattr(AUD, "log_action", _upis)
    return k, b


def _jedan(t):
    r = nadji_rocista(t)
    assert len(r) == 1, r
    return r[0]


# ── izvlačenje ────────────────────────────────────────────────────────────────

def test_poziv_datum_vreme_sudnica_sud_broj():
    t = ("OSNOVNI SUD U BEOGRADU\nPosl. br. P 5521/2026\nPOZIV ZA ROČIŠTE\nU predmetu radi poništaja rešenja o otkazu "
         "ugovora o radu, pripremno ročište zakazuje se za 15.11.2026. godine u 10:00 časova, u sudnici broj 14.")
    r = _jedan(t)
    assert (r["datum"], r["vreme"], r["sudnica"]) == (date(2026, 11, 15), "10:00", "14")
    assert "zakazuje se za 15.11.2026" in r["citat"]
    assert sud_iz_teksta(t) == "Osnovni sud u Beogradu" and broj_iz_teksta(t) == "P 5521/2026"


def test_otkaz_ugovora_kao_predmet_spora_ne_gasi_predlog():
    """Radni spor: „o otkazu“ odmah posle datuma je predmet spora, ne stanje ročišta."""
    r = _jedan("Ročište se zakazuje za 02.12.2026. godine u 9,30 časova radi rasprave o otkazu ugovora o radu.")
    assert (r["datum"], r["vreme"]) == (date(2026, 12, 2), "09:30")


@pytest.mark.parametrize("t", [
    "Ročište zakazano za 15.11.2026. godine odlaže se do daljeg.",
    "Ročište je održano dana 15.11.2026. godine u 11:00 časova.",
    "Ročište zakazano za 15.11.2026. godine otkazuje se.",
    "Ročište se zakazuje za 31.02.2027. godine u 10:00 časova.",          # nemoguć datum (OCR)
    "Ročište se zakazuje za 29.02.2027. godine u 10:00 časova.",          # 2027 nije prestupna
    "Tužba je podneta 15.11.2026. godine.",                                # nema reči ročište
])
def test_nije_predlog(t):
    assert nadji_rocista(t) == []


# Nalaz nezavisnog pregleda (N3): realne formulacije koje prvo izvlačenje nije razumelo. Očekivanje = šta advokat
# treba da vidi kao PREDLOG (prazno = ništa; datum = jedini predlog).
PREGLED = [
    ("Ročište zakazano za 12.11.2026. godine se odlaže.", []),
    ("Obaveštavamo vas da ročište zakazano za 12.11.2026. godine neće se održati.", []),
    ("Ročište se neće održati 15.11.2026. zbog štrajka.", []),
    ("Ročište zakazano za 15.11.2026. skida se sa dnevnog reda.", []),
    ("Odloženo ročište od 12.11.2026. godine", []),
    ("Ročište za glavnu raspravu biće zakazano naknadno. U Beogradu, dana 30.10.2026. godine Sudija", []),
    ("DOSTAVNICA Poziv za ročište. Primljeno dana 30.10.2026.", []),
    ("Ročište se odlaže na neodređeno vreme. Veštaku se nalaže da nalaz dostavi do 15.12.2026.", []),
    ("Na ročištu stranke su se saglasile da tuženi isplati iznos do 30.11.2026. godine.", []),
    ("PRESUDA nakon javne glavne rasprave zaključene dana 20.11.2026. godine", []),
    ("ZAPISNIK sa ročišta održanog dana 27.10.2026. godine u 10:00 časova", []),
    ("Na danas održanom ročištu dana 27.10.2026. stranke su", []),
    ("Ročište zakazano za 15.1 1.2026. u 10:00, a rok za odgovor je 20.11.2026.", []),     # OCR pokvaren datum: ništa, ne rok
    ("Rok za odgovor na tužbu je 20.11.2026, a ročište će biti zakazano posle.", []),
    ("Ročište od 12.11.2026 zakazuje se 03.12.2026 sa početkom u 09:30", [(date(2026, 12, 3), "09:30")]),
    ("Ročište zakazano za 12.11.2026. godine odlaže se i zakazuje za 03.12.2026. godine u 10:00 časova.", [(date(2026, 12, 3), "10:00")]),
    ("Poziva se tuženi da dana 15.11.2026. godine u 10,00 časova pristupi na ročište u sudnici 12.", [(date(2026, 11, 15), "10:00")]),
    ("Ročište će se održati dana 15.11.2026. u 10:00 časova u sudnici broj 115.", [(date(2026, 11, 15), "10:00")]),
    ("Pripremno ročište zakazuje se za 15.11.2026. godine u 10 časova.", [(date(2026, 11, 15), "10:00")]),
    ("Odluka o otkazu ugovora o radu. Ročište 15.11.2026. u 10:00.", [(date(2026, 11, 15), "10:00")]),
    ("Ročište se odlaže za 03.12.2026. godine u 10 časova.", [(date(2026, 12, 3), "10:00")]),
    ("Ročište zakazano za 12.11.2026. godine odlaže se za 03.12.2026. u 09:00.", [(date(2026, 12, 3), "09:00")]),
    ("pripremno ročište zakazuje se za\n15.11.2026. godine u 10:00 časova", [(date(2026, 11, 15), "10:00")]),   # prelom reda
]


@pytest.mark.parametrize("t,ocekivano", PREGLED)
def test_realne_formulacije_iz_pregleda(t, ocekivano):
    assert [(x["datum"], x["vreme"]) for x in nadji_rocista(t)] == ocekivano


# Drugi krug nezavisnog pregleda (N3): pomeranje, „umesto“, prekid, „biće održana“, skraćenice, akt „od“ datuma.
PREGLED2 = [
    ('DOSTAVNICA\nPoziv za ročište P 100/2026 primljen dana 30.10.2026. godine.', []),
    ('Presuda je doneta posle javne rasprave 30.10.2026. godine.', []),
    ('Ročište koje je bilo zakazano za 12.11.2026. godine sud je pomerio za 03.12.2026. godine.', [(date(2026, 12, 3), None)]),
    ('Ročište je zakazano rešenjem od 28.10.2026. godine za 15.11.2026. godine u 10 časova.', [(date(2026, 11, 15), '10:00')]),
    ('Tuženi je u podnesku od 30.10.2026. godine osporio navode i raspravljao o visini štete.', []),
    ('Ročište zakazano za 12.11.2026. prekida se, jer je tuženi preminuo.', []),
    ('Ročište zakazano za 12.11.2026. se ne može održati zbog bolesti sudije.', []),
    ('Ročište zakazano za 12.11.2026. nije se moglo održati.', []),
    ('Umesto ročišta zakazanog za 12.11.2026. godine, ročište će se održati 03.12.2026. godine.', [(date(2026, 12, 3), None)]),
    ('Ročište zakazano za 12.11.2026.\n\nOdlaže se do daljeg.', []),
    ('ZAPISNIK O GLAVNOJ RASPRAVI\nSastavljen dana 27.10.2026. godine kod Osnovnog suda u Beogradu. Započeto u 10:00 časova.', []),
    ('Na ročište zakazano za danas pristupio je tužilac dana 27.10.2026. godine u 10 časova.', []),
    ('Protiv ove presude doneta posle glavne rasprave može se izjaviti žalba u roku od 15 dana, a najdocnije 15.11.2026.', []),
    ('Raspravno veće je odredilo da će se odluka objaviti 15.11.2026. godine.', []),
    ('Ročište se odlaže za 03.12.2026. godine u 10 časova.', [(date(2026, 12, 3), '10:00')]),
    ('Ročište se odlaže i zakazuje za 03.12.2026. godine u 10:00 časova.', [(date(2026, 12, 3), '10:00')]),
    ('Glavna rasprava biće održana dana 15.11.2026. godine u 10 časova.', [(date(2026, 11, 15), '10:00')]),
    ('Nastavak glavne rasprave biće održan 15.11.2026. u 11:00 časova.', [(date(2026, 11, 15), '11:00')]),
    ('Ročište zakazano kod sudije dr. Jovana Petrovića za 15.11.2026. u 10 časova.', [(date(2026, 11, 15), '10:00')]),
    ('Pripremno ročište zakazuje se za 10.11.2026. godine, a glavna rasprava za 20.11.2026. godine.', [(date(2026, 11, 10), None), (date(2026, 11, 20), None)]),
    ('Pozivate se da kao svedok pristupite ovom sudu dana 15.11.2026. godine u 9,30 časova, sudnica 12, radi saslušanja na ročištu.', [(date(2026, 11, 15), '09:30')]),
    ('Наставак главне расправе одржаће се дана 15.11.2026. године у 10 часова у судници 3.', [(date(2026, 11, 15), '10:00')]),
    ('Dokazi su dostavljeni naknadno. Ročište se zakazuje za 15.11.2026.', [(date(2026, 11, 15), None)]),
    ('Pošto su dokazi dostavljeni naknadno, ročište se zakazuje za 15.11.2026.', [(date(2026, 11, 15), None)]),
    ('Ročište se odlaže, a novo ročište zakazuje se za 03.12.2026. u 10:00.', [(date(2026, 12, 3), '10:00')]),
    ('Ročište se zaka-\nzuje za 15.11.2026. u 10:00.', [(date(2026, 11, 15), '10:00')]),
    ('Ročište se zakazuje za 15. 11. 2026. godine u 10 . 00 časova.', [(date(2026, 11, 15), '10:00')]),
    ('Dana 15.11.2026. godine u 10 časova održaće se ročište.', []),   # poznata granica: datum ispred glagola se ne prepoznaje
    ('Ročište se zakazuje za 15.11.2026. g. u 10 časova.', [(date(2026, 11, 15), '10:00')]),
    ('Glavna rasprava se zaključuje. Ročište za objavljivanje presude zakazuje se za 15.11.2026.', [(date(2026, 11, 15), None)]),
    ('U sporu radi raskida zaključenog ugovora ročište se zakazuje za 15.11.2026. godine u 10 časova.', [(date(2026, 11, 15), '10:00')]),
    ('Ročište po predlogu za odlaganje izvršenja zakazuje se za 15.11.2026.', [(date(2026, 11, 15), None)]),
]


@pytest.mark.parametrize("t,ocekivano", PREGLED2)
def test_realne_formulacije_drugi_krug(t, ocekivano):
    assert [(x["datum"], x["vreme"]) for x in nadji_rocista(t)] == ocekivano


def test_odlaganje_predlaze_samo_novo_rociste():
    r = _jedan("Ročište zakazano za 15.11.2026. godine odlaže se. Novo ročište zakazuje se za 05.12.2026. godine u 09:30 časova, sudnica 7.")
    assert (r["datum"], r["vreme"], r["sudnica"]) == (date(2026, 12, 5), "09:30", "7")
    assert r["citat"].startswith("Novo ročište")


def test_prestupni_dan_prelaz_godine_cirilica_i_mesec_recima():
    assert _jedan("Ročište se zakazuje za 29.02.2028. godine u 08:00 časova.")["datum"] == date(2028, 2, 29)
    assert _jedan("Glavna rasprava zakazana je za 04.01.2027. godine u 13:00 h.")["datum"] == date(2027, 1, 4)
    c = _jedan("Рочиште се заказује за 12.01.2027. године у 11,00 часова у судници 205.")
    assert (c["datum"], c["vreme"], c["sudnica"]) == (date(2027, 1, 12), "11:00", "205")
    m = _jedan("glavna rasprava će se održati 3. decembra 2026. godine sa početkom u 9.15 h")
    assert (m["datum"], m["vreme"]) == (date(2026, 12, 3), "09:15")
    assert sud_iz_teksta("ВИШИ СУД У НОВОМ САДУ") == "Viši sud u Novom Sadu"


def test_dva_rocista_u_jednom_dokumentu_i_bez_vremena():
    r = nadji_rocista("Pripremno ročište zakazuje se za 10.11.2026. godine. Ročište za glavnu raspravu zakazuje se za "
                      "20.11.2026. godine u 12:00 časova.")
    assert [(x["datum"], x["vreme"]) for x in r] == [(date(2026, 11, 10), None), (date(2026, 11, 20), "12:00")]


# ── rute nad stvarnim prijemom ─────────────────────────────────────────────────

def _sr(d):
    return d.strftime("%d.%m.%Y.")


def _predmet(k, h=A, naziv="Predmet za rociste"):
    r = k.post("/klijenti", json={"tip": "fizicko_lice", "ime": "Ana", "prezime": naziv.replace(" ", "")}, headers=h)
    kid = r.json()["klijent"]["id"]
    r = k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": naziv}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["predmet_id"]


def _prikaci(k, b, pid, redovi, ime="Poziv za rociste.pdf"):
    r = _otpremi(k, _pdf(redovi), ime=ime)
    assert r.status_code in (200, 202), r.text
    jid = r.json()["rezultati"][0]["job_id"]
    for _ in range(3):
        _radnik()
    posao = next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)
    if posao["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=A).status_code == 200
    r = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid, "klijent_strana": "plaintiff"}, headers=A)
    assert r.status_code == 200, r.text
    return jid


def test_poziv_kroz_stvaran_prijem_daje_predlog_a_ne_rociste(lanac):
    k, b = lanac
    pid = _predmet(k)
    dan = _danas_beograd() + timedelta(days=40)
    _prikaci(k, b, pid, ["OSNOVNI SUD U BEOGRADU", "Posl. br. P 77/2026", "POZIV ZA ROCISTE",
                         f"Pripremno rociste zakazuje se za {_sr(dan)} godine u 10:00 casova, u sudnici broj 14."])
    assert any((d.get("tekst_sadrzaj") or "").strip() for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid)
    r = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A)
    assert r.status_code == 200, r.text
    p = r.json()["predlozi"]
    assert len(p) == 1 and p[0]["datum"] == dan.isoformat() and p[0]["vreme"] == "10:00" and p[0]["sudnica"] == "14"
    assert p[0]["sud"] == "Osnovni sud u Beogradu" and p[0]["broj_predmeta_suda"] == "P 77/2026"
    assert p[0]["izvori"][0]["naziv"] == "Poziv za rociste.pdf" and "zakazuje se" in p[0]["izvori"][0]["citat"]
    assert [x for x in b.tabele.get("rocista", []) if x["predmet_id"] == pid] == []           # predlog NIJE ročište
    # B nema pristup
    assert k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=B).status_code == 404
    assert k.post("/api/rocista/predlozi/odbaci", json={"predmet_id": pid, "kljuc": p[0]["kljuc"]}, headers=B).status_code == 404
    # zakazano ročište gasi predlog (bez obzira na stanje); odbacivanje drugog je trajno
    assert k.post("/api/rocista", json={"predmet_id": pid, "sud": p[0]["sud"], "datum": dan.isoformat(), "vreme": "10:00"}, headers=A).status_code == 200
    assert k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"] == []


def test_odbacivanje_trajno_po_predmetu_i_prosli_se_broje(lanac):
    k, b = lanac
    pid, pid2 = _predmet(k), _predmet(k, naziv="Drugi predmet")
    dan, proslo = _danas_beograd() + timedelta(days=30), _danas_beograd() - timedelta(days=30)
    tekst = f"Rociste se zakazuje za {_sr(dan)} godine u 09:00 casova. Prethodno rociste je odrzano {_sr(proslo)} godine."
    for p_ in (pid, pid2):
        b.tabele.setdefault("predmet_dokumenti", []).append({"id": f"d-{p_}", "predmet_id": p_, "user_id": "uid-A", "naziv_fajla": "Z.pdf", "tekst_sadrzaj": tekst})
    b.tabele["predmet_dokumenti"].append({"id": "d-prazan", "predmet_id": pid, "user_id": "uid-A", "naziv_fajla": "Sken.pdf", "tekst_sadrzaj": ""})
    d = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()
    assert [x["datum"] for x in d["predlozi"]] == [dan.isoformat()] and d["dokumenata_bez_teksta"] == 1
    kljuc = d["predlozi"][0]["kljuc"]
    assert k.post("/api/rocista/predlozi/odbaci", json={"predmet_id": pid, "kljuc": kljuc}, headers=A).status_code == 200
    assert k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"] == []
    assert len(k.get(f"/api/rocista/predlozi?predmet_id={pid2}", headers=A).json()["predlozi"]) == 1   # drugi predmet nije pogođen
    assert k.post("/api/rocista/predlozi/odbaci", json={"predmet_id": pid, "kljuc": "nije-kljuc"}, headers=A).status_code == 422
    assert not [x for x in b.tabele.get("rocista", []) if x["predmet_id"] in (pid, pid2)]


def test_pad_citanja_nije_prazan_spisak(solo, monkeypatch):
    k, b = solo
    pid = _predmet(k)
    import routers.rocista as R
    pravi = R._get_supa

    class _Pada:
        def __init__(self, s):
            self._s = s

        def table(self, ime):
            t = self._s.table(ime)
            if ime == "predmet_dokumenti":
                t.select = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("baza pala"))
            return t

    monkeypatch.setattr(R, "_get_supa", lambda: _Pada(pravi()))
    r = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A)
    assert r.status_code == 503 and "predlozi" not in r.json()            # pad nije prazan spisak; poruku piše V2


def test_star_poziv_bez_reci_odrzano_nije_predlog_i_broji_se(lanac):
    """Stari poziv (datum prošao) ne nosi oznaku stanja — odbacuje ga tek filter prošlih datuma, uz broj."""
    k, b = lanac
    pid = _predmet(k, naziv="Stari poziv")
    proslo, sutra = _danas_beograd() - timedelta(days=3), _danas_beograd() + timedelta(days=1)
    b.tabele.setdefault("predmet_dokumenti", []).append({"id": "d-star", "predmet_id": pid, "user_id": "uid-A", "naziv_fajla": "Stari poziv.pdf",
        "tekst_sadrzaj": f"Rociste se zakazuje za {_sr(proslo)} godine u 10:00 casova. Ponovljeno rociste zakazuje se za {_sr(sutra)} godine u 08:30 casova."})
    d = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()
    assert [x["datum"] for x in d["predlozi"]] == [sutra.isoformat()] and d["proslih"] == 1, d


def test_isti_datum_sa_vremenom_i_bez_je_jedan_predlog(lanac):
    k, b = lanac
    pid = _predmet(k, naziv="Spajanje")
    dan = _danas_beograd() + timedelta(days=12)
    for i, t in enumerate([f"Rociste se zakazuje za {_sr(dan)} godine u 11:00 casova.", f"Rociste je zakazano za {_sr(dan)} godine."]):
        b.tabele.setdefault("predmet_dokumenti", []).append({"id": f"d-s{i}", "predmet_id": pid, "user_id": "uid-A", "naziv_fajla": f"D{i}.pdf", "tekst_sadrzaj": t})
    p = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"]
    assert len(p) == 1 and p[0]["vreme"] == "11:00" and sorted(x["naziv"] for x in p[0]["izvori"]) == ["D0.pdf", "D1.pdf"], p


def test_odbacen_datum_sa_vremenom_gasi_i_isti_datum_bez_vremena(lanac):
    k, b = lanac
    pid = _predmet(k, naziv="Odbacivanje spojenog")
    dan = _danas_beograd() + timedelta(days=14)
    for i, t in enumerate([f"Rociste se zakazuje za {_sr(dan)} godine u 11:00 casova.", f"Rociste je zakazano za {_sr(dan)} godine."]):
        b.tabele.setdefault("predmet_dokumenti", []).append({"id": f"d-o{i}", "predmet_id": pid, "user_id": "uid-A", "naziv_fajla": f"O{i}.pdf", "tekst_sadrzaj": t})
    p = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"]
    assert len(p) == 1
    assert k.post("/api/rocista/predlozi/odbaci", json={"predmet_id": pid, "kljuc": p[0]["kljuc"]}, headers=A).status_code == 200
    assert k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"] == []


def test_odbacen_predlog_bez_vremena_se_ne_vraca_kroz_novi_dokument(lanac):
    """Pregled N3: spajanje je ranije išlo pre odbacivanja, pa je odbačen `D|` oživljavao kao `D|11:00`."""
    k, b = lanac
    pid = _predmet(k, naziv="Bez vremena odbacen")
    dan = _danas_beograd() + timedelta(days=16)
    dok = b.tabele.setdefault("predmet_dokumenti", [])
    dok.append({"id": "d-bv0", "predmet_id": pid, "user_id": "uid-A", "naziv_fajla": "Bez.pdf", "tekst_sadrzaj": f"Rociste je zakazano za {_sr(dan)} godine."})
    p = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"]
    assert len(p) == 1 and p[0]["vreme"] is None
    assert k.post("/api/rocista/predlozi/odbaci", json={"predmet_id": pid, "kljuc": p[0]["kljuc"]}, headers=A).status_code == 200
    dok.append({"id": "d-bv1", "predmet_id": pid, "user_id": "uid-A", "naziv_fajla": "Sa.pdf", "tekst_sadrzaj": f"Rociste se zakazuje za {_sr(dan)} godine u 11:00 casova."})
    p2 = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"]
    assert len(p2) == 1 and p2[0]["vreme"] == "11:00" and [x["naziv"] for x in p2[0]["izvori"]] == ["Sa.pdf"], p2


# ── S1-C2 (revizija Sektora 1): vraćanje odloženog ročišta posle zakazanog nastavka ──

def test_s1_vrati_na_zakazano_posle_nastavka_409_bez_dva_aktivna(lanac):
    from routers.email_notif import _danas_beograd
    k, b = lanac
    pid = _predmet(k)
    d1, d2 = _danas_beograd() + timedelta(days=10), _danas_beograd() + timedelta(days=40)
    r1 = k.post("/api/rocista", json={"predmet_id": pid, "sud": "Osnovni sud u Beogradu", "datum": d1.isoformat()}, headers=A).json()["rociste"]
    assert k.patch(f"/api/rocista/{r1['id']}", json={"status": "odlozeno"}, headers=A).status_code == 200
    assert k.post("/api/rocista", json={"predmet_id": pid, "sud": "Osnovni sud u Beogradu", "datum": d2.isoformat()}, headers=A).status_code == 200
    r = k.patch(f"/api/rocista/{r1['id']}", json={"status": "zakazano"}, headers=A)
    assert r.status_code == 409 and d2.isoformat() in r.json()["detail"]
    akt = [x for x in b.tabele["rocista"] if x["predmet_id"] == pid and (x.get("status") or "zakazano") == "zakazano"]
    assert [x["datum"] for x in akt] == [d2.isoformat()]


def test_s1_vrati_na_zakazano_bez_nastavka_i_dalje_radi(lanac):
    from routers.email_notif import _danas_beograd
    k, b = lanac
    pid = _predmet(k)
    d1 = _danas_beograd() + timedelta(days=10)
    r1 = k.post("/api/rocista", json={"predmet_id": pid, "sud": "Osnovni sud u Beogradu", "datum": d1.isoformat()}, headers=A).json()["rociste"]
    assert k.patch(f"/api/rocista/{r1['id']}", json={"status": "odlozeno"}, headers=A).status_code == 200
    assert k.patch(f"/api/rocista/{r1['id']}", json={"status": "zakazano"}, headers=A).status_code == 200
