# -*- coding: utf-8 -*-
"""
Z017 — DOSIJE PREDMETA (domen).

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. PRAZNO POLJE SE NE PRIKAZUJE.
     Prazan red u zaglavlju je tvrdnja „ovaj podatak postoji i nije popunjen".
     Za predmet nastao iz dokumenta to cesto nije istina — podatak ni ne
     pripada toj vrsti predmeta. `test_prazna_polja_ne_ulaze_u_zaglavlje`.

  2. INTERNI IDENTIFIKATORI NISU PODATAK ZA ADVOKATA.
     UUID predmeta se koristi za rutu, nikad kao prikazano polje.
     `test_uuid_nikad_nije_prikazano_polje`.

  3. ROK U DOSIJEU POSTUJE ISTI UGOVOR KAO DANAS (fail-closed).
     Neizjavljen red je dogadjaj hronologije, ali NIJE rok; kandidat nikad ne
     stoji medju obavezama; razresen rok ne ulazi ni u jednu aktivnu listu.
     Da Dosije ima sopstvena pravila, isti rok bi u dva ekrana imao dva
     razlicita pravna statusa. `test_*_rok_*`.

  4. „PREUZMI ORIGINAL" SE NUDI SAMO KAD ORIGINAL POSTOJI.
     Spis bez `storage_path` je zapis o dokumentu, ne dokument. Ponudjeno pa
     palo preuzimanje je gore od izostanka ponude. `test_spis_bez_originala`.

  5. KLIJENT NIJE STRANKA.
     `klijenti_linked` je poslovni odnos kancelarije; `tuzilac`/`tuzeni` su
     procesne uloge. Spajanje ta dva pojma je tacno ono sto je COI audit vec
     jednom platio. `test_klijent_i_stranka_su_odvojeni`.

  6. OCENA SPREMNOSTI SE NE PRIKAZUJE KAO BROJ.
     Broj bez objasnjenja je kanonom zabranjen KPI. Razlozi jesu upotrebljivi.
     `test_spremnost_ne_izlaze_broj`.
"""
import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V2 = os.path.join(KOREN, "v2").replace("\\", "/")
sys.path.insert(0, KOREN)

node = shutil.which("node")
nodemark = pytest.mark.skipif(node is None, reason="node nije dostupan")


