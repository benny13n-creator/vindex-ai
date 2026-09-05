# -*- coding: utf-8 -*-
"""
Z015 W1.1 — DOMEN I MATEMATIKA STRANICENJA (izvrseno u Node-u).

Ovi moduli su cisti: bez DOM-a, bez mreze, bez stanja. Zato se mogu izvrsiti
direktno i tvrditi ishod, umesto da se cita izvor i pogadja ponasanje.

Sta se cuva, a sto se iz koda ne vidi:

  1. `ukupno` sa servera je JEDINI izvor broja rezultata. Ako bi neko racunao
     iz duzine strane, brojac bi na 2000 predmeta pisao „50 predmeta" i
     `imaSledecu` bi bilo netacno. `test_ukupno_dolazi_sa_servera` obara to.

  2. Nepoznat enum NE SME osvanuti korisniku kao sirov kljuc iz baze
     (Z015 §19). `test_nepoznat_enum_ne_curi` obara to.

  3. Zapis bez naziva ne sme oboriti ceo registar. `test_zapis_bez_naziva`
     obara to.
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
pytestmark = pytest.mark.skipif(node is None, reason="node nije dostupan")


def _pokreni(telo: str):
    skripta = textwrap.dedent(f"""
        import {{ uZapis, uZapise, uStranu }} from "file:///{V2}/domain/predmeti.js";
        import {{ nazivStanja, klasaStanja, nazivVrste, datum }} from "file:///{V2}/domain/labels.js";
        import {{ napraviStanje, novaGeneracija, jeAktuelna, STANJE }} from "file:///{V2}/features/predmeti/state.js";
        const rezultat = (() => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run(
        [node, "--input-type=module", "-e", skripta],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


# ─── Preslikavanje zapisa ────────────────────────────────────────────────────

def test_summary_red_se_preslikava_u_zapis():
    z = _pokreni("""
        return uZapis({ id: "abc-123", naziv: "Marković protiv DOO Vektor",
                        broj_predmeta: "P-441/25", tip: "parnicni", status: "aktivan",
                        updated_at: "2026-08-31T10:00:00+00:00" });
    """)
    assert z["naziv"] == "Marković protiv DOO Vektor"
    assert z["broj"] == "P-441/25"
    assert z["vrsta"] == "Parnični"
    assert z["stanje"] == "Aktivan"
    assert z["stanjeKlasa"] == "aktivan"
    assert z["izmenjeno"] == "31.08.2026."


def test_nepoznat_enum_ne_curi():
    """
    Sirovi kljuc iz baze se korisniku ne prikazuje ni kada mapa ne zna za njega.

    IZMENJENO U Z017 — I ZASTO. Prvobitna verzija je trazila da nepoznata
    vrednost postane PRAZNA (`vrsta == ""`, `stanje == "—"`). Merenje na
    produkciji je pokazalo sta to znaci u praksi: `predmeti.tip` NIJE
    kontrolisan recnik i nosi radni_spor, Parnica, opsti, ugovorni_spor,
    nasledstvo, naknada_stete, potrosacki_spor, ostalo — od 23 predmeta samo
    1 pogadja negdasnji uzi recnik. Pravilo je, dakle, brisalo STVARAN
    podatak na 22 od 23 predmeta i tvrdilo da predmet vrstu nema.

    Namera pravila (Z015 §19) je bila da advokat ne cita programerski zargon
    („radni_spor"), a ne da izgubi podatak. Zato invarijanta sada glasi:

        SIROV KLJUC (snake_case, sa donjim crtama) SE NIKAD NE PRIKAZUJE,
        ali se nepoznata vrednost CITLJIVO ispisuje umesto da nestane,
        a SEMANTIKA se i dalje ne pogadja — `stanjeKlasa` ostaje „nepoznato",
        pa nepoznato stanje ne dobija boju aktivnog ni zavrsenog predmeta.
    """
    z = _pokreni("""
        return uZapis({ naziv: "X", tip: "neki_novi_tip_iz_baze", status: "neko_novo_stanje" });
    """)
    kao_tekst = json.dumps(z, ensure_ascii=False)
    # Sirov kljuc ne sme na ekran ni u jednom obliku sa donjom crtom.
    assert "neki_novi_tip" not in kao_tekst
    assert "neko_novo_stanje" not in kao_tekst
    assert "_" not in z["vrsta"] and "_" not in z["stanje"]
    # Ali podatak NIJE obrisan.
    assert z["vrsta"] == "Neki novi tip iz baze"
    assert z["stanje"] == "Neko novo stanje"
    # Semantika se i dalje ne pogadja.
    assert z["stanjeKlasa"] == "nepoznato"


def test_prazna_vrednost_i_dalje_daje_crticu():
    """Praznina i nepoznata vrednost su dve razlicite cinjenice."""
    z = _pokreni('return uZapis({ naziv: "X" });')
    assert z["vrsta"] == ""
    assert z["stanje"] == "—"
    assert z["stanjeKlasa"] == "nepoznato"


def test_zapis_bez_naziva():
    z = _pokreni('return uZapis({ id: "x", naziv: "   " });')
    assert z["naziv"] == "Predmet bez naziva"


def test_neispravan_datum_ne_baca():
    z = _pokreni('return [uZapis({naziv:"a", updated_at:"ne-datum"}), uZapis({naziv:"b"})];')
    assert z[0]["izmenjeno"] == "—"
    assert z[1]["izmenjeno"] == "—"


def test_dug_naziv_se_ne_sece():
    """Registar ne sme skracivati naziv u modelu — prelamanje je stvar CSS-a."""
    dug = "A" * 400
    z = _pokreni(f'return uZapis({{ naziv: "{dug}" }});')
    assert len(z["naziv"]) == 400
    assert "…" not in z["naziv"] and "..." not in z["naziv"]


def test_nedostajuca_lista_ne_obara():
    assert _pokreni("return uZapise(null);") == []
    assert _pokreni("return uZapise(undefined);") == []


# ─── Matematika stranicenja ──────────────────────────────────────────────────

def test_ukupno_dolazi_sa_servera():
    """Duzina strane NIJE broj rezultata."""
    s = _pokreni("""
        const red = { id:"1", naziv:"n" };
        return uStranu({ predmeti: Array(50).fill(red), ukupno: 2000, limit: 50, offset: 0 }, 50, 0);
    """)
    assert s["ukupno"] == 2000
    assert len(s["zapisi"]) == 50
    assert s["prvi"] == 1 and s["poslednji"] == 50
    assert s["imaSledecu"] is True and s["imaPrethodnu"] is False


@pytest.mark.parametrize("ukupno,offset,ocekivano", [
    (20, 0, (1, 20, False, False)),
    (200, 0, (1, 50, True, False)),
    (200, 50, (51, 100, True, True)),
    (200, 150, (151, 200, False, True)),
    (2000, 1950, (1951, 2000, False, True)),
])
def test_polozaj_strane(ukupno, offset, ocekivano):
    prvi, poslednji, ima_s, ima_p = ocekivano
    koliko = min(50, ukupno - offset)
    s = _pokreni(f"""
        const red = {{ id:"1", naziv:"n" }};
        return uStranu({{ predmeti: Array({koliko}).fill(red), ukupno: {ukupno},
                          limit: 50, offset: {offset} }}, 50, {offset});
    """)
    assert (s["prvi"], s["poslednji"], s["imaSledecu"], s["imaPrethodnu"]) == (prvi, poslednji, ima_s, ima_p)


def test_prazan_registar():
    s = _pokreni('return uStranu({ predmeti: [], ukupno: 0, limit: 50, offset: 0 }, 50, 0);')
    assert s["zapisi"] == [] and s["ukupno"] == 0
    assert s["prvi"] == 0 and s["imaSledecu"] is False and s["imaPrethodnu"] is False


def test_server_sme_da_skrati_limit():
    """`/api/predmeti` skracuje limit na [1,500]. Klijent mora usvojiti
    STVARNI limit iz odgovora — inace sledeci offset preskoci zapise."""
    s = _pokreni("""
        const red = { id:"1", naziv:"n" };
        return uStranu({ predmeti: Array(500).fill(red), ukupno: 900, limit: 500, offset: 0 }, 5000, 0);
    """)
    assert s["limit"] == 500
    assert s["poslednji"] == 500


def test_odgovor_bez_polja_ne_obara():
    s = _pokreni("return uStranu({}, 50, 0);")
    assert s["zapisi"] == [] and s["ukupno"] == 0 and s["limit"] == 50


# ─── Odbrana od zastarelog odgovora ──────────────────────────────────────────

def test_nova_generacija_prekida_prethodnu():
    r = _pokreni("""
        const s = napraviStanje(50);
        const a = novaGeneracija(s);
        const prviPrekinut = () => a.signal.aborted;
        const b = novaGeneracija(s);
        return { staraAktuelna: jeAktuelna(s, a.broj),
                 novaAktuelna: jeAktuelna(s, b.broj),
                 staraPrekinuta: prviPrekinut() };
    """)
    assert r["staraAktuelna"] is False
    assert r["novaAktuelna"] is True
    assert r["staraPrekinuta"] is True, "AbortController prethodne generacije nije prekinut"


def test_generacija_raste_monotono():
    r = _pokreni("""
        const s = napraviStanje(50);
        const b = [];
        for (let i = 0; i < 5; i++) b.push(novaGeneracija(s).broj);
        return b;
    """)
    assert r == [1, 2, 3, 4, 5]


# ─── Nazivi ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sirovo,ocekivano", [
    ("aktivan", "Aktivan"), ("AKTIVAN", "Aktivan"), ("u toku", "U toku"),
    ("zavrsen", "Završen"), ("", "—"), (None, "—"),
])
def test_naziv_stanja(sirovo, ocekivano):
    val = "null" if sirovo is None else f'"{sirovo}"'
    assert _pokreni(f"return nazivStanja({val});") == ocekivano


def test_datum_je_srpski_oblik():
    assert _pokreni('return datum("2026-01-05T23:00:00Z");').endswith(".2026.")
    assert _pokreni('return datum(null);') == "—"
