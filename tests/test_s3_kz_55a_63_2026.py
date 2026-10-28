# -*- coding: utf-8 -*-
"""S3 — čl. 55a posle izmene KZ 63/2026 (objavljen 10.07.2026, primena od 18.07.2026).

Izvor (proveren 27.10.2026): prečišćen tekst Krivičnog zakonika na pravno-informacioni-sistem.rs
(eli/rep/sgrs/skupstina/zakon/2024/94/30 → „85/2005-30 … 94/2024-390, 63/2026-28“). Doslovni ćirilični tekst čl. 55a ispod je
kopiran sa te stranice; napomena izdavača: zakon 63/2026 stupa na snagu 18.07.2026, a samo njegovi čl. 2–3 (čl. 348–348g)
primenjuju se posle devet meseci. Lokalni tekst zakona (data/laws/pdfs/krivicni_zakonik.pdf) i baza Vindex su zaključno
sa 94/2024."""
import os
from datetime import date

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")   # `main` gradi klijenta pri uvozu; poziva se ne pravi

import pytest

from shared import visestruki_povrat as V

CL_55A_PIS = ("(1) За кривично дело учињено са умишљајем, за које је прописана казна затвора, суд ће изрећи казну изнад "
              "половине распона прописане казне полазећи од најмање мере те казне, под следећим условима: 1) ако је учинилац "
              "раније два пута осуђен за иста или истоврсна кривична дела учињена са умишљајем на затвор од најмање једну "
              "годину; 2) ако од дана отпуштања учиниоца са издржавања изречене казне до извршења новог кривичног дела није "
              "протекло пет година. (2) Под ранијом осудом подразумева се осуда за кривично дело која је утврђена "
              "правноснажном пресудом домаћег суда, односно суда стране државе.")

_LAT = dict(zip("абвгдђежзијклљмнњопрстћуфхцчџшАБВГДЂЕЖЗИЈКЛЉМНЊОПРСТЋУФХЦЧЏШ",
                ["a", "b", "v", "g", "d", "đ", "e", "ž", "z", "i", "j", "k", "l", "lj", "m", "n", "nj", "o", "p", "r", "s",
                 "t", "ć", "u", "f", "h", "c", "č", "dž", "š", "A", "B", "V", "G", "D", "Đ", "E", "Ž", "Z", "I", "J", "K",
                 "L", "Lj", "M", "N", "Nj", "O", "P", "R", "S", "T", "Ć", "U", "F", "H", "C", "Č", "Dž", "Š"]))

NOVO = ("Okrivljeni je ranije dva puta osuđen na zatvor od po dve godine za umišljajna dela, otpušten je pre tri godine, a sada "
        "je sa umišljajem izvršio delo za koje je propisan zatvor od jedne do osam godina.")


def _ishod(q):
    return V.izracunaj(**V.iz_pitanja(q)).primenjuje_se


def test_citat_je_doslovna_transliteracija_zvanicnog_teksta():
    assert "".join(_LAT.get(z, z) for z in CL_55A_PIS) == V.CITAT_55A
    assert "63/2026" in V.IZVOR_55A and "18.07.2026" in V.IZVOR_55A
    assert V.POCETAK_PRIMENE_63_2026 == date(2026, 7, 18)


def test_bez_navoda_o_istovrsnosti_uslov_je_nepoznat_a_uslovni_raspon_se_daje():
    t, r = V.blok(NOVO)
    assert r.primenjuje_se == V.NEPOZNATO
    assert "[NEPOZNATO] 1b) ranija dela su ista ili istovrsna kao novo delo" in t
    assert "Ako se uslovi utvrde: kazna bi morala biti veća od 4 godine i 6 meseci, najviše 8 godina" in t
    assert "baza zakona Vindex sadrži tekst Krivičnog zakonika zaključno sa izmenom 94/2024" in t