def _js(telo: str):
    skripta = textwrap.dedent(f"""
        import * as O from "file:///{V2}/domain/dosije.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


PREDMET = {
    "id": "11111111-2222-3333-4444-555555555555",
    "naziv": "Marković protiv Delta osiguranja",
    "broj_predmeta": "P 1234/25",
    "tip": "radni_spor",
    "status": "aktivan",
    "tuzilac": "Marković Petar",
    "tuzeni": "Delta osiguranje a.d.o.",
    "vrednost_spora": 850000,
    "created_at": "2026-03-14T10:00:00Z",
}


# ═══════════════════════════════════════════════════════════════════════════
# 1 + 2 — zaglavlje
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_prazna_polja_ne_ulaze_u_zaglavlje():
    mrsav = {"id": "x", "naziv": "Predmet iz dokumenta", "status": "aktivan"}
    polja = _js(f"return O.poljaZaglavlja(O.uZaglavlje({_j(mrsav)}));")
    imena = [p["naziv"] for p in polja]
    assert "Tužilac" not in imena
    assert "Tuženi" not in imena
    assert "Broj predmeta" not in imena
    assert "Vrednost spora" not in imena
    assert all(p["vrednost"] for p in polja), polja


@nodemark
def test_puna_polja_ulaze_redom():
    polja = _js(f"return O.poljaZaglavlja(O.uZaglavlje({_j(PREDMET)}));")
    imena = [p["naziv"] for p in polja]
    assert imena == ["Broj predmeta", "Vrsta", "Tužilac", "Tuženi",
                     "Vrednost spora", "Otvoren"], imena
    assert dict((p["naziv"], p["vrednost"]) for p in polja)["Vrsta"] == "Radni spor"


@nodemark
def test_stvarna_vrsta_predmeta_se_ne_brise():
    """
    `predmeti.tip` nije kontrolisan recnik. Mereno na produkciji: od 23
    predmeta samo 1 pogadja negdasnji uzi recnik (`ostalo`). Da nepoznata
    vrednost ostane prazna, 22 od 23 predmeta bi u registru i Dosijeu imala
    prazno polje „Vrsta" — brisanje stvarnog podatka, ne opreznost.
    """
    stvarne = ["radni_spor", "Parnica", "opsti", "ugovorni_spor",
               "nasledstvo", "naknada_stete", "potrosacki_spor", "ostalo"]
    r = _js(f"""
      const L = await import("file:///{V2}/domain/labels.js");
      return {_j(stvarne)}.map(t => L.nazivVrste(t));
    """)
    assert all(x.strip() for x in r), dict(zip(stvarne, r))
    assert "_" not in " ".join(r), r
    assert r[0] == "Radni spor" and r[2] == "Opšti"


@nodemark
def test_vrsta_van_recnika_se_i_dalje_cita():
    """
    Recnik pokriva danasnje vrednosti; sutrasnju ne moze. Vrsta koje u recniku
    NEMA mora ostati citljiva, inace se ista greska vraca cim neko unese nov
    tip predmeta. Ovaj test namerno bira vrednosti kojih u `VRSTA` nema.
    """
    nepoznate = ["stecajni_postupak", "izvrsenje na nepokretnosti", "MEDIJACIJA"]
    r = _js(f"""
      const L = await import("file:///{V2}/domain/labels.js");
      return {_j(nepoznate)}.map(t => L.nazivVrste(t));
    """)
    assert r[0] == "Stecajni postupak", r
    assert r[1] == "Izvrsenje na nepokretnosti", r
    assert r[2] == "MEDIJACIJA", r
    assert "_" not in " ".join(r), r


@nodemark
def test_nepoznato_stanje_se_ispisuje_ali_ne_dobija_boju():
    """Rec se prikazuje (podatak postoji), semantika se ne pogadja."""
    r = _js(f"""
      const L = await import("file:///{V2}/domain/labels.js");
      return {{ naziv: L.nazivStanja("u_arhivi"), klasa: L.klasaStanja("u_arhivi"),
                prazno: L.nazivStanja("") }};
    """)
    assert r["naziv"] == "U arhivi"
    assert r["klasa"] == "nepoznato"
    assert r["prazno"] == "—"


@nodemark
def test_uuid_nikad_nije_prikazano_polje():
    polja = _js(f"return O.poljaZaglavlja(O.uZaglavlje({_j(PREDMET)}));")
    spojeno = " ".join(str(p["vrednost"]) for p in polja)
    assert PREDMET["id"] not in spojeno
    assert not any(p["naziv"].lower().startswith("id") for p in polja)


@nodemark
def test_predmet_bez_naziva_ne_ostaje_prazan():
    z = _js('return O.uZaglavlje({ id:"x" });')
    assert z["naziv"].strip() != ""


@nodemark
def test_iznos_odbija_nulu_i_smece():
    r = _js("""return [O.iznos(0), O.iznos(-5), O.iznos(null),
                       O.iznos("abc"), O.iznos(850000).length > 0];""")
    assert r[:4] == ["", "", "", ""]
    assert r[4] is True


# ═══════════════════════════════════════════════════════════════════════════
# 3 — rokovi: isti ugovor kao Danas
# ═══════════════════════════════════════════════════════════════════════════

def _rokovi(redovi):
    return _js(f"""
      const sada = new Date(2026, 8, 5);
      const r = O.uRokove({_j(redovi)}, sada);
      return {{ obaveze: r.obaveze.length, zaProveru: r.zaProveru.length,
                razreseni: r.razreseni, nedokazivo: r.nedokazivo }};
    """)


@nodemark
def test_neizjavljen_red_nije_rok():
    """Bez `vrsta`/`stanje_odluke` red je dogadjaj hronologije, ne rok."""
    r = _rokovi([{"id": "1", "dogadjaj": "Rok za žalbu", "datum_iso": "2026-09-10"}])
    assert r["obaveze"] == 0
    assert r["zaProveru"] == 0
    assert r["nedokazivo"] == 1


@nodemark
def test_potvrdjen_rok_je_obaveza():
    r = _rokovi([{"id": "1", "dogadjaj": "Rok za žalbu", "datum_iso": "2026-09-10",
                  "vrsta": "rok", "stanje": "potvrdjen"}])
    assert r["obaveze"] == 1
    assert r["zaProveru"] == 0


@nodemark
def test_kandidat_nikad_nije_obaveza():
    r = _rokovi([{"id": "1", "dogadjaj": "Rok za žalbu", "datum_iso": "2026-09-10",
                  "vrsta": "rok", "stanje": "kandidat"}])
    assert r["obaveze"] == 0
    assert r["zaProveru"] == 1


@nodemark
@pytest.mark.parametrize("stanje", ["izvrsen", "otkazan", "odbijen"])
def test_razresen_rok_ne_ulazi_u_aktivne(stanje):
    r = _rokovi([{"id": "1", "dogadjaj": "Rok za žalbu", "datum_iso": "2026-09-10",
                  "vrsta": "rok", "stanje": stanje}])
    assert r["obaveze"] == 0
    assert r["zaProveru"] == 0
    assert r["razreseni"] == 1


@nodemark
def test_akter_sa_AI_nije_dokaz_o_vrsti():
    """Tekst nikad ne odlucuje o vrsti reda — to je Z016.2 zabrana."""
    r = _rokovi([{"id": "1", "dogadjaj": "ROK: odgovor na tužbu",
                  "datum_iso": "2026-09-10", "akter": "Pipeline (AI)",
                  "izvor": "LEGACY_UNKNOWN"}])
    assert r["obaveze"] == 0 and r["zaProveru"] == 0
    assert r["nedokazivo"] == 1


@nodemark
def test_istekao_rok_je_oznacen_kao_prosao():
    r = _js(f"""
      const sada = new Date(2026, 8, 5);
      const x = O.uRokove({_j([{"id": "1", "dogadjaj": "Rok", "datum_iso": "2026-08-20",
                                "vrsta": "rok", "stanje": "potvrdjen"}])}, sada);
      return {{ proslo: x.obaveze[0].proslo, kada: x.obaveze[0].kada }};
    """)
    assert r["proslo"] is True
    assert r["kada"].strip() != ""


@nodemark
def test_rokovi_su_sortirani_po_datumu_rastuce():
    r = _js(f"""
      const sada = new Date(2026, 8, 5);
      const x = O.uRokove({_j([
          {"id": "b", "dogadjaj": "Kasniji", "datum_iso": "2026-10-01", "vrsta": "rok", "stanje": "potvrdjen"},
          {"id": "a", "dogadjaj": "Raniji", "datum_iso": "2026-09-07", "vrsta": "rok", "stanje": "potvrdjen"},
      ])}, sada);
      return x.obaveze.map(o => o.id);
    """)
    assert r == ["a", "b"]


# ═══════════════════════════════════════════════════════════════════════════
# 4 — spisi
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_spis_bez_originala_ne_nudi_preuzimanje():
    s = _js('return O.uSpis({ id:"d1", naziv_fajla:"Tužba.pdf" });')
    assert s["imaOriginal"] is False


@nodemark
def test_spis_sa_originalom_nudi_preuzimanje():
    s = _js('return O.uSpis({ id:"d1", naziv_fajla:"Tužba.pdf", storage_path:"a/b.pdf" });')
    assert s["imaOriginal"] is True


@nodemark
def test_spis_bez_naziva_ne_ostaje_prazan():
    s = _js('return O.uSpis({ id:"d1" });')
    assert s["naziv"].strip() != ""


# ═══════════════════════════════════════════════════════════════════════════
# 5 — klijent vs stranka
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_klijent_i_stranka_su_odvojeni():
    d = _js(f"""
      const sada = new Date(2026, 8, 5);
      const x = O.sastaviDosije({{ predmet: {_j(PREDMET)},
        klijenti_linked: [{{ id:"k1", firma:"Marković Petar pr" }}] }}, null, sada);
      return {{ klijenti: x.klijenti.map(k=>k.naziv),
                tuzilac: x.zaglavlje.tuzilac, tuzeni: x.zaglavlje.tuzeni }};
    """)
    assert d["klijenti"] == ["Marković Petar pr"]
    assert d["tuzilac"] == "Marković Petar"
    assert d["tuzeni"] == "Delta osiguranje a.d.o."


@nodemark
def test_predmet_bez_klijenata_ne_izmislja_klijenta():
    d = _js(f"return O.sastaviDosije({{ predmet: {_j(PREDMET)} }}, null, new Date()).klijenti;")
    assert d == []


# ═══════════════════════════════════════════════════════════════════════════
# 6 — spremnost
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_spremnost_bez_statusa_je_null():
    assert _js("return O.uSpremnost({ score: 42 });") is None
    assert _js("return O.uSpremnost(null);") is None


@nodemark
def test_spremnost_ne_izlaze_broj():
    s = _js('return O.uSpremnost({ status:"delimično", score: 42, razlozi:["Nema stranaka"] });')
    assert "score" not in s
    # Vrednost se prikazuje citljivo (veliko pocetno slovo), ali se NE menja:
    # vidi `test_spremnost_ne_curi_sirov_enum`.
    assert s["status"].lower() == "delimično"
    assert s["razlozi"] == ["Nema stranaka"]


# ═══════════════════════════════════════════════════════════════════════════
# Struktura celina
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_sidra_pokrivaju_tacno_celine():
    """INVARIJANTA: nijedno sidro bez celine, nijedna celina bez sidra.

    Popis ispod je SNIMAK sadrzaja Dosijea, ne invarijanta. Prosiren je sa
    „naplata" kad je B16 dodao sestu celinu (rad evidentiran na predmetu) sa
    stvarnim tokom, backend ugovorom i testovima. Prva tvrdnja — ona koja
    stvarno stiti korisnika od sidra koje vodi u prazno — NIJE menjana.
    """
    r = _js("return { c: O.CELINE.map(x=>x.kljuc), s: O.SIDRA.map(x=>x.kljuc) };")
    assert r["c"] == r["s"]
    assert r["c"] == ["stanje", "hronologija", "analiza", "spisi", "rokovi",
                      "naplata"]


@nodemark
def test_hronologija_je_najnovije_prvo():
    r = _js(f"""return O.uHronologiju({_j([
        {"id": "star", "dogadjaj": "Prvi", "datum_iso": "2026-01-01"},
        {"id": "nov", "dogadjaj": "Drugi", "datum_iso": "2026-08-01"},
    ])}).map(x=>x.id);""")
    assert r == ["nov", "star"]


@nodemark
def test_prazan_odgovor_ne_rusi_dosije():
    d = _js("return Object.keys(O.sastaviDosije(null, null, new Date()));")
    for k in ("zaglavlje", "polja", "klijenti", "spisi", "hronologija", "rokovi"):
        assert k in d, d


@nodemark
def test_spremnost_ne_curi_sirov_enum():
    """
    `/health` vraca sirov enum („kriticno", „delimicno_spreman"). Prikazan
    takav, to je programerski zargon na ekranu advokata -- tacno ono sto
    Z015 §19 zabranjuje. Vrednost se ne menja, samo postaje rec; sirov oblik
    ostaje dostupan pod `statusSirovi` za dijagnostiku.
    """
    s = _js('return O.uSpremnost({ status:"delimicno_spreman", razlozi:["Nema stranaka"] });')
    assert s["status"] == "Delimicno spreman"
    assert "_" not in s["status"]
    assert s["statusSirovi"] == "delimicno_spreman"


# ═══════════════════════════════════════════════════════════════════════════
# ZADACI, ROCISTA, BELESKE — tri stvari koje NISU rok
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_zadatak_rociste_i_rok_su_tri_razlicite_stvari():
    """
    Zadatak je posao koji je advokat sam sebi zadao; rociste je zakazan
    termin pred sudom; rok je pravna posledica. Nijedno od prva dva ne prolazi
    kroz ugovor o rokovima (migracija 129) i nijedno ne sme da se pojavi kao
    rok. Domen ih drzi u tri odvojene funkcije nad tri odvojena izvora.
    """
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const rok = O.uRokove([{ id:"r", dogadjaj:"Rok", datum_iso:"2026-09-10",
                               vrsta:"rok", stanje:"potvrdjen" }], sada);
      const zad = O.uZadatke([{ id:"z", naziv:"Zadatak", status:"otvoren" }], sada);
      const roc = O.uRocista([{ id:"c", sud:"Sud", datum:"2026-09-12" }], sada);
      return { rokova: rok.obaveze.length, zadataka: zad.otvoreni.length,
               rocista: roc.redovi.length,
               zadatakURokovima: rok.obaveze.some(x => x.opis === "Zadatak"),
               rocisteURokovima: rok.obaveze.some(x => x.opis === "Sud") };
    """)
    assert r["rokova"] == 1 and r["zadataka"] == 1 and r["rocista"] == 1
    assert r["zadatakURokovima"] is False
    assert r["rocisteURokovima"] is False


