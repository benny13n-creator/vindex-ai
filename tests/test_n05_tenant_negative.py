# -*- coding: utf-8 -*-
"""N05 — negativni testovi izolacije zakupaca kroz kritične tokove (Smart Intake, dokumenti, izvoz, rokovi, AI).

Dva STROGO odvojena sintetička korisnika A i B, svaki sa sopstvenim predmetom, poslom prijema i dokumentom.
Svaki napad je izvršen HTTP zahtev kroz STVARNE rute (`api.app`), a provera je trostruka:
  (1) statusni kod, (2) telo odgovora ne sadrži nijedan podatak korisnika B (ime fajla, tekst, rok, predmet),
  (3) odbijen zahtev ne ostavlja upis — snimak relevantnih tabela PRE i POSLE je identičan.
Uz svaki napad postoji pozitivna kontrola (vlasnik isti zahtev izvršava uspešno), da 404 ne bi dolazio od
pokvarenog okruženja umesto od provere vlasništva.

Harness: tests/ns005_harness.py (lažan Supabase koji VERNO primenjuje `.eq` filtere, service-role semantika —
RLS se ovde NE proverava), tests/ns005_intake_fake.py (SQL-verna emulacija intake reda), stvaran intake worker
nad digitalnim PDF-om (bez Tesseract-a). AI: Law Brain sinteza preko tests/ns008_fake.py, `/api/pitanje` preko
NS005 fixture-a iz tests/test_ns005_t6_pravno_pitanje.py. Nijedan poziv ne napušta loopback.
"""
import copy
import json
import uuid

import pytest

import shared.audit_immutable as _audit_mod
from tests.ns005_harness import zaglavlje, SPOLJNI_POKUSAJI
from tests.test_ns005_t14_smart_intake import PA, PB, _obradi, _otpremi, ok  # noqa: F401 — `ok` je fixture
from tests.test_vcr002_t02_ocr_korpus import _digitalni_pdf

# Pravi `log_action` (harness ga gasi): odluka o roku i pregled dokumenta SU upisi u audit lanac, pa se
# odsustvo upisa posle odbijenog napada meri u stvarnoj tabeli `audit_immutable`.
_PRAVI_LOG = _audit_mod.log_action

A_LINIJE = [
    "OSNOVNI SUD U SUBOTICI",
    "Broj predmeta: P 1100/2026",
    "Tuzilac: Aleksandar Alfic iz Subotice",
    "Tuzeni: Alfa Promet DOO iz Sombora",
    "Rok za odgovor na tuzbu je 30 dana od dana dostavljanja.",
]
B_LINIJE = [
    "VISI SUD U LESKOVCU",
    "Broj predmeta: P 8813/2026",
    "Tuzilac: Bozidar Betakovic iz Vranja",
    "Tuzeni: Beta Tajna Gradnja DOO iz Pirota",
    "Rok za odgovor na tuzbu je 15 dana od dana dostavljanja.",
]
B_IME = "betakovic_tajni_ugovor.pdf"
A_IME = "alfic_tuzba.pdf"
# Bilo koji od ovih nizova u odgovoru korisniku A = curenje podataka korisnika B.
B_TRAGOVI = ("Betakovic", "betakovic", "8813", "Beta Tajna", "LESKOVCU", "uid-B", "TAJNI rok B", "TAJNA BELESKA B",
             "Predmet B")

# Tabele čije stanje odbijen napad NE SME da promeni.
# `audit_immutable` se meri posebno (`_audit_o_B`): pozadinski audit zadaci vlasnikovih ranijih radnji (create_task)
# smeju da se upišu tokom kasnijeg zahteva, pa sirov snimak tabele nije deterministički.
TABELE = ("intake_jobs", "predmet_dokumenti", "extracted_entities", "intake_review_queue", "predmet_hronologija",
          "predmeti", "klijenti", "predmet_klijenti", "events", "v2_mutation_idempotency",
          "predmet_beleske")


def _snimak(b):
    return json.dumps({t: b.tabele.get(t, []) for t in TABELE}, sort_keys=True, default=str)