@pytest.mark.parametrize("dodatak,ocekivano", [
    (" Ranija dela su istovrsna sa novim delom.", V.DA),
    (" Ranija dela su ista krivična dela kao novo.", V.DA),
    (" Ranija dela nisu istovrsna sa novim.", V.NE),
    (" Ranija dela su različita krivična dela od novog.", V.NEPOZNATO),     # različita ≠ neistovrsna (ocenjuje sud)
    (" Ne radi se o istovrsnim delima.", V.NE),
    (" Nije reč o istovrsnim delima.", V.NE),
    (" Ranija dela nisu sva istovrsna sa novim.", V.NEPOZNATO),
    (" Tužilac tvrdi da su dela istovrsna, odbrana to osporava.", V.NEPOZNATO),
    (" Da li su ranija dela istovrsna?", V.NEPOZNATO),
    (" Ranija dela nisu ista, ali jesu istovrsna.", V.NEPOZNATO),            # oba smera → bez zaključka
])
def test_izricit_navod_istovrsnosti(dodatak, ocekivano):
    assert _ishod(NOVO + dodatak) == ocekivano


@pytest.mark.parametrize("q,ocekivano", [
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem, otpušten je pre tri godine, a "
     "sada je sa umišljajem izvršio krađu, propisan zatvor od jedne do osam godina.", V.NEPOZNATO),   # završna revizija M1:
    # sistem ne izvodi istovrsnost iz naziva (prefiks je spajao „nasilje u porodici“ i „nasilničko ponašanje“)
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine za nasilje u porodici učinjeno sa umišljajem, otpušten je pre "
     "tri godine, a sada je sa umišljajem izvršio nasilničko ponašanje, propisan zatvor od jedne do osam godina.", V.NEPOZNATO),
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem, otpušten je pre tri godine, a "
     "sada je sa umišljajem izvršio tešku krađu, propisan zatvor od jedne do osam godina.", V.NEPOZNATO),   # drugo delo
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine za prevare učinjene sa umišljajem, otpušten je pre tri godine, "
     "a sada je sa umišljajem izvršio krađu, propisan zatvor od jedne do osam godina.", V.NEPOZNATO),   # istovrsnost: sud
])
def test_istovrsnost_se_ne_izvodi_iz_naziva_dela(q, ocekivano):
    assert _ishod(q) == ocekivano


def test_vremensko_vazenje_i_strana_osuda_se_navode():
    q = ("Okrivljeni je dva puta osuđen za umišljajna dela na zatvor od po dve godine, jednom od strane suda u inostranstvu. "
         "Otpušten je 01.03.2022, a novo delo sa umišljajem izvršio je 15.01.2025. Propisan zatvor od jedne do osam godina.")
    t, r = V.blok(q)
    assert "čl. 5 st. 2" in t and "pre 18.07.2026" in t and "stranog suda" in t
    c = V.iz_pitanja(q.replace("15.01.2025", "15.09.2026"))
    assert c["novo_delo"] == date(2026, 9, 15)
    assert not any(n.startswith("Vremensko važenje") for n in V.izracunaj(**c).napomene)   # delo posle 18.07.2026


@pytest.mark.parametrize("mn_g,mx_g,polovina,najniza", [
    (1, 8, (4, 6), (4, 7)),            # 1–8: polovina 4 g. 6 m.; najniža iznad polovine na pune mesece 4 g. 7 m.
    (3, 12, (7, 6), (7, 7)),           # VKS Kzz 602/2022: 3–12 → 7 g. 6 m.; 7 g. 7 m. pravilno
])
def test_aritmetika_polovine_deterministicki(mn_g, mx_g, polovina, najniza):
    G, M = 360, 30
    r = V.izracunaj(novo_delo_umisljaj=True, propisan_min_dana=mn_g * G, propisan_max_dana=mx_g * G,
                    ranije_osude=[V.RanijaOsuda(True, 24)] * 2, proteklo_od_otpusta_meseci=24, istovrsna=True)
    assert r.primenjuje_se == V.DA
    assert r.raspon["polovina_raspona_dana"] == polovina[0] * G + polovina[1] * M
    assert r.raspon["najniza_dozvoljena_dana"] == najniza[0] * G + najniza[1] * M


# ── S3: nadležnost — Zakon o uređenju sudova i sedišta sudova (provereno na PIS 27.10.2026) ─────────────────────

