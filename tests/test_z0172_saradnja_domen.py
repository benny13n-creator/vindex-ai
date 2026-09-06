# -*- coding: utf-8 -*-
"""
Z017.2 -- B18 SARADNJA, domen.

B18 je bio pogresno klasifikovan kao "DEFERRED: zavisi od postojanja
kancelarije, vlasnikov nalog vraca no_firma" -- neistina, `routers/saradnja.py`
ne pominje `firma`/`kancelarija` nijednom, i tabela `predmet_saradnici`
POSTOJI u produkcionoj bazi (dokazano read-only probom, 0 redova). Stvarni
razlog je bio: 0 V2 povrsine. Ovi testovi cuvaju domenski sloj te povrsine.

  1. NEPOZNATA/PRAZNA ULOGA se NIKAD ne prikazuje kao jedna od tri stvarne.
     Isti zakon kao `nazivStanja`/`nazivVrste` (Z015 SS19).
     `test_nepoznata_uloga_ne_postaje_jedna_od_tri`.

  2. "VLASNIK" JE JEDINI SIGNAL KOJI OTKLJUCAVA UPRAVLJANJE.
     `citanje`/`saradnja`/`vodenje`/`None` NISU vlasnik.
     `test_samo_vlasnik_je_vlasnik`.

  3. VALIDACIJA EMAILA JE FRONTEND PRVA LINIJA, NE JEDINA.
     Backend i dalje odbija (`_lookup_user_by_email` 404), ovo samo sprecava
     ocigledno neispravan zahtev.
     `test_email_validacija`.
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
        import * as S from "file:///{V2}/domain/saradnja.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


@nodemark
def test_nepoznata_uloga_ne_postaje_jedna_od_tri():
    assert _js('return S.nazivUloge("citanje");') == "Čitanje"
    assert _js('return S.nazivUloge("saradnja");') == "Saradnja"
    assert _js('return S.nazivUloge("vodenje");') == "Vođenje"
    # "SARADNJA" (velika slova) NIJE u ovoj listi -- nazivUloge normalizuje
    # velicinu slova pre poredjenja, isti obrazac kao domain/labels.js
    # normalizuj(); to je namerna blagost prema case-u iz istog fiksnog
    # backend enuma, ne rupa u zakonu "nepoznato ostaje vidljivo drugacije".
    for nepoznato in ("vlasnik", "", None, "obrisano"):
        assert _js(f"return S.nazivUloge({_j(nepoznato)});") == "—", nepoznato


@nodemark
def test_samo_vlasnik_je_vlasnik():
    assert _js('return S.jeVlasnik({ uloga: "vlasnik" });') is True
    for uloga in ("citanje", "saradnja", "vodenje", None, ""):
        assert _js(f'return S.jeVlasnik({{ uloga: {_j(uloga)} }});') is False, uloga


@nodemark
def test_mojauloga_prazno_je_null_ne_prazan_string():
    assert _js('return S.mojaUloga({ uloga: null });') is None
    assert _js('return S.mojaUloga({});') is None
    assert _js('return S.mojaUloga({ uloga: "saradnja" });') == "saradnja"


@nodemark
def test_email_validacija():
    assert _js('return S.validanEmail("kolega@firma.rs");') is True
    for lose in ("", "bez-at-znaka.rs", "@nema-lokalni.rs", "ima@ali nema.tld", "a@b"):
        assert _js(f"return S.validanEmail({_j(lose)});") is False, lose


@nodemark
def test_usaradnika_prazan_email_ostaje_crtica_ne_prazno():
    r = _js('return S.uSaradnika({ saradnik_user_id: "u1", email: "", uloga: "citanje" });')
    assert r["email"] == "—"
    assert r["ulogaNaziv"] == "Čitanje"


@nodemark
def test_usaradnike_prihvata_i_golu_listu_i_omotnicu():
    a = _js('return S.uSaradnike([{ saradnik_user_id:"1", email:"a@b.rs", uloga:"citanje" }]).length;')
    b = _js('return S.uSaradnike({ saradnici: [{ saradnik_user_id:"1", email:"a@b.rs", uloga:"citanje" }] }).length;')
    assert a == 1 and b == 1


@nodemark
def test_uloge_katalog_ima_sve_tri_i_tacnim_redosledom():
    r = _js("return S.ULOGE.map(u => u.kljuc);")
    assert r == ["citanje", "saradnja", "vodenje"]