def _audit_o_B(b, b_ids):
    """Audit redovi koje je napadač A ostavio o B-ovim objektima (mora biti prazno)."""
    return [x for x in b.tabele.get("audit_immutable", []) if x.get("user_id") == "uid-A"
            and (str(x.get("resource_id")) in b_ids or any(i in str(x.get("metadata") or "") for i in b_ids))]


def _bez_b(r):
    for x in B_TRAGOVI:
        assert x not in r.text, f"curenje podatka B ({x!r}) u odgovoru {r.status_code}: {r.text[:300]}"


def _posao(b, jid):
    return next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)


def _pripremi_posao(k, korisnik, linije, ime):
    r = _otpremi(k, korisnik, _digitalni_pdf(linije), ime=ime)
    assert r.status_code == 202, r.text
    x = r.json()["rezultati"][0]
    assert x["ok"] is True, x
    assert _obradi() is True
    jid = x["job_id"]
    st = k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje(korisnik))
    assert st.status_code == 200, st.text
    if st.json()["job"]["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=zaglavlje(korisnik)).status_code == 200
    return jid


@pytest.fixture
def svet(ok, monkeypatch):  # noqa: F811
    """A i B: svaki svoj predmet, svoj posao prijema (pregledan, spreman), B-ov dokument prikačen predmetu B,
    svaki svoj rok-kandidat i belešku."""
    k, b = ok
    monkeypatch.setattr(_audit_mod, "log_action", _PRAVI_LOG)
    b.tabele.setdefault("audit_immutable", [])
    b.tabele["predmet_hronologija"] = [
        {"id": "rok-A-1", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Rok za odgovor A", "datum_iso": "2026-11-20",
         "vaznost": "visok", "izvor": "ai", "vrsta": "rok", "stanje": "kandidat"},
        {"id": "rok-B-1", "user_id": "uid-B", "predmet_id": PB, "dogadjaj": "TAJNI rok B", "datum_iso": "2026-11-18",
         "vaznost": "kritičan", "izvor": "ai", "vrsta": "rok", "stanje": "kandidat"},
    ]
    b.tabele["predmet_beleske"] = [
        {"id": "bel-A", "predmet_id": PA, "user_id": "uid-A", "sadrzaj": "Beleska A o svedoku", "created_at": "2026-10-01"},
        {"id": "bel-B", "predmet_id": PB, "user_id": "uid-B", "sadrzaj": "TAJNA BELESKA B o nagodbi", "created_at": "2026-10-01"},
    ]
    for t in ("predmet_istorija", "predmet_dokazi", "billing_entries", "rocista", "predmet_komentari", "usage_events",
              "korisnik_email_notif"):
        b.tabele.setdefault(t, [])
    b.tabele["billing_entries"] += [
        {"id": "bil-A", "user_id": "uid-A", "predmet_id": PA, "opis": "Sastanak A", "datum": "2026-10-01", "iznos_rsd": 1},
        {"id": "bil-B", "user_id": "uid-B", "predmet_id": PB, "opis": "Beta Tajna naplata", "datum": "2026-10-01", "iznos_rsd": 2},
    ]
    b.tabele["profiles"] = [{"id": "uid-A", "email": "uid-A@primer.test"}, {"id": "uid-B", "email": "uid-B@primer.test"}]

    jA = _pripremi_posao(k, "A", A_LINIJE, A_IME)
    jB = _pripremi_posao(k, "B", B_LINIJE, B_IME)
    # B prikači svoj posao svom predmetu — tako nastaje B-ov dokument (tekst + šifrovan original u skladištu).
    jB2 = _pripremi_posao(k, "B", B_LINIJE + ["Prilog 2: ugovor o gradjenju"], "betakovic_prilog.pdf")
    f = k.post(f"/api/smart-intake/jobs/{jB2}/finalize", json={"predmet_id": PB}, headers=zaglavlje("B"))
    assert f.status_code == 200 and f.json()["ok"] is True, f.text
    dokB = next(d for d in b.tabele["predmet_dokumenti"] if d["user_id"] == "uid-B")
    # Dokument prikačen kroz Smart Intake nosi oznaku `session/<id>`, ne put do originala (smart_intake.py); original
    # postoji samo za dokument otpremljen direktno (api.py upload). Da bi preuzimanje imalo PRAVI original za
    # pozitivnu kontrolu, red pokazuje na B-ov stvarno šifrovan objekat u lažnoj kofi (isti format kao api.py upload).
    dokB["storage_path"] = _posao(b, jB2)["storage_path"]
    assert dokB["predmet_id"] == PB and dokB.get("storage_path") and "Betakovic" in (dokB.get("tekst_sadrzaj") or "")
    entB = next(e["id"] for e in b.tabele["extracted_entities"]
                if any(d["id"] == e["document_id"] and _posao(b, d["intake_job_id"])["uploaded_by"] == "uid-B"
                       for d in b.tabele["intake_documents"]))
    b_ids = {PB, jB, jB2, dokB["id"], entB, "rok-B-1", "bel-B"}
    return {"k": k, "b": b, "jA": jA, "jB": jB, "dokB": dokB["id"], "entB": entB, "b_ids": b_ids}


# ── 1: A čita B-ov posao prijema ────────────────────────────────────────────────────────────────────────────────

def test_01_A_ne_cita_niti_menja_B_posao(svet):
    k, b, jB = svet["k"], svet["b"], svet["jB"]
    assert k.get(f"/api/smart-intake/jobs/{jB}", headers=zaglavlje("B")).status_code == 200   # pozitivna kontrola
    pre = _snimak(b)
    odgovori = [
        k.get(f"/api/smart-intake/jobs/{jB}", headers=zaglavlje("A")),
        k.post(f"/api/smart-intake/jobs/{jB}/review/resolve", headers=zaglavlje("A")),
        k.post(f"/api/smart-intake/jobs/{jB}/review/reject", headers=zaglavlje("A")),
    ]
    nepostojeci = k.get(f"/api/smart-intake/jobs/{uuid.uuid4()}", headers=zaglavlje("A"))
    for r in odgovori:
        assert r.status_code == 404, r.text
        _bez_b(r)
    assert odgovori[0].json() == nepostojeci.json()           # tuđ posao se ne razlikuje od nepostojećeg
    assert _snimak(b) == pre


# ── 2: A prikačuje B-ov posao svom predmetu ─────────────────────────────────────────────────────────────────────

def test_02_A_ne_prikacuje_B_posao_svom_predmetu(svet):
    k, b, jB = svet["k"], svet["b"], svet["jB"]
    pre, vektori = _snimak(b), list(b.vektori)
    r = k.post(f"/api/smart-intake/jobs/{jB}/finalize", json={"predmet_id": PA}, headers=zaglavlje("A"))
    assert r.status_code == 404, r.text
    _bez_b(r)
    assert _snimak(b) == pre and b.vektori == vektori
    p = _posao(b, jB)
    assert p["predmet_id"] is None and p.get("finalizing_at") is None and not p.get("assimilation_complete")
    # batch put (isto jezgro) — isti ishod, bez upisa
    rb = k.post("/api/smart-intake/jobs/finalize-batch", json={"job_ids": [jB], "predmet_id": PA}, headers=zaglavlje("A"))
    assert rb.status_code in (200, 404, 422), rb.text
    _bez_b(rb)
    assert _snimak(b) == pre and b.vektori == vektori


# ── 3: A prikačuje SVOJ posao B-ovom predmetu ───────────────────────────────────────────────────────────────────

def test_03_A_ne_prikacuje_svoj_posao_B_predmetu(svet):
    k, b, jA = svet["k"], svet["b"], svet["jA"]
    pre, vektori = _snimak(b), list(b.vektori)
    r = k.post(f"/api/smart-intake/jobs/{jA}/finalize", json={"predmet_id": PB}, headers=zaglavlje("A"))
    assert r.status_code == 404, r.text
    _bez_b(r)
    assert not [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == PB and d["user_id"] == "uid-A"]
    assert b.vektori == vektori
    p = _posao(b, jA)
    assert p["predmet_id"] is None and not p.get("assimilation_complete")
    # zauzeće je oslobođeno: A odmah može ispravno da prikači svom predmetu (pozitivna kontrola, bez 409)
    f = k.post(f"/api/smart-intake/jobs/{jA}/finalize", json={"predmet_id": PA}, headers=zaglavlje("A"))
    assert f.status_code == 200 and f.json()["predmet_id"] == PA, f.text
    assert json.loads(pre)["predmet_dokumenti"] == [d for d in b.tabele["predmet_dokumenti"] if d["user_id"] == "uid-B"]


# ── 4: A preuzima B-ov original ili OCR/tekst ───────────────────────────────────────────────────────────────────

def test_04_A_ne_dobija_B_original_ni_tekst(svet):
    k, b, dokB = svet["k"], svet["b"], svet["dokB"]
    ok_t = k.get(f"/api/predmeti/{PB}/dokumenti/{dokB}/preview", headers=zaglavlje("B"))
    ok_d = k.get(f"/api/predmeti/{PB}/dokumenti/{dokB}/download", headers=zaglavlje("B"))
    assert ok_t.status_code == 200 and "Betakovic" in ok_t.json()["tekst"]                 # pozitivna kontrola
    assert ok_d.status_code == 200 and ok_d.content.startswith(b"%PDF")
    pre = _snimak(b)
    for put in (f"/api/predmeti/{PB}/dokumenti/{dokB}/preview", f"/api/predmeti/{PB}/dokumenti/{dokB}/download"):
        r = k.get(put, headers=zaglavlje("A"))
        assert r.status_code == 404, (put, r.text)
        _bez_b(r)
        assert b"%PDF" not in r.content
    assert _snimak(b) == pre
    assert _audit_o_B(b, svet["b_ids"]) == []                   # ni `dokument_view`/`dokument_download` audit


# ── 5: A izvozi koristeći B-ove ID-jeve ─────────────────────────────────────────────────────────────────────────

def test_05_izvoz_ne_daje_B_podatke(svet, monkeypatch):
    k, b, dokB = svet["k"], svet["b"], svet["dokB"]
    import routers.export as exp
    pdf = []
    monkeypatch.setattr(exp, "_generiši_pdf", lambda *a: pdf.append(a) or b"%PDF-n05")
    assert k.get(f"/api/predmeti/{PB}/pdf-export", headers=zaglavlje("B")).status_code == 200   # pozitivna kontrola
    pdf.clear()
    pre = _snimak(b)
    r = k.get(f"/api/predmeti/{PB}/pdf-export", headers=zaglavlje("A"))
    assert r.status_code == 404, r.text
    _bez_b(r)
    assert pdf == []                                            # B-ov predmet nikad nije stigao do generatora PDF-a
    # Prenosivost: forsirani B-ovi ID-jevi u upitu se ignorišu; izvoz sadrži SAMO A.
    import io
    import zipfile
    z = k.get("/api/export/complete", params={"user_id": "uid-B", "predmet_id": PB, "dok_id": dokB}, headers=zaglavlje("A"))
    assert z.status_code == 200, z.text
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        sadrzaj = "".join(zf.read(n).decode("utf-8") for n in zf.namelist())
    for x in B_TRAGOVI:
        assert x not in sadrzaj, x
    assert dokB not in sadrzaj and "Sastanak A" in sadrzaj
    g = k.get("/api/gdpr/export", params={"user_id": "uid-B"}, headers={**zaglavlje("A"), "X-User-Id": "uid-B"})
    assert g.status_code == 200, g.text
    _bez_b(g)
    assert g.json()["profil"].get("id") == "uid-A" and [p["id"] for p in g.json()["predmeti"]] == [PA]
    assert _snimak(b) == pre and _audit_o_B(b, svet["b_ids"]) == []


# ── 6: A potvrđuje/odbija B-ov rok-kandidat ─────────────────────────────────────────────────────────────────────

def test_06_A_ne_odlucuje_o_B_roku(svet):
    k, b = svet["k"], svet["b"]
    pre = _snimak(b)
    for akcija in ("potvrdi", "odbij"):
        r = k.post(f"/api/rokovi/rok-B-1/{akcija}", json={"napomena": "upad"}, headers=zaglavlje("A"))
        assert r.status_code == 404, r.text
        _bez_b(r)
    assert _snimak(b) == pre
    assert not [x for x in b.tabele["audit_immutable"] if x.get("resource_id") == "rok-B-1"]
    lista = k.get("/api/rokovi/kandidati", params={"od": "2026-10-01", "dana": 120}, headers=zaglavlje("B"))
    assert {x["id"]: x["stanje_odluke"] for x in lista.json()["rokovi"]} == {"rok-B-1": "UNCONFIRMED"}
    # pozitivna kontrola: B sme
    assert k.post("/api/rokovi/rok-B-1/potvrdi", json={}, headers=zaglavlje("B")).status_code == 200


# ── 8: forsirana polja vlasništva (telo/upit/zaglavlja) se ignorišu ─────────────────────────────────────────────

def test_08_forsirana_polja_vlasnistva_se_ignorisu(svet):
    k, b, jB, jA = svet["k"], svet["b"], svet["jB"], svet["jA"]
    lazna = {**zaglavlje("A"), "X-User-Id": "uid-B", "X-Tenant-Id": "uid-B", "X-Kancelarija-Id": "uid-B",
             "X-Forwarded-User": "uid-B"}
    pre = _snimak(b)
    r1 = k.get(f"/api/smart-intake/jobs/{jB}", params={"user_id": "uid-B", "uploaded_by": "uid-B"}, headers=lazna)
    r2 = k.post(f"/api/smart-intake/jobs/{jB}/finalize", headers=lazna,
                json={"predmet_id": PB, "user_id": "uid-B", "uploaded_by": "uid-B", "tenant_id": "uid-B", "owner": "uid-B"})
    r3 = k.post("/api/rokovi/rok-B-1/potvrdi", json={"user_id": "uid-B", "napomena": "x"}, headers=lazna)
    r4 = k.get("/api/rokovi/kandidati", params={"user_id": "uid-B", "predmet_id": PB, "od": "2026-10-01", "dana": 120},
               headers=lazna)
    for r in (r1, r2, r3):
        assert r.status_code == 404, r.text
        _bez_b(r)
    assert r4.status_code == 200 and r4.json()["rokovi"] == []        # filter predmeta B nad A-ovim redovima = prazno
    _bez_b(r4)
    assert _snimak(b) == pre
    # Otpremanje sa forsiranim vlasnikom u formi i zaglavlju: posao pripada pozivaocu (A), ne B.
    u = k.post("/api/smart-intake/documents", headers=lazna, data={"user_id": "uid-B", "uploaded_by": "uid-B"},
               files=[("files", ("forsirano.pdf", _digitalni_pdf(A_LINIJE + ["forsirano"]), "application/pdf"))])
    assert u.status_code == 202, u.text
    novi = _posao(b, u.json()["rezultati"][0]["job_id"])
    assert novi["uploaded_by"] == "uid-A" and novi["storage_path"].startswith("uid-A/")
    assert jA != novi["id"]


# ── 9: nedostupan objekat kroz validan identifikator porekla ────────────────────────────────────────────────────

def test_09_tudji_identifikator_porekla_ne_otvara_nista(svet):
    k, b, dokB, entB = svet["k"], svet["b"], svet["dokB"], svet["entB"]
    pre = _snimak(b)
    # B-ov dokument „kroz” A-ov sopstveni predmet (vlasnik predmeta je A, dokument je B)
    for put in (f"/api/predmeti/{PA}/dokumenti/{dokB}/preview", f"/api/predmeti/{PA}/dokumenti/{dokB}/download"):
        r = k.get(put, headers=zaglavlje("A"))
        assert r.status_code == 404, (put, r.text)
        _bez_b(r)
    # B-ov izvučeni entitet (entitet → dokument prijema → posao → vlasnik B)
    r = k.post(f"/api/smart-intake/entities/{entB}/correct", json={"corrected_value": "UPAD"}, headers=zaglavlje("A"))
    assert r.status_code == 404, r.text
    _bez_b(r)
    assert all(e.get("corrected_value") is None for e in b.tabele["extracted_entities"])
    assert _snimak(b) == pre


# ── 10: ponovljen zahtev / ponovna upotreba ključa idempotencije ne prelazi granicu ─────────────────────────────

def test_10_isti_kljuc_idempotencije_ne_prelazi_granicu(svet):
    k, b, jB = svet["k"], svet["b"], svet["jB"]
    kljuc = str(uuid.uuid4())
    telo = {"predmet_id": PB}
    # B legitimno izvršava i keš sadrži B-ov uspešan odgovor pod ključem K.
    fb = k.post(f"/api/smart-intake/jobs/{jB}/finalize", json=telo, headers={**zaglavlje("B"), "Idempotency-Key": kljuc})
    assert fb.status_code == 200 and fb.json()["predmet_id"] == PB, fb.text
    pre = _snimak(b)
    # A šalje BAJT-U-BAJT isti zahtev sa ISTIM ključem — ne sme dobiti B-ov sačuvan odgovor.
    odgovori = [k.post(f"/api/smart-intake/jobs/{jB}/finalize", json=telo,
                       headers={**zaglavlje("A"), "Idempotency-Key": kljuc}) for _ in range(3)]
    for r in odgovori:
        assert r.status_code == 404, r.text
        _bez_b(r)
    assert odgovori[0].headers.get("idempotent-replayed") is None   # prvi A-ov zahtev je IZVRŠEN, ne vraćen iz keša B
    posle = json.loads(_snimak(b))
    # jedina dozvoljena promena: A-ov sopstveni red idempotencije (vlasnik uid-A); B-ov red netaknut
    pre_d = json.loads(pre)
    assert {t: v for t, v in posle.items() if t != "v2_mutation_idempotency"} == \
           {t: v for t, v in pre_d.items() if t != "v2_mutation_idempotency"}
    b_redovi = lambda d: [x for x in d["v2_mutation_idempotency"] if x["user_id"] == "uid-B"]
    assert b_redovi(posle) == b_redovi(pre_d)
    assert {x["user_id"] for x in posle["v2_mutation_idempotency"] if x["idempotency_key"] == kljuc} <= {"uid-A", "uid-B"}
    # B ponavlja svoj zahtev: dobija SVOJ sačuvan odgovor (ključ nije „potrošen” od A)
    fb2 = k.post(f"/api/smart-intake/jobs/{jB}/finalize", json=telo, headers={**zaglavlje("B"), "Idempotency-Key": kljuc})
    assert fb2.status_code == 200 and fb2.json() == fb.json() and fb2.headers.get("idempotent-replayed") == "true"


def test_10b_ponovljeni_napad_bez_kljuca_nikad_ne_prolazi(svet):
    k, b, jB = svet["k"], svet["b"], svet["jB"]
    pre = _snimak(b)
    for _ in range(5):
        r = k.post(f"/api/smart-intake/jobs/{jB}/finalize", json={"predmet_id": PA}, headers=zaglavlje("A"))
        assert r.status_code == 404, r.text
    assert _snimak(b) == pre and _posao(b, jB).get("finalizing_at") is None


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []


# ── 7: A dobija B-ov privatni AI kontekst ───────────────────────────────────────────────────────────────────────
# (a) Law Brain sinteza — jedini predmetno-vezan poziv modela u V2: tuđ predmet = 404 PRE modela i PRE naplate.

from tests.test_ns008_t12_synthesis import svet as lb_svet  # noqa: E402,F401 — pytest fixture
from tests.test_ns008_t11_api import PA_CUR, PB_CUR  # noqa: E402
import tests.ns008_fake as _f8  # noqa: E402


def test_07a_law_brain_sinteza_tudjeg_predmeta_bez_modela_i_kredita(lb_svet):
    k, b, krediti, pozivi, odgovor = lb_svet
    odgovor["v"] = {"tvrdnje": []}
    pre = json.dumps(b.tabele, sort_keys=True, default=str)
    kljuc = str(uuid.uuid4())
    for h in (_f8.zaglavlje("A"), {**_f8.zaglavlje("A"), "Idempotency-Key": kljuc}, {**_f8.zaglavlje("A"), "X-User-Id": "uid-B"}):
        r = k.post(f"/api/law-brain/predmeti/{PB_CUR}/sinteza", headers=h)
        assert r.status_code == 404, r.text
        assert "B tekući" not in r.text
    assert pozivi == [] and krediti == []
    g = k.get(f"/api/law-brain/predmeti/{PB_CUR}", headers=_f8.zaglavlje("A"))
    assert g.status_code == 404 and "B tekući" not in g.text
    posle = json.loads(json.dumps(b.tabele, sort_keys=True, default=str))
    pre_d = json.loads(pre)
    # dozvoljeno: A-ov sopstveni red idempotencije i A-ov red kredita/profila (provera prava pre tela rute)
    van = ("v2_mutation_idempotency", "user_credits", "profiles")
    assert {t: v for t, v in posle.items() if t not in van} == {t: v for t, v in pre_d.items() if t not in van}
    assert {x.get("user_id") for t in van for x in posle.get(t, []) if x not in pre_d.get(t, [])} <= {"uid-A", None}
    # pozitivna kontrola: A na sopstvenom predmetu stiže do modela
    assert k.post(f"/api/law-brain/predmeti/{PA_CUR}/sinteza", headers=_f8.zaglavlje("A")).status_code == 200
    assert len(pozivi) == 1


# (b) /api/pitanje sa B-ovim predmet_id: B-ov kontekst se NE čita i NE ulazi u prompt.
# Napomena (dizajn, VCR001 T04): pitanje se izvršava kao opšte, bez konteksta, i naplaćuje se A za A-ovo pitanje.

from tests.test_ns005_t6_pravno_pitanje import ok as pitanje_ok, ODGOVOR  # noqa: E402,F401


def test_07b_pitanje_sa_tudjim_predmetom_ne_cita_niti_salje_B_kontekst(pitanje_ok, monkeypatch):
    k, b = pitanje_ok
    b.tabele["predmeti"].append({"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "status": "aktivan"})
    b.tabele["predmet_beleske"].append({"id": "b2", "predmet_id": PB, "user_id": "uid-B",
                                        "sadrzaj": "TAJNA BELESKA B o nagodbi", "created_at": "2026-10-01"})
    import api
    from shared.ai_provenance import _case_ctx
    prompti = []

    async def _pokreni(fn, pitanje_za_agenta, *a, **kw):
        prompti.append((pitanje_za_agenta, (_case_ctx.get() or {}).get("predmet_id")))
        return dict(ODGOVOR)
    monkeypatch.setattr(api, "pokreni", _pokreni)
    b.dnevnik.clear()
    r = k.post("/api/pitanje", json={"pitanje": "Kako dokazati štetu?", "predmet_id": PB,
                                     "user_id": "uid-B"}, headers={**zaglavlje("A"), "X-User-Id": "uid-B"})
    assert r.status_code == 200, r.text
    _bez_b(r)
    assert r.json()["kontekst_predmeta"] is False and r.json()["kontekst_predmeta_stanje"] == "NIJE_PROCITAN"
    assert len(prompti) == 1 and prompti[0][1] is None
    assert "TAJNA BELESKA B" not in prompti[0][0] and "KONTEKST PREDMETA" not in prompti[0][0]
    # B-ove beleške/istorija/činjenice nisu ni pročitane (kapija vlasništva je PRE čitanja konteksta)
    assert not [z for z in b.dnevnik if z["tabela"] in ("predmet_beleske", "predmet_istorija", "predmet_dokazi")]
