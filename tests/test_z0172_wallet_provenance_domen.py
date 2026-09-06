# -*- coding: utf-8 -*-
"""
Z017.2 -- G7 WALLET PROVENANCE, domen.

G7 je bio DEFERRED("isti blokator kao G1-G5") -- neistina. Backend
(routers/wallet_provenance.py) je DETERMINISTICKI (stvarni Etherscan
podaci + OFAC SDN provera), NE GPT interpretacija -- ne deli G1-G5-ov
provenance problem uopste. 0 V2 povrsine je bio jedini razlog odsustva.

  1. SANKCIONISAN=null (nepoznato) SE NE MESA SA sankcionisan=false
     (aktivno provereno, nema poklapanja). `test_sankcionisan_null_nije_false`.

  2. VALIDACIJA ETH ADRESE PRATI BACKEND FORMAT (0x + 40 hex).
     `test_validna_eth_adresa`.
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
        import * as W from "file:///{V2}/domain/walletProvenance.js";
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
def test_sankcionisan_null_nije_false():
    nepoznato = _js('return W.uWalletProvenance({}).sankcionisan;')
    provereno_cist = _js('return W.uWalletProvenance({ novcanik_sankcionisan: false }).sankcionisan;')
    provereno_pogodak = _js('return W.uWalletProvenance({ novcanik_sankcionisan: true }).sankcionisan;')
    assert nepoznato is None
    assert provereno_cist is False
    assert provereno_pogodak is True
    assert nepoznato is not provereno_cist  # None i False se ne smeju stopiti


@nodemark
def test_validna_eth_adresa():
    assert _js('return W.validnaEthAdresa("0x" + "a".repeat(40));') is True
    for lose in ("", "0x123", "a" * 42, "0x" + "g" * 40, "0x" + "a" * 39):
        assert _js(f"return W.validnaEthAdresa({_j(lose)});") is False, lose


@nodemark
def test_nalazi_citaju_stvaran_sadrzaj():
    r = _js(
        'return W.uWalletProvenance({ nalazi: { sankcioni: ['
        '{ tip:"direktan_pogodak", confidence:"visoka", opis:"Adresa je na listi." }'
        '], analiticki: [], nedostatak_podataka: [] } }).sankcioni;'
    )
    assert len(r) == 1
    assert r[0]["opis"] == "Adresa je na listi."
    assert r[0]["poverenje"] == "visoka"


@nodemark
def test_ogranicenja_analize_se_prenose_ne_izmisljaju():
    r = _js('return W.uWalletProvenance({ ogranicenja_analize: ["Samo Ethereum.", "Samo 1-hop."] }).ogranicenja;')
    assert r == ["Samo Ethereum.", "Samo 1-hop."]
