# -*- coding: utf-8 -*-
"""
Z017.1 — KLIJENT (domen).

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. POVERLJIVA POLJA SE NE PRIKAZUJU — NI PRAZNA.
     `jmbg`, `broj_pasosa`, `pib` i `maticni_broj` su u bazi sifrovani, a
     `filter_klijent` ih po ulozi uklanja iz odgovora. Prazno polje „JMBG"
     na ekranu tvrdilo bi da klijent JMBG NEMA, a istina je da ga ovaj ekran
     ne sme videti. Zato ne postoje u spisku polja ni kada ih backend posalje.
     `test_poverljiva_polja_nikad_ne_ulaze`.

  2. AKTIVNI I ZAVRSENI PREDMETI SE NE SABIRAJU.
     Aktivan predmet je obaveza, zavrsen je istorija — advokat ih cita
     drugacije. `test_aktivni_i_zavrseni_su_odvojeni`.

  3. PRAVNO I FIZICKO LICE IMAJU RAZLICITE OBAVEZNE PODATKE.
     Backend trazi `ime` (min 2) za oba, pa se za pravno lice tamo salje
     naziv firme — to je ugovor servera. Validacija na klijentu mora da
     gadja polje koje je korisniku VIDLJIVO. `test_pravno_lice_*`.

  4. FIRMA PRETICE LICNO IME U NAZIVU.
     `test_firma_pretice_ime`.
"""
import json
import os
import shutil
import subprocess
import textwrap

import pytest

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V2 = os.path.join(KOREN, "v2").replace("\\", "/")

node = shutil.which("node")
nodemark = pytest.mark.skipif(node is None, reason="node nije dostupan")