def test_pravila_nadleznosti_nose_proveren_zakon_o_uredjenju_sudova_i_vremensku_granicu_sedista():
    import main as M
    t = M.NADLEZNOST_ZPP_PRAVILA
    assert "10/2023, bez kasnijih izmena" in t and "čl. 24 st. 2–3" in t and "čl. 25 st. 1 tač. 7–8" in t and "čl. 27 st. 1" in t
    assert "40.000 evra — ZPP čl. 403 st. 3" in t
    assert "101/2013, 9/2026, 56/2026" in t and "TEK OD 1. MARTA 2027" in t and "do tada važi raspored iz 101/2013" in t
    assert "nije potvrđen izvorom" not in t                     # stvarna nadležnost više nije „bez izvora“


def test_verzija_kljuca_kesa_promenjena_posle_s3():
    import main as M
    assert M._CACHE_VERZIJA == "2026-10-28-s3"


ZUS_PIS = {   # doslovno sa pravno-informacioni-sistem.rs (Закон о уређењу судова, 10/2023-25), provereno 27.10.2026
    "ZUS_24_2": "Основни суд у првом степену суди у грађанскоправном спору ако за поједини грађанскоправни спор није надлежан "
                "други суд и води извршни и ванпарнични поступак, осим ако законом није друкчије прописано.",
    "ZUS_24_3": "Основни суд у првом степену суди у стамбеном спору; спору поводом заснивања, постојања и престанка радног односа; о "
                "праву, обавези и одговорности из радног односа; о накнади штете коју запослени претрпи на раду или у вези са радом; "
                "спору поводом задовољавања стамбених потреба на основу рада.",
    "ZUS_25_1_7": "суди у грађанскоправном спору ако вредност предмета спора омогућује изјављивање ревизије",
    "ZUS_27_1_1": "у спору између домаћег и страног привредног друштва, предузећа, задруга и предузетника и њихових асоцијација "
                  "(привредни субјекти), у спору који настане између привредног субјекта и другог правног лица у обављању "
                  "делатности привредног субјекта, као и ако је у наведеном спору једна од странака физичко лице ако је са "
                  "странком у односу материјалног супарничарства;",
}


@pytest.mark.parametrize("ime", sorted(ZUS_PIS))
def test_citati_zus_su_doslovna_transliteracija(ime):
    import main as M
    assert "".join(_LAT.get(z, z) for z in ZUS_PIS[ime]) == getattr(M, ime)


@pytest.mark.parametrize("q,stvarna,sedista", [
    ("Tužimo fizičko lice sa prebivalištem u Novom Sadu radi vraćanja zajma od 3.000 evra. Koji sud je mesno i stvarno nadležan?", True, False),
    ("Tužimo fizičko lice sa prebivalištem na Voždovcu u Beogradu radi duga. Koji konkretan osnovni sud u Beogradu je nadležan?", True, True),
    ("Klijent iz Niša tuži privredno društvo sa sedištem u Kragujevcu. Koji sud je mesno nadležan?", False, False),
])
def test_napomene_stvarne_nadleznosti_i_sedista(q, stvarna, sedista):
    import main as M
    t = M._napomene_nadleznosti(q, "")
    assert ("--- STVARNA NADLEŽNOST" in t) is stvarna and ("od 1. marta 2027" in t) is sedista
    assert "nije potvrđen izvorom iz baze" not in t


def test_stari_tekst_55a_iz_baze_se_oznacava_u_odgovoru():
    import main as M
    q = ("Okrivljeni je ranije dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem, otpušten je pre tri "
         "godine, a sada je sa umišljajem izvršio krađu za koju je propisan zatvor od jedne do osam godina. Raspon?")
    ai = ("--- CITAT ZAKONA [RAG]\n\"Krivični zakonik, član 55a: Za krivično delo učinjeno sa umišljajem, za koje je propisana kazna "
          "zatvora, sud će izreći kaznu iznad polovine raspona propisane kazne, pod sledećim uslovima: 1) ako je učinilac ranije "
          "dva puta osuđen za krivična dela učinjena sa umišljajem na zatvor od najmanje jednu godinu\"")
    v = M._dodaj_proracun_povrata(q, {"status": "success", "data": ai})
    assert v["data"].count("[TEKST ČL. 55a PRE IZMENE 63/2026") == 1       # samo statutarna fraza
    cinjenice = M._dodaj_proracun_povrata(q, {"status": "success", "data": "Okrivljeni je osuđen za krivična dela učinjena "
                                                                         "sa umišljajem, i to dva puta."})
    assert "PRE IZMENE" not in cinjenice["data"]                             # činjenični tekst se ne označava
    blok = v["data"].split("\n\n--- CITAT ZAKONA")[0]
    assert "PRE IZMENE" not in blok and "polazeći od najmanje mere te kazne" in blok    # važeći tekst u proračunu