@nodemark
def test_zavrsen_zadatak_ostaje_kao_dokaz_a_ne_medju_otvorenim():
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const z = O.uZadatke([
        { id:"1", naziv:"Otvoren", status:"otvoreno" },
        { id:"2", naziv:"Gotov",  status:"zavrsen" },
        { id:"3", naziv:"Otkazan", status:"otkazan" }], sada);
      return { otvorenih: z.otvoreni.map(x=>x.naziv), zavrsenih: z.zavrseni.length, ukupno: z.ukupno };
    """)
    assert r["otvorenih"] == ["Otvoren"]
    assert r["zavrsenih"] == 2
    assert r["ukupno"] == 3


@nodemark
def test_zadaci_sortirani_po_roku_a_bez_roka_idu_na_kraj():
    """
    Ulaz je NAMERNO veci od tri stavke i ima DVA zadatka bez roka.
    Sa tri stavke V8 koristi insertion sort i poredjenje se ne pozove u
    redosledu koji razotkriva obrnutu granu — mutacija je prezivela ne zato
    sto je test slab u nameri, nego zato sto je uzorak bio premali da grana
    uopste bude dosegnuta.
    """
    r = _js("""
      const sada = new Date(2026, 8, 5);
      return O.uZadatke([
        { id:"a", naziv:"Bez roka 1", status:"otvoreno" },
        { id:"b", naziv:"Najkasniji", status:"otvoreno", rok_datum:"2026-12-01" },
        { id:"c", naziv:"Raniji",     status:"otvoreno", rok_datum:"2026-09-07" },
        { id:"d", naziv:"Bez roka 2", status:"otvoreno" },
        { id:"e", naziv:"Srednji",    status:"otvoreno", rok_datum:"2026-10-15" },
        { id:"f", naziv:"Najraniji",  status:"otvoreno", rok_datum:"2026-09-06" }], sada)
        .otvoreni.map(x => x.naziv);
    """)
    assert r[:4] == ["Najraniji", "Raniji", "Srednji", "Najkasniji"], r
    assert set(r[4:]) == {"Bez roka 1", "Bez roka 2"}, r


@nodemark
def test_rociste_bez_suda_ili_datuma_nije_termin():
    """Sud i datum su obavezni po serverskom ugovoru — nepotpun red nije rociste."""
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const x = O.uRocista([
        { id:"1", sud:"Osnovni sud", datum:"2026-09-12" },
        { id:"2", sud:"Bez datuma" },
        { id:"3", datum:"2026-09-20" }], sada);
      return { potpunih: x.redovi.length, nepotpunih: x.nepotpuna };
    """)
    assert r["potpunih"] == 1
    assert r["nepotpunih"] == 2


@nodemark
def test_prazna_beleska_se_ne_prikazuje():
    r = _js('return O.uBeleske([{id:"1", sadrzaj:"Ima teksta"}, {id:"2", sadrzaj:"   "}, {id:"3"}]).length;')
    assert r == 1


@nodemark
def test_beleske_se_prenose_cele_a_ne_kao_broj():
    """
    Ranije je `sastaviDosije` vracao samo DUZINU — ekran je mogao da kaze
    „ima 3 beleske", ali ne i STA u njima pise, sto je jedino zbog cega
    beleska postoji.
    """
    d = _js("""return O.sastaviDosije({ predmet:{id:"p"},
      beleske:[{id:"b1", sadrzaj:"Zvao klijent."}] }, null, new Date());""")
    assert isinstance(d["beleske"], list)
    assert d["beleske"][0]["tekst"] == "Zvao klijent."
    assert d["brojBelezaka"] == 1
