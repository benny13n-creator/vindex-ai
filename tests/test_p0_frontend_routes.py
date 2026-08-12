# -*- coding: utf-8 -*-
"""
P0-5 — SVAKI `fetch` IZ FRONTENDA MORA DA POGAĐA REGISTROVANU RUTU.

ŠTA JE BILO

`static/vindex.js` je zvao `POST /api/evidence-graph/generi%C5%A1i`, a backend
sluša `/generisi` (`routers/evidence_graph.py:178`). Zahtev je padao na
`GET /{predmet_id}` i vraćao **405**. Oba dugmeta za graf dokaza — „Generisi
graf" i „↺ Regenerisi" — bila su mrtva.

ZAŠTO SE PONOVILO I ZAŠTO OVDE STOJI TEST KLASE, A NE JEDNOG SLUČAJA

Od 618 registrovanih ruta, tačno JEDNA sadrži naše slovo:
`/api/ugovor-zastupanja/generiši` (`routers/ugovor_zastupanja.py:283`). Dva
susedna modula donela su suprotnu odluku o dijakritici u putanji. Frontend je
oba pozvao istim oblikom (`generi%C5%A1i`) i tačno jedan promašio.

Postojeći test `test_gamma_evidence_check_wiring.py:32` gađa ispravan ASCII put
i prolazi — dokazuje da backend ruta postoji i **nikad ne pita da li je frontend
zove**. To je isti razred greške koji je ovaj sprint našao tri puta: test meri
jednu stranu ugovora između slojeva.

Zato se ovde ne proverava jedna putanja. Iz `vindex.js` se vade SVE `fetch`
putanje i porede sa stvarnim tabelama ruta FastAPI aplikacije.
"""
import os
import re

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_JS = os.path.join(_KOREN, "static", "vindex.js")


def _js() -> str:
    return open(_JS, encoding="utf-8").read()


@pytest.fixture(scope="module")
def rute():
    """Stvarna tabela ruta, iz aplikacije — ne iz `grep`-a po dekoratorima."""
    import api
    izvucene = set()
    for r in api.app.routes:
        put = getattr(r, "path", None)
        if put:
            izvucene.add(put)
    assert len(izvucene) > 300, f"učitano samo {len(izvucene)} ruta — app nije podignut"
    return izvucene


def _u_obrazac(put: str) -> str:
    """`/api/predmeti/{id}/upload` → regex koji pogađa konkretan poziv."""
    delovi = re.split(r"\{[^}]+\}", put)
    return "^" + r"[^/]+".join(re.escape(d) for d in delovi) + "$"


@pytest.fixture(scope="module")
def obrasci(rute):
    return [(p, re.compile(_u_obrazac(p))) for p in rute]


def _putanje_iz_js():
    """Vadi samo NEPROMENLJIVE putanje — one koje test može da presudi.

    Dinamički sastavljeni URL-ovi (`'/api/x/' + id`) se ovde namerno preskaču:
    o njima ovaj test ne može da tvrdi ništa, a lažan nalaz je gori od
    izostavljenog. Uzima se deo do prve konkatenacije.
    """
    from urllib.parse import unquote

    js = _js()
    nadjene = {}
    for m in re.finditer(r"fetch\(\s*(?:BASE_URL\s*\+\s*)?['\"](/api/[^'\"]*)['\"]", js):
        # Ako iza niske sledi `+`, putanja se tek sastavlja — literal je samo
        # njen prefiks (`'/api/zadaci/' + id`). Prva verzija ovog testa je te
        # prefikse prijavila kao 47 nepostojećih ruta; sve su bile lažne.
        ostatak = js[m.end():m.end() + 40].lstrip()
        if ostatak.startswith("+"):
            continue
        # `%C5%A1` u izvoru i `š` u tabeli ruta su ISTA putanja. Poređenje mora
        # da bude nad dekodiranim oblikom, inače test prijavljuje razliku
        # kodiranja kao nepostojeću rutu.
        put = unquote(m.group(1).split("?")[0])
        red = js[: m.start()].count("\n") + 1
        nadjene.setdefault(put, red)
    return nadjene