@pytest.mark.parametrize("q,ocekivano", [
    ("Koji konkretan osnovni sud u Beogradu je nadležan za tužbu za dug?", True),
    ("Koji je Vrhovni sud zauzeo stav o zastarelosti potraživanja iz ugovora o zajmu?", False),   # sudska praksa
    ("Koji je viši sud doneo presudu u predmetu o naknadi štete?", False),
    ("Koji apelacioni sud je ukinuo presudu o razvodu braka?", False),
    ("Sud za maloletnike je nadležan za koje učinioce?", False),                                     # krivično
    ("Koja sudska veća su nadležna za maloletnike?", False),
    ("Koji je disciplinski sud advokatske komore nadležan?", False),
])
def test_detektor_gradjanske_nadleznosti_posle_zavrsne_revizije(q, ocekivano):
    from app.services.retrieve import je_pitanje_gradjanske_nadleznosti
    assert je_pitanje_gradjanske_nadleznosti(q) is ocekivano


def test_napomena_o_preuzimanju_predmeta_ima_izvor_u_prelaznoj_odredbi():
    """Čl. 4 st. 3 zakona 9/2026 (PIS, „Одредбе које нису унете у пречишћен текст“): „Предмети који до дана почетка
    примене овог закона нису окончани пред Трећим основним судом у Београду … преузимају месно надлежни судови … основани
    овим законом.“ Primena: čl. 8 (izmenjen 56/2026) — „примењује се од 1. марта 2027. године“."""
    import main as M
    assert "Predmete koji do tada nisu okončani pred dosadašnjim Trećim osnovnim sudom u Beogradu preuzimaju mesno " \
           "nadležni sudovi osnovani tim izmenama" in M._NAPOMENA_SEDISTA
    assert "od 1. marta 2027. godine" in M._NAPOMENA_SEDISTA


class _Match:
    def __init__(self, md, mid="x"):
        self.id, self.metadata, self.score = mid, md, 0.9


class _Indeks:
    """Lažan Pinecone indeks: vraća dva stara vektora čl. 55a (tekst baze do 94/2024) i jedan čl. 55."""
    def __init__(self):
        self.upiti = []

    def query(self, **kw):
        self.upiti.append(kw)
        stari = f"Član 55a {V.CITAT_55A_DO_63_2026}"
        ms = [_Match({"law": "KZ", "article": "Član 55a", "zakon": "KZ", "clan": 55, "text": stari, "parent_text": stari}),
              _Match({"law": "KZ", "article": "Član 55", "zakon": "KZ", "clan": 55, "text": "Član 55 (1) Ako je učinilac …"}),
              _Match({"law": "ZKP", "article": "Član 55a", "text": "Član 55a drugi zakon"})]
        return type("R", (), {"matches": ms})()


