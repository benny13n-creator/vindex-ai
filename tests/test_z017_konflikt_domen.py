# -*- coding: utf-8 -*-
"""
Z017.1 — SUKOB INTERESA (domen), owner-locked product invariant.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. `status` I `provera_potpuna` SE NE SMEJU SPOJITI.
     Backend vraca oba odvojeno. Kombinacija koja je opasna je
     `status="clear"` uz `provera_potpuna=false`: pretraga NIJE uspela, a
     doslovno citanje `status`-a bi dalo „Mozete prihvatiti klijenta".
     Tacno to je vec jednom bio BETA blocker (`657818a5`): COI je „uspesno
     pretrazivao prazno". `test_clear_uz_nepotpunu_proveru_NIJE_cisto`.

  2. ODSUTAN ODGOVOR NIJE CIST ODGOVOR.
     Pad poziva, prekid, nepoznat oblik -> „nije provereno", nikad „cisto".
     `test_pad_poziva_nije_cisto`, `test_neocekivan_oblik_nije_cisto`.

  3. BLOKIRAJUCI NALAZ SE NE MOZE POTVRDITI.
     `NASTAVAK.BLOKIRANO` nema put dalje. Nalaz koji trazi pregled ima, ali
     samo kroz izricitu ljudsku radnju. `test_konflikt_je_blokirajuci`.

  4. NAJSTROZIJI ISHOD POBEDJUJE.
     Provera se radi nad vise stranaka. Cist nalaz nad tuziocem ne sme da
     nadglasa blokirajuci nalaz nad tuzenim. `test_spoji_bira_najstroziji`.

  5. `provera_potpuna` MORA BITI IZRICITO `true`.
     Odsutno polje (stariji ili izmenjen backend) tretira se kao nepotpuno —
     fail-closed. `test_odsutna_potvrda_potpunosti_je_nepotpuna`.

  6. SISTEM PODUDARANJA SE NE DIRA.
     Ovaj modul ne racuna slicnost i ne prikazuje skor. Kanonski matching
     zivi u backendu. `test_domen_ne_prikazuje_skor`.
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
        import * as K from "file:///{V2}/domain/konflikt.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


def _ishod(odgovor):
    return _js(f"const r = K.uIshod({_j(odgovor)}); return {{ ishod: r.ishod, "
               f"nastavak: r.nastavak, naslov: r.naslov, telo: r.telo, "
               f"konflikata: r.konflikti.length }};")


CIST = {"status": "clear", "provera_potpuna": True, "konflikti": []}


# ═══════════════════════════════════════════════════════════════════════════
# 1 + 5 — status i potpunost se ne spajaju
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_clear_uz_potpunu_proveru_je_cisto():
    r = _ishod(CIST)
    assert r["ishod"] == "cisto"
    assert r["nastavak"] == "slobodno"


@nodemark
def test_clear_uz_nepotpunu_proveru_NIJE_cisto():
    """Ovo je cela poenta modula: `status` sam po sebi nije dokaz."""
    r = _ishod({"status": "clear", "provera_potpuna": False, "konflikti": [],
                "slojevi_greska": ["predmeti", "klijenti"]})
    assert r["ishod"] == "nepotpuna"
    assert r["nastavak"] == "uz_potvrdu"
    assert "predmeti" in r["telo"] and "klijenti" in r["telo"], r["telo"]
    assert "NE znači da konflikta nema" in r["telo"]


@nodemark
def test_odsutna_potvrda_potpunosti_je_nepotpuna():
    """Odsutno polje != `true`. Stariji backend ne sme tiho da prodje kao cist."""
    r = _ishod({"status": "clear", "konflikti": []})
    assert r["ishod"] == "nepotpuna"


@nodemark
def test_provera_potpuna_mora_biti_bas_true():
    for lazno in ("true", 1, "da"):
        r = _ishod({"status": "clear", "provera_potpuna": lazno, "konflikti": []})
        assert r["ishod"] == "nepotpuna", lazno


# ═══════════════════════════════════════════════════════════════════════════
# 2 — odsutan odgovor
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_pad_poziva_nije_cisto():
    r = _ishod(None)
    assert r["ishod"] == "nepotpuna"
    assert r["nastavak"] == "uz_potvrdu"
    assert "nije izvršena" in r["naslov"]


@nodemark
def test_neocekivan_oblik_nije_cisto():
    r = _ishod({"nesto": "drugo"})
    assert r["ishod"] == "nepotpuna"


# ═══════════════════════════════════════════════════════════════════════════
# 3 — blokada
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_konflikt_je_blokirajuci():
    r = _ishod({"status": "conflict", "provera_potpuna": True,
                "konflikti": [{"naziv": "Delta d.o.o.", "aktivan": True, "severitet": "visok"}]})
    assert r["ishod"] == "konflikt"
    assert r["nastavak"] == "blokirano"
    assert r["konflikata"] == 1


@nodemark
def test_konflikt_blokira_i_kad_je_provera_nepotpuna():
    """Nepotpunost ne sme da OLAKSA ishod — blokada ostaje blokada."""
    r = _ishod({"status": "conflict", "provera_potpuna": False,
                "konflikti": [{"naziv": "X", "aktivan": True}]})
    assert r["nastavak"] == "blokirano"


@nodemark
def test_review_trazi_izricitu_potvrdu():
    r = _ishod({"status": "review", "provera_potpuna": True,
                "konflikti": [{"naziv": "Bivsi klijent", "aktivan": False}]})
    assert r["ishod"] == "pregled"
    assert r["nastavak"] == "uz_potvrdu"


@nodemark
def test_konflikti_bez_statusa_i_dalje_traze_paznju():
    """Ako backend vrati nalaze a status izostane, tok se ne pusta slobodno."""
    r = _ishod({"provera_potpuna": True, "konflikti": [{"naziv": "X"}]})
    assert r["nastavak"] != "slobodno"


# ═══════════════════════════════════════════════════════════════════════════
# 4 — spajanje po strankama
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_spoji_bira_najstroziji():
    r = _js(f"""
      const a = K.uIshod({_j(CIST)});
      const b = K.uIshod({_j({"status": "conflict", "provera_potpuna": True,
                              "konflikti": [{"naziv": "X", "aktivan": True}]})});
      const s = K.spoji([a, b]);
      return {{ nastavak: s.nastavak, ishod: s.ishod }};
    """)
    assert r["nastavak"] == "blokirano"


@nodemark
def test_spoji_cuva_nepotpunost_ispred_cistog():
    r = _js(f"""
      const a = K.uIshod({_j(CIST)});
      const b = K.uIshod({_j({"status": "clear", "konflikti": []})});
      return K.spoji([a, b]).nastavak;
    """)
    assert r == "uz_potvrdu"


@nodemark
def test_spoji_praznog_niza_nije_cisto():
    assert _js("return K.spoji([]).nastavak;") == "uz_potvrdu"


@nodemark
def test_spoji_sabira_nalaze_svih_stranaka():
    r = _js(f"""
      const a = K.uIshod({_j({"status": "review", "provera_potpuna": True,
                              "konflikti": [{"naziv": "A"}]})});
      const b = K.uIshod({_j({"status": "review", "provera_potpuna": True,
                              "konflikti": [{"naziv": "B"}]})});
      return K.spoji([a, b]).konflikti.map(k => k.naziv);
    """)
    assert sorted(r) == ["A", "B"]


# ═══════════════════════════════════════════════════════════════════════════
# 6 — granice prikaza
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_domen_ne_prikazuje_skor():
    k = _js('return Object.keys(K.uKonflikt({ naziv:"X", severitet:"visok", score: 93 }));')
    assert "score" not in k
    assert not any("skor" in x.lower() for x in k), k


@nodemark
def test_emodzi_iz_backend_poruke_ne_stize_na_ekran():
    """Kanon zabranjuje 🚨⚠️🔍; backend ih salje u `poruka`, mi je ne koristimo."""
    r = _js(f"""
      const x = K.uIshod({{ status:"conflict", provera_potpuna:true,
        poruka:"🚨 OZBILJAN KONFLIKT: 2 konflikta!",
        konflikti:[{{ naziv:"🚨 Delta d.o.o.", aktivan:true }}] }});
      return x.naslov + " " + x.telo + " " + x.konflikti.map(k => k.naziv).join(" ");
    """)
    # Provera mora obuhvatiti i NAZIVE KONFLIKATA — oni dolaze sa servera i
    # bas oni nose emodzi. Bez toga test prolazi i kad ciscenje nestane.
    for znak in ("🚨", "⚠️", "🔍"):
        assert znak not in r, r
    assert "Delta d.o.o." in r


@nodemark
def test_prazan_upit_se_ne_salje_serveru():
    """
    Backend na prazan zahtev vraca `clear` — tacno, ali bi na ekranu znacilo
    „provereno, cisto" za proveru koja se nikad nije desila. Zato se odluka
    donosi PRE poziva.
    """
    r = _js("""return [ K.imaStaDaSeProveri({}),
                        K.imaStaDaSeProveri({ ime_prezime: "   " }),
                        K.imaStaDaSeProveri({ ime_prezime: "Petar" }),
                        K.imaStaDaSeProveri({ firma: "Delta d.o.o." }) ];""")
    assert r == [False, False, True, True]


@nodemark
def test_upit_se_gradi_iz_obe_stranke():
    r = _js('return K.upitIzStranaka({ tuzilac:"Petar Petrović", tuzeni:"Delta d.o.o." })'
            '.map(x => x.uloga + ":" + x.ime_prezime);')
    assert r == ["tužilac:Petar Petrović", "tuženi:Delta d.o.o."]


@nodemark
def test_prazna_stranka_ne_pravi_upit():
    r = _js('return K.upitIzStranaka({ tuzilac:"Petar", tuzeni:"" }).length;')
    assert r == 1