def test_pronadjeno_je_dovoljno_poziva_da_test_ima_smisla():
    """Negativna kontrola nad samim merenjem.

    Ako se obrazac za vađenje pokvari, ostali testovi bi „prošli" nad praznim
    skupom. Ovo je jedini razlog zbog kog ovaj test postoji.
    """
    nadjene = _putanje_iz_js()
    assert len(nadjene) >= 40, (
        f"iz vindex.js izvučeno samo {len(nadjene)} nepromenljivih `fetch` "
        f"putanja — obrazac za vađenje je pokvaren, ostali testovi ne mere ništa"
    )


def test_svaka_nepromenljiva_fetch_putanja_postoji_na_backendu(obrasci):
    """SRŽ. Kvar iz P0-5 bi ovde pao istog dana."""
    promaseni = []
    for put, red in sorted(_putanje_iz_js().items()):
        if not any(rx.match(put) for _, rx in obrasci):
            promaseni.append(f"vindex.js:{red} → {put}")
    assert not promaseni, (
        "frontend zove putanje koje ne postoje ni u jednoj registrovanoj ruti:\n  "
        + "\n  ".join(promaseni)
    )


def test_nijedna_fetch_putanja_nije_procentno_kodirana(rute):
    """Uža, jeftinija brava nad tačnim obrascem koji je napravio kvar.

    `%C5%A1` u putanji znači da je neko kodirao `š`. To radi samo ako i backend
    ruta sadrži `š` — a takva je tačno jedna od 618. Svaka nova takva putanja
    je skoro sigurno greška, pa mora da bude izričito potvrđena ovde.
    """
    js = _js()
    dozvoljene = {"/api/ugovor-zastupanja/generi%C5%A1i"}

    # Potvrda da izuzetak nije izmišljen: ta ruta STVARNO postoji sa `š`.
    assert "/api/ugovor-zastupanja/generiši" in rute, (
        "izuzetak u `dozvoljene` više ne odgovara stvarnoj tabeli ruta — "
        "ukloniti ga umesto da se test drži zastarelog zapisa"
    )

    nadjene = []
    for m in re.finditer(r"fetch\(\s*(?:BASE_URL\s*\+\s*)?['\"](/api/[^'\"]*%[0-9A-Fa-f]{2}[^'\"]*)['\"]", js):
        put = m.group(1)
        if put in dozvoljene:
            continue
        nadjene.append(f"vindex.js:{js[: m.start()].count(chr(10)) + 1} → {put}")

    assert not nadjene, (
        "procentno kodirana putanja u `fetch` pozivu — skoro sigurno je "
        "backend ruta ASCII, pa ovo pada na drugu rutu ili na 404:\n  "
        + "\n  ".join(nadjene)
    )


def test_evidence_graph_dugmad_gadjaju_pravu_rutu(rute):
    """Imenovana provera baš za nalaz koji je otvorio ovaj P0.

    Opšti test iznad bi ga uhvatio, ali imenovana provera ostavlja trag zašto
    je uvedena — i pada sa porukom koja objašnjava, a ne samo prijavljuje.
    """
    js = _js()
    assert "/api/evidence-graph/generisi" in js, (
        "poziv za generisanje grafa dokaza više ne gađa `/generisi`"
    )
    assert "/api/evidence-graph/generi%C5%A1i" not in js, (
        "vraćena je putanja sa kodiranim `š` — backend sluša `/generisi` "
        "(routers/evidence_graph.py:178), pa ovo pada na `GET /{predmet_id}` → 405"
    )
    assert "/api/evidence-graph/generisi" in rute, (
        "backend ruta `/api/evidence-graph/generisi` više ne postoji — "
        "ovog puta se pomerila druga strana ugovora"
    )