def _js(telo: str):
    skripta = textwrap.dedent(f"""
        import * as K from "file:///{V2}/domain/klijent.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


PUN = {
    "id": "k1", "tip": "fizicko_lice", "ime": "Petar", "prezime": "Petrović",
    "email": "petar@primer.rs", "telefon": "0601234567", "adresa": "Knez Mihailova 1",
    "status": "aktivan", "kreirano": "2026-03-01T10:00:00Z",
    # Poverljiva — backend ih moze poslati; ekran ih NE SME prikazati.
    "jmbg": "0101990710011", "pib": "123456789", "broj_pasosa": "A1234567",
    "maticni_broj": "21234567",
}


# ═══════════════════════════════════════════════════════════════════════════
# 1 — poverljiva polja
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_poverljiva_polja_nikad_ne_ulaze():
    polja = _js(f"return K.poljaKlijenta(K.uZaglavlje({_j(PUN)}));")
    imena = " ".join(p["naziv"].lower() for p in polja)
    vrednosti = " ".join(str(p["vrednost"]) for p in polja)
    for zabranjeno in ("jmbg", "pib", "pasoš", "pasos", "matični", "maticni"):
        assert zabranjeno not in imena, imena
    for vrednost in ("0101990710011", "123456789", "A1234567", "21234567"):
        assert vrednost not in vrednosti, vrednosti


@nodemark
def test_zaglavlje_ne_nosi_poverljive_vrednosti():
    z = _js(f"return K.uZaglavlje({_j(PUN)});")
    kao_tekst = json.dumps(z, ensure_ascii=False)
    for vrednost in ("0101990710011", "123456789", "A1234567"):
        assert vrednost not in kao_tekst, kao_tekst


@nodemark
def test_prazno_polje_ne_zauzima_red():
    mrsav = {"id": "k1", "tip": "fizicko_lice", "ime": "Petar"}
    polja = _js(f"return K.poljaKlijenta(K.uZaglavlje({_j(mrsav)}));")
    assert all(p["vrednost"] for p in polja), polja
    assert not any(p["naziv"] == "Email" for p in polja)


# ═══════════════════════════════════════════════════════════════════════════
# 2 — predmeti klijenta
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_aktivni_i_zavrseni_su_odvojeni():
    d = _js(f"""
      const x = K.sastaviKlijenta({_j({
          "klijent": PUN,
          "aktivni_predmeti": [{"id": "p1", "naziv": "Aktivan"}],
          "zavrseni_predmeti": [{"id": "p2", "naziv": "Zavrsen"},
                                {"id": "p3", "naziv": "Drugi zavrsen"}],
      })});
      return {{ aktivni: x.aktivni.map(p=>p.naziv), zavrseni: x.zavrseni.map(p=>p.naziv),
                imaPredmete: x.imaPredmete }};
    """)
    assert d["aktivni"] == ["Aktivan"]
    assert len(d["zavrseni"]) == 2
    assert d["imaPredmete"] is True


@nodemark
def test_klijent_bez_predmeta():
    d = _js(f"return K.sastaviKlijenta({_j({'klijent': PUN})});")
    assert d["aktivni"] == [] and d["zavrseni"] == []
    assert d["imaPredmete"] is False


@nodemark
def test_prazan_odgovor_ne_rusi_domen():
    d = _js("return Object.keys(K.sastaviKlijenta(null));")
    for k in ("zaglavlje", "polja", "aktivni", "zavrseni", "imaPredmete"):
        assert k in d, d


# ═══════════════════════════════════════════════════════════════════════════
# 3 + 4 — naziv i otvaranje novog
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_firma_pretice_ime():
    n = _js('return K.naziv({ firma:"Delta d.o.o.", ime:"Petar", prezime:"Petrović" });')
    assert n == "Delta d.o.o."


@nodemark
def test_fizicko_lice_dobija_ime_prezime():
    assert _js('return K.naziv({ ime:"Petar", prezime:"Petrović" });') == "Petar Petrović"


@nodemark
def test_klijent_bez_imena_ne_ostaje_prazan():
    assert _js('return K.naziv({});').strip() != ""


@nodemark
def test_pravno_lice_salje_firmu_i_kao_ime():
    """Backend trazi `ime` min 2 za obe vrste — to je ugovor servera."""
    telo = _js('return K.uTeloNovog({ tip:"pravno_lice", firma:"Delta d.o.o." });')
    assert telo["tip"] == "pravno_lice"
    assert telo["ime"] == "Delta d.o.o."
    assert telo["firma"] == "Delta d.o.o."
    assert telo["prezime"] == ""


@nodemark
def test_fizicko_lice_ne_salje_firmu():
    telo = _js('return K.uTeloNovog({ tip:"fizicko_lice", ime:"Petar", prezime:"Petrović", firma:"nesto" });')
    assert telo["ime"] == "Petar" and telo["prezime"] == "Petrović"
    assert telo["firma"] == ""


@nodemark
def test_telo_nikad_ne_nosi_poverljivo():
    telo = _js('return Object.keys(K.uTeloNovog({ tip:"fizicko_lice", ime:"Petar" }));')
    for zabranjeno in ("jmbg", "pib", "broj_pasosa", "maticni_broj"):
        assert zabranjeno not in telo, telo


@nodemark
def test_pravno_lice_trazi_firmu_ne_ime():
    g = _js('return K.nedostaci({ tip:"pravno_lice", ime:"Petar", firma:"" });')
    assert len(g) == 1
    assert "firme" in g[0].lower(), g


@nodemark
def test_fizicko_lice_trazi_ime_ne_firmu():
    g = _js('return K.nedostaci({ tip:"fizicko_lice", ime:"", firma:"Delta d.o.o." });')
    assert len(g) == 1
    assert "ime" in g[0].lower(), g


@nodemark
def test_ispravan_unos_nema_nedostataka():
    assert _js('return K.nedostaci({ tip:"fizicko_lice", ime:"Petar" });') == []
    assert _js('return K.nedostaci({ tip:"pravno_lice", firma:"Delta" });') == []


@nodemark
def test_jedan_znak_nije_dovoljan():
    """Backend trazi min 2 — klijent postuje istu granicu, ne svoju."""
    assert len(_js('return K.nedostaci({ tip:"fizicko_lice", ime:"P" });')) == 1


@nodemark
def test_vrsta_i_stanje_se_citljivo_ispisuju():
    z = _js('return K.uZaglavlje({ tip:"pravno_lice", status:"aktivan" });')
    assert z["vrsta"] == "Pravno lice"
    assert "_" not in z["vrsta"]


@nodemark
def test_zastita_poverljivih_polja_je_DOHVATLJIVA():
    """
    Mutaciono merenje je pokazalo da je zastita bila nedohvatljiva: spisak
    polja je fiksan i nijedan poverljiv kljuc u njega ne dolazi, pa je
    uklanjanje filtera prolazilo neprimeceno. Zastita koju test ne moze da
    dosegne nije zastita nego komentar. Ovaj test je zove direktno.
    """
    r = _js("""return {
      jmbg:      K.smePrikazati("jmbg"),
      pib:       K.smePrikazati("pib"),
      pasos:     K.smePrikazati("broj_pasosa"),
      maticni:   K.smePrikazati("maticni_broj"),
      poNazivu:  K.smePrikazati("nesto_novo", "JMBG klijenta"),
      poNazivu2: K.smePrikazati("x", "PIB"),
      email:     K.smePrikazati("email", "Email"),
      adresa:    K.smePrikazati("adresa", "Adresa"),
    };""")
    for zabranjeno in ("jmbg", "pib", "pasos", "maticni", "poNazivu", "poNazivu2"):
        assert r[zabranjeno] is False, (zabranjeno, r)
    assert r["email"] is True and r["adresa"] is True


@nodemark
def test_poverljivo_polje_bi_bilo_izbaceno_i_da_udje_u_spisak():
    """Dokaz da filter stvarno radi nad spiskom, ne samo nad kljucem."""
    r = _js("""
      const polja = [{ kljuc:"email", naziv:"Email", vrednost:"a@b.rs" },
                     { kljuc:"pib", naziv:"PIB", vrednost:"123456789" },
                     { kljuc:"x", naziv:"JMBG", vrednost:"0101990710011" }];
      return polja.filter(p => K.smePrikazati(p.kljuc, p.naziv)).map(p => p.naziv);
    """)
    assert r == ["Email"], r


@nodemark
def test_polja_su_ALLOW_LISTA_a_ne_deny_lista():
    """
    PRVI sloj zastite je to sto `poljaKlijenta` emituje SAMO imenovana polja —
    allow-lista. `smePrikazati` je DRUGI sloj.

    Zato mutacija koja ukloni drugi sloj i dalje ne propusta poverljiv podatak:
    to je ono sto odbrana u dubinu i znaci. Ovaj test cuva PRVI sloj — da se
    spisak ne prosiri necim sto nije predvidjeno, ma sta backend poslao.
    """
    napadnut = {
        "id": "k1", "tip": "fizicko_lice", "ime": "Petar", "email": "a@b.rs",
        "jmbg": "0101990710011", "pib": "123456789", "broj_pasosa": "A1",
        "maticni_broj": "21234567", "lozinka": "tajna", "interni_id": "X-9",
        "napomena_interna": "ne prikazuj", "user_id": "u-1",
    }
    kljucevi = _js(f"return K.poljaKlijenta(K.uZaglavlje({_j(napadnut)})).map(p => p.kljuc);")
    DOZVOLJENI = {"vrsta", "email", "telefon", "adresa", "upisan"}
    assert set(kljucevi) <= DOZVOLJENI, kljucevi


@nodemark
def test_zaglavlje_ne_prenosi_nepredvidjena_polja():
    """Ni zaglavlje ne sme da postane prolaz za sve sto backend posalje."""
    napadnut = {"ime": "Petar", "lozinka": "tajna", "user_id": "u-1", "jmbg": "0101990710011"}
    z = _js(f"return Object.keys(K.uZaglavlje({_j(napadnut)}));")
    for zabranjeno in ("lozinka", "user_id", "jmbg"):
        assert zabranjeno not in z, z


@nodemark
def test_predmet_klijenta_dolazi_UGNEZDJEN():
    """
    `/klijenti/{id}` vraca red veze `predmet_klijenti` sa UGNEZDJENIM
    predmetom, ne ravan predmet:

        { predmet_id, uloga_klijenta, predmeti: { id, naziv, status, tip } }

    Mereno uzivo: citanje `naziv` sa gornjeg nivoa davalo je „Predmet bez
    naziva" za svaki predmet klijenta, a veza je vodila nikuda jer je `id`
    bio prazan.
    """
    p = _js("""return K.uPredmet({
      predmet_id: "p-1", uloga_klijenta: "stranka",
      predmeti: { id: "p-1", naziv: "Marković protiv Delte", tip: "radni_spor" } });""")
    assert p["naziv"] == "Marković protiv Delte"
    assert p["id"] == "p-1"
    assert p["vrsta"] == "Radni spor"
    assert p["uloga"] == "stranka"


@nodemark
def test_ravan_oblik_predmeta_i_dalje_radi():
    """Drugi pozivalac (pretraga) salje ravan oblik — ne sme se pokvariti."""
    p = _js('return K.uPredmet({ id:"p-2", naziv:"Ravan predmet", tip:"parnica" });')
    assert p["id"] == "p-2" and p["naziv"] == "Ravan predmet"


@nodemark
def test_veza_bez_predmeta_ne_dobija_lazan_id():
    p = _js('return K.uPredmet({ predmet_id:"p-3", predmeti: null });')
    assert p["id"] == "p-3"
    assert p["naziv"] == "Predmet bez naziva"