@pytest.mark.parametrize("putanja", ["direktan", "vec", "semanticka"])
def test_korpus_cl_55a_se_cita_kao_vazeci_tekst_a_stari_je_oznacen_istorijski(monkeypatch, putanja):
    """Bojan beta: AI deo odgovora je iz baze navodio tekst čl. 55a PRE 63/2026 kao važeći. Svaka tačka čitanja zakonskog
    korpusa mora dati važeći tekst kao citabilni; stari ostaje samo označen kao istorijski. Drugi članovi i zakoni ne smeju
    da se menjaju."""
    from app.services import retrieve as R
    ix = _Indeks()
    monkeypatch.setattr(R, "_get_index", lambda: ix)
    monkeypatch.setattr(R, "_ugradi_query", lambda q: [0.0])
    ms = {"direktan": lambda: R._direktan_fetch_clana("Član 55a", "KZ"),
          "vec": lambda: R._pretraga_vec([0.0], 5),
          "semanticka": lambda: R._semanticka_pretraga("visestruki povrat", 5)}[putanja]()
    cl55a, cl55, zkp = ms
    assert cl55a.metadata["text"] == f"Član 55a {V.CITAT_55A}"
    assert "ista ili istovrsna" in R._formatiraj_match(cl55a).split("[ISTORIJSKI TEKST")[0]
    assert "CITABILNI TEKST: Član 55a (1) Za krivično delo" in R._formatiraj_match(cl55a)
    istorijski = cl55a.metadata["parent_text"].split("[ISTORIJSKI TEKST", 1)
    assert V.CITAT_55A_DO_63_2026 not in istorijski[0] and V.CITAT_55A_DO_63_2026 in istorijski[1]
    assert "do 17.07.2026" in istorijski[1] and "čl. 5 KZ" in istorijski[1]
    assert cl55.metadata["text"] == "Član 55 (1) Ako je učinilac …" and "parent_text" not in cl55.metadata
    assert zkp.metadata["text"] == "Član 55a drugi zakon"


def test_oznaka_starog_teksta_ne_pogadja_vazeci_citat_iz_korpusa():
    import main as M
    assert not M._STARI_55A_RE.search(f"Član 55a {V.CITAT_55A}")
    assert M._STARI_55A_RE.search(V.CITAT_55A_DO_63_2026)


@pytest.mark.parametrize("tekst, ocekivano", [
    ("Okrivljeni može pokušati da ospori primenu člana 55a ako smatra da uslovi nisu ispunjeni.", set()),
    ("Odbrana tvrdi da uslovi nisu ispunjeni.", set()),
    ("U ovom slučaju uslovi iz člana 55a nisu ispunjeni.", {"NE"}),
    ("Čl. 55a se ne primenjuje jer dela nisu istovrsna.", {"NE"}),
])
def test_uslovna_negacija_nije_tvrdnja_o_primeni(tekst, ocekivano):
    """Živo merenje (Bojan beta, D3): uslovi DA, a AI rečenica „ako smatra da uslovi nisu ispunjeni“ je davala lažno
    UPOZORENJE da AI tvrdi suprotno."""
    import main as M
    assert M._tvrdnje_o_primeni(tekst) == ocekivano


def test_zus_u_kontekstu_je_izvor_koji_provera_citata_priznaje():
    """Bojan beta (D2): AI deo je stvarnu nadležnost pripisivao ZPP čl. 40 jer ZUS nije bio u kontekstu. Proveren tekst ZUS-a
    ulazi u kontekst sa zaglavljem kao iz korpusa; citat „čl. 27 Zakona o uređenju sudova“ je tada potvrđen, a izmišljen
    član istog zakona nije."""
    import main as M
    izvori = M._izvori_iz_konteksta(M._ZUS_KONTEKST)
    (ident,) = izvori
    assert set(izvori[ident]) == {"24", "25", "27"}
    ok = M._klasifikuj_citate("Stvarno je nadležan privredni sud (čl. 27 Zakona o uređenju sudova).", M._ZUS_KONTEKST)
    lose = M._klasifikuj_citate("Nadležan je privredni sud (čl. 29 Zakona o uređenju sudova).", M._ZUS_KONTEKST)
    assert [c["nivo"] for c in ok] == [M.CITAT_SOURCE_MATCHED]
    assert [c["nivo"] for c in lose] == [M.CITAT_UNVERIFIED]
    assert all(M.ZUS_IZVOR in d for d in M._ZUS_KONTEKST)


def test_ozicenje_zus_konteksta_u_ask_agent():
    import inspect
    import main as M
    izvor = inspect.getsource(M.ask_agent)
    assert "filtrirani = filtrirani + _ZUS_KONTEKST" in izvor and "_je_nadl_ctx(pitanje_api)" in izvor
