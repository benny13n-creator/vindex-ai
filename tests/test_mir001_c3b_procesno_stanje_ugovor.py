# -*- coding: utf-8 -*-
"""MIR001 C3b STRUCTURAL TASK-01 — izvodljivost ugovora procesnog stanja utemeljenog na izvoru (`shared/procesno_stanje`).

Scenariji A–D su tekstovi Golden Case spisa iz slepog merenja (`docs/v2-execution/mir001_c3b_model/t03`), doslovno.
Negativni slučajevi (uključujući napade recenzenta GATE-01, 1. prolaz): lažno poklapanje dokumenta, stranka u
zapisniku, narativ ranije ukinute odluke, kasniji akt suda, tihi promašaji (velika slova, negacije, nevidljivi i
ćirilični znaci), zamke datuma, izvod modela/zastareo izvod, tuđi predmet, potvrda vrste samo iz audit traga.
"""
import inspect

import pytest

from shared import procesno_stanje as PS

P, U = "pred-1", "user-A"
_ZAGLAVLJE = "PRIVREDNI SUD U PRIMERGRADU (SINTETICKI)\nBroj predmeta: P 9901/2026\n"
DOK06 = (_ZAGLAVLJE + "IZJASNJENJE TUZENOG NA NALAZ VESTAKA (SINTETICKI PREDMET)\n"
         "Tuzeni osporava nalaz vestaka od 15.06.2026. godine.\nTuzeni tvrdi da vestak nije izvrsio uvid u gradjevinski dnevnik.\n"
         "Tuzeni predlaze dopunu vestacenja.\nDatum izjasnjenja: 01.07.2026. godine.")
ZAPISNIK = (_ZAGLAVLJE + "ZAPISNIK SA ROCISTA (SINTETICKI PREDMET)\nRociste odrzano dana 15.07.2026. godine.\n"
            "Uvidom u gradjevinsku dozvolu utvrdjeno je da je izdata dana 01.02.2024. godine.\n"
            "Sud prihvata predlog za dopunu vestacenja.\n"
            "Sud nalaze tuzenom da dostavi gradjevinski dnevnik u roku od 15 dana.\n"
            "Tuzilac je precizirao tuzbeni zahtev na iznos od 3.150.000 dinara.\n"
            "Tuzilac povlaci zahtev za naknadu stete na robi od 600.000 dinara.\n"
            "Sledece rociste zakazano je za 18.11.2026. godine.")
ODUSTANAK = (_ZAGLAVLJE + "PODNESAK TUZENOG (SINTETICKI PREDMET)\nTuzeni odustaje od predloga za dopunu vestacenja.\n"
             "Tuzeni navodi da gradjevinski dnevnik nije sacuvan.\nDatum podneska: 05.09.2026. godine.")
BEZ_ZAPISNIKA = (_ZAGLAVLJE + "PODNESAK TUZENOG (SINTETICKI PREDMET)\nTuzeni navodi da je na rocistu odrzanom 15.07.2026. "
                 "godine raspravljano o njegovom predlogu za dopunu vestacenja.\nTuzeni ponavlja predlog za dopunu vestacenja.\n"
                 "Datum podneska: 20.07.2026. godine.")
PREDUJAM = ZAPISNIK.replace("Sud nalaze tuzenom da dostavi gradjevinski dnevnik u roku od 15 dana.",
                            "Sud nalaze tuziocu da u roku od 8 dana od prijema zapisnika uplati predujam za dopunu "
                            "vestacenja u iznosu od 60.000 dinara.")


def _d(oznaka, tekst, **kw):
    return {"id": "id-" + oznaka, "predmet_id": P, "user_id": U, "oznaka": oznaka, "tekst": tekst, **kw}


def _st(*dok, neprocitani=(), potvrde_vrste=None):
    return PS.utvrdi(list(dok), predmet_id=P, user_id=U, neprocitani=neprocitani, potvrde_vrste=potvrde_vrste)


def _sud(st, vrsta):
    return [x for x in st["dogadjaji"] if x["akter"] == "SUD" and x["vrsta"] == vrsta]


def _nep(st, deo):
    return [n for n in st["nepoznato"] if deo in n]


def _bez_tvrdnji_o_stanju(dog):
    """Izvod je proveren; tumačenje nikad; nijedno polje ne tvrdi važenje, prestanak, istek, izvršenje ni uplatu."""
    assert dog["klasa"] == PS.VERIFIED and dog["klasa_tumacenja"] in (PS.UNKNOWN, PS.CONTESTED)
    assert not ({"vazi", "prestao", "istekao", "izvrseno", "placeno", "ponisten"} & set(dog)), dog
    assert dog.get("izvrsenje", PS.UNKNOWN) == PS.UNKNOWN and dog.get("uplata", PS.UNKNOWN) == PS.UNKNOWN
    if "rok" in dog:
        assert dog["rok"]["tok_i_istek"] == PS.UNKNOWN


# ── A: sud izričito nalaže dopunu ────────────────────────────────────────────────────────────────────────────────
def test_A_izvod_naloga_je_proveren_tumacenje_je_kandidat_rok_i_izvrsenje_nepoznati():
    st = _st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK))
    [pr], [nal] = _sud(st, "SUD_PRIHVATA"), _sud(st, "SUD_NALAZE")
    for x in (pr, nal):
        assert x["oznaka"] == "DOK-07" and x["dokument_id"] == "id-DOK-07" and x["datum_dokumenta"] == "2026-07-15"
        assert x["vrsta_dokumenta"] == {"akter": "SUD", "osnov": "NASLOV", "klasa": PS.UNKNOWN,
                                        "naslov": "ZAPISNIK SA ROCISTA (SINTETICKI PREDMET)"}
        assert PS.potvrdi_izvod(ZAPISNIK, x["tekst_sha256"], x["pocetak"], x["kraj"], x["izvod"])
        _bez_tvrdnji_o_stanju(x)
    assert pr["izvod"] == "Sud prihvata predlog za dopunu vestacenja."
    assert nal["rok"] == {"trajanje_dana": 15, "pocetak_iz_izvoda": None, "tok_i_istek": PS.UNKNOWN}
    assert [k["odnos"] for k in pr["kasniji"]] == ["RANIJE"] and "stanje" not in pr     # raniji predlog = pozadina
    assert "stanje" not in nal                         # stranka u istom zapisniku (precizira zahtev) nije o nalogu
    assert _nep(st, "postupljeno po nalogu") and st["potpunost"] == "POTPUNO"


# ── B: tuženi kasnije odustaje ───────────────────────────────────────────────────────────────────────────────────
def test_B_kasniji_odustanak_ne_ukida_nalog_nego_ga_cini_spornim_bez_dejstva():
    st = _st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", ODUSTANAK))
    [pr], [nal] = _sud(st, "SUD_PRIHVATA"), _sud(st, "SUD_NALAZE")
    kasn = [k for k in pr["kasniji"] if k["oznaka"] == "DOK-08"]
    assert kasn == [{"id": kasn[0]["id"], "oznaka": "DOK-08", "vrsta": "STRANKA_ODUSTAJE", "odnos": "KASNIJE",
                     "dejstvo": PS.UNKNOWN}]
    assert pr["stanje"] == PS.CONTESTED and nal["stanje"] == PS.CONTESTED      # i navod „dnevnik nije sačuvan“
    _bez_tvrdnji_o_stanju(pr)
    _bez_tvrdnji_o_stanju(nal)
    [od] = [x for x in st["dogadjaji"] if x["vrsta"] == "STRANKA_ODUSTAJE"]
    assert od["akter"] == "TUZENI" and od["datum_dokumenta"] == "2026-09-05"
    assert _nep(st, "da li DOK-08 (stranka_odustaje, kasnije) menja ovu odluku")


# ── C: zapisnika nema ────────────────────────────────────────────────────────────────────────────────────────────
def test_C_bez_zapisnika_navod_stranke_o_rocistu_nije_odluka_a_ishod_je_nepoznat():
    st = _st(_d("DOK-06", DOK06), _d("DOK-07", BEZ_ZAPISNIKA))
    assert not [x for x in st["dogadjaji"] if x["akter"] == "SUD"]
    [nav] = [x for x in st["dogadjaji"] if x["vrsta"] == "STRANKA_NAVODI_O_SUDU"]
    assert nav["akter"] == "TUZENI" and nav["klasa"] == PS.VERIFIED          # proveren je NAVOD, ne ročište
    assert "među pročitanim dokumentima nema dokumenta prepoznatog kao sudski" in st["nepoznato"]
    assert _nep(st, "zapisnik sa ročišta od 15.07.2026 nije prepoznat među pročitanim dokumentima — ishod ročišta NEPOZNAT")
    assert not _nep(st, "nije među pročitanim")                              # odsustvo se ne tvrdi


def test_C_zapisnik_istog_datuma_postoji_nema_lazne_nepoznanice():
    assert not _nep(_st(_d("DOK-07", ZAPISNIK), _d("DOK-08", BEZ_ZAPISNIKA)), "zapisnik sa ročišta")
    # GATE-01 3. prolaz R1: uobičajen red „… godine, sa početkom u 10 časova“ (datum dokumenta tada nije označen)
    z = ZAPISNIK.replace("Rociste odrzano dana 15.07.2026. godine.", "Rociste odrzano dana 15.07.2026. godine, sa pocetkom u 10 casova.")
    assert PS.datum_dokumenta(z, "SUD")["datum"] is None
    assert not _nep(_st(_d("DOK-07", z), _d("DOK-08", BEZ_ZAPISNIKA)), "zapisnik sa ročišta")


# ── D: predujam — uplata i rok nisu utvrđeni ─────────────────────────────────────────────────────────────────────
def test_D_predujam_uplata_i_tok_roka_nepoznati():
    st = _st(_d("DOK-07", PREDUJAM))
    [nal] = _sud(st, "SUD_NALAZE")
    assert nal["uplata"] == PS.UNKNOWN and nal["izvrsenje"] == PS.UNKNOWN
    assert nal["rok"] == {"trajanje_dana": 8, "pocetak_iz_izvoda": "od prijema zapisnika", "tok_i_istek": PS.UNKNOWN}
    assert _nep(st, "uplata nije utvrđena iz pročitanih dokumenata") and _nep(st, "rok od 8 dana")
    assert not _nep(st, "nema dokumenta")                                    # odsustvo se ne tvrdi


def test_D_navod_stranke_o_uplati_nije_dokaz_uplate():
    navod = (_ZAGLAVLJE + "PODNESAK TUZIOCA (SINTETICKI PREDMET)\nTuzilac navodi da je uplatio predujam za dopunu "
             "vestacenja.\nDatum podneska: 20.07.2026. godine.")
    st = _st(_d("DOK-07", PREDUJAM), _d("DOK-08", navod))
    [nal] = _sud(st, "SUD_NALAZE")
    [n] = [x for x in st["dogadjaji"] if x["oznaka"] == "DOK-08"]
    assert n["vrsta"] == "STRANKA_NAVODI_IZVRSENJE" and n["akter"] == "TUZILAC"
    assert nal["uplata"] == PS.UNKNOWN and nal["stanje"] == PS.CONTESTED
    assert any(k["oznaka"] == "DOK-08" and k["dejstvo"] == PS.UNKNOWN for k in nal["kasniji"])


def test_D_konstatacija_uplate_u_zapisniku_vezana_ali_uplata_ostaje_neutvrdjena():
    t = PREDUJAM.replace("Tuzilac je precizirao", "Konstatuje se da je tuzilac uplatio predujam za dopunu vestacenja.\n"
                                                  "Tuzilac je precizirao")
    st = _st(_d("DOK-07", t))
    [nal] = _sud(st, "SUD_NALAZE")
    assert nal["uplata"] == PS.UNKNOWN and nal["stanje"] == PS.CONTESTED
    assert [k["vrsta"] for k in nal["kasniji"] if k["odnos"] == "ISTI_DOKUMENT"] == ["SUD_KONSTATUJE"]


# ── Negativni: lažno poklapanje dokumenta (napadi GATE-01) ───────────────────────────────────────────────────────
@pytest.mark.parametrize("tekst", [
    "Veza: Vase resenje P 9901/2026\nPODNESAK TUZIOCA\nSud je usvojio tuzbeni zahtev u celosti.\n",
    _ZAGLAVLJE + "Predmet: Primedbe tuzenog na zapisnik\nTuzilac predlaze da sud odbije predlog za dopunu vestacenja.\n"
                 "Datum podneska: 20.07.2026.",
    _ZAGLAVLJE + "PODNESAK TUZENOG (SINTETICKI PREDMET)\nSud prihvata predlog za dopunu vestacenja.\nDatum podneska: 20.07.2026.",
])
def test_tekst_stranke_nikad_ne_postaje_odluka_suda(tekst):
    st = _st(_d("DOK-09", tekst))
    assert not [x for x in st["dogadjaji"] if x["akter"] == "SUD"]
    assert all(x["klasa_tumacenja"] == PS.UNKNOWN for x in st["dogadjaji"])


def test_red_veza_ili_predmet_nije_naslov():
    assert PS.vrsta_dokumenta("Veza: Vase resenje P 9901/2026\nPODNESAK TUZIOCA\n")["akter"] == "TUZILAC"
    assert PS.vrsta_dokumenta("Predmet: Primedbe tuzenog na zapisnik\nTekst.")["akter"] == "NEPOZNAT"


def test_stranka_u_zapisniku_nije_glas_suda():
    t = ZAPISNIK + ("\nPunomocnik tuzenog predlaze da sud odbije tuzbeni zahtev kao neosnovan.\n"
                    "Punomocnik tuzioca navodi da je sud vec usvojio njihov predlog na ranijem rocistu.\n"
                    "Tuzeni predlaze dopunu vestacenja.")
    st = _st(_d("DOK-07", t))
    assert {x["vrsta"] for x in st["dogadjaji"] if x["akter"] == "SUD"} == {"SUD_PRIHVATA", "SUD_NALAZE", "SUD_ZAKAZANO"}
    stranka = [x for x in st["dogadjaji"] if x["vrsta"] == "STRANKA_U_SUDSKOM_DOKUMENTU"]
    assert {x["izvod"][:20] for x in stranka} >= {"Punomocnik tuzenog p", "Punomocnik tuzioca n", "Tuzeni predlaze dopu"}
    assert all(x["akter"] == "STRANKA" for x in stranka)
    # predlog stranke u ISTOM zapisniku o istom predmetu je pozadina odluke, ne osporavanje
    [pr] = _sud(st, "SUD_PRIHVATA")
    assert [k["odnos"] for k in pr["kasniji"]] == ["ISTI_DOKUMENT"] and "stanje" not in pr


@pytest.mark.parametrize("rec", ["Punomocnik tuzioca: sud je vec usvojio predlog za dopunu.",            # subjekat
                                 "Na rocistu je punomocnik tuzenog predlozio da sud odbije tuzbeni zahtev."])  # govor
def test_stranka_kao_subjekat_ili_preneseni_govor_nije_sud(rec):
    st = _st(_d("DOK-07", _ZAGLAVLJE + "ZAPISNIK SA ROCISTA\n" + rec + "\n"))
    assert not [x for x in st["dogadjaji"] if x["akter"] == "SUD"]


# ── GATE-01 2. prolaz N1: dativ i preneseni govor ne smeju progutati nalog suda ──────────────────────────────────
@pytest.mark.parametrize("rec,vrsta", [
    ("Tuziocu se nalaze da u roku od 8 dana od prijema zapisnika uplati predujam od 60.000 dinara.", "SUD_NALAZE"),
    ("Tuzenom se nalaze da dostavi gradjevinski dnevnik u roku od 15 dana.", "SUD_NALAZE"),
    ("Strankama se nalaze da u roku od 8 dana dostave pisane izjave.", "SUD_NALAZE"),
    ("Nakon sto je tuzeni predlozio dopunu vestacenja, sud prihvata predlog i odredjuje dopunu.", "SUD_PRIHVATA"),
    ("Sud nalaze tuzenom da dostavi dnevnik, kako tuzilac predlaze, jer je to potrebno.", "SUD_NALAZE"),
    ("Predlog tuzenog za dopunu vestacenja se prihvata.", "SUD_PRIHVATA"),
    ("Tuzenom sud nalaze da dostavi gradjevinski dnevnik.", "SUD_NALAZE"),                        # dativ bez „se“
    ("Tuzeni se obavezuje da tuziocu isplati iznos od 3.150.000 dinara.", "SUD_NALAZE"),          # izreka presude
])
def test_bezlicni_i_slozeni_nalog_ostaje_glas_suda(rec, vrsta):
    st = _st(_d("DOK-07", _ZAGLAVLJE + "ZAPISNIK SA ROCISTA\nRociste odrzano dana 15.07.2026. godine.\n" + rec + "\n"))
    [x] = [x for x in st["dogadjaji"] if x["izvod"] == rec]
    assert (x["akter"], x["vrsta"]) == ("SUD", vrsta)


def test_D_bezlicni_nalog_o_predujmu():
    t = PREDUJAM.replace("Sud nalaze tuziocu da u roku od 8 dana", "Tuziocu se nalaze da u roku od 8 dana")
    [nal] = _sud(_st(_d("DOK-07", t)), "SUD_NALAZE")
    assert nal["uplata"] == PS.UNKNOWN and nal["rok"]["pocetak_iz_izvoda"] == "od prijema zapisnika"


def test_preneseni_govor_sa_odlukom_je_glasan():
    st = _st(_d("DOK-07", ZAPISNIK + "\nPunomocnik tuzenog predlaze da sud odbije tuzbeni zahtev kao neosnovan."))
    assert _nep(st, "rečenica pripisana stranci pominje odluku suda — ko odlučuje, nije utvrđeno")


def test_inicijal_i_din_ne_seku_izvod():
    t = (_ZAGLAVLJE + "ZAPISNIK SA ROCISTA\nSud nalaze vestaku M. Markovicu da u roku od 30 dana dostavi dopunu nalaza.\n"
         "Sud nalaze tuziocu da uplati predujam od 60.000 din. U roku od 8 dana od prijema zapisnika.\n")
    izvodi = [x["izvod"] for x in _sud(_st(_d("DOK-07", t)), "SUD_NALAZE")]
    assert izvodi[0].endswith("dopunu nalaza.") and izvodi[1].endswith("od prijema zapisnika.")


def test_dva_naslova_razlicite_vrste_su_sukob_i_naslov_nije_u_izvodu():
    t = "Zakljucak suda od 10.07.2026 - odgovor tuzenog\nPODNESAK TUZENOG\nTuzeni odustaje od predloga."
    v = PS.vrsta_dokumenta(t)
    assert v["klasa"] == PS.CONTESTED and "dva naslova" in v["sukob"]
    t2 = "Zapisnik sa rocista\nSud prihvata predlog za dopunu vestacenja."
    [x] = _sud(_st(_d("DOK-07", t2)), "SUD_PRIHVATA")
    assert x["izvod"] == "Sud prihvata predlog za dopunu vestacenja."


def test_odustanak_u_istom_zapisniku_cini_odluku_spornom():
    t = ZAPISNIK + "\nPunomocnik tuzenog odustaje od predloga za dopunu vestacenja."
    [pr] = _sud(_st(_d("DOK-07", t)), "SUD_PRIHVATA")
    assert pr["stanje"] == PS.CONTESTED and [k["odnos"] for k in pr["kasniji"]] == ["ISTI_DOKUMENT"]


def test_dokument_bez_naslova_recenica_nalik_odluci_je_nepoznat_akter_i_glasno():
    st = _st(_d("DOK-09", "Sud prihvata predlog za dopunu vestacenja.\nSud nalaze tuzenom da dostavi dnevnik."))
    assert {x["vrsta"] for x in st["dogadjaji"]} == {"NEPOZNAT_AKTER"} and all(x["akter"] == "NEPOZNAT" for x in st["dogadjaji"])
    assert _nep(st, "DOK-09: vrsta dokumenta nije utvrđena")


# ── Negativni: nepotkrepljeno tumačenje (ranija/ukinuta odluka, kasniji akt suda) ────────────────────────────────
def test_narativ_ranije_ukinute_odluke_nije_vazeca_odluka():
    t = (_ZAGLAVLJE + "RESENJE\nResenjem od 01.03.2026. sud je prihvatio predlog za dopunu vestacenja, ali je to resenje "
         "ukinuto od strane viseg suda.\nDoneto dana 20.09.2026.\n")
    st = _st(_d("DOK-10", t))
    assert not _sud(st, "SUD_PRIHVATA")
    [x] = _sud(st, "SUD_NARATIV")
    assert x["klasa_tumacenja"] == PS.UNKNOWN and _nep(st, "sud narativ, značenje i važenje nisu utvrđeni")


def test_kasniji_akt_suda_koji_ukida_cini_odluke_spornim():
    uk = _ZAGLAVLJE + "RESENJE\nUkida se zakljucak o dopuni vestacenja.\nDoneto dana 20.09.2026.\n"
    st = _st(_d("DOK-07", ZAPISNIK), _d("DOK-11", uk))
    [pr], [nal] = _sud(st, "SUD_PRIHVATA"), _sud(st, "SUD_NALAZE")
    assert pr["stanje"] == nal["stanje"] == PS.CONTESTED
    assert [k["odnos"] for k in pr["kasniji"] if k["oznaka"] == "DOK-11"] == ["KASNIJE"]          # isti predmet
    assert [k["odnos"] for k in nal["kasniji"] if k["oznaka"] == "DOK-11"] == ["NEPOZNAT_PREDMET"]  # ne zna se koja


def test_dve_recenice_u_istom_redu_su_dve_radnje():
    t = PREDUJAM.replace("u iznosu od 60.000 dinara.", "u iznosu od 60.000 dinara. Konstatuje se da je tuzilac uplatio "
                                                          "predujam za dopunu vestacenja.")
    st = _st(_d("DOK-07", t))
    [nal] = _sud(st, "SUD_NALAZE")
    assert nal["izvod"].endswith("60.000 dinara.") and nal["uplata"] == PS.UNKNOWN and nal["stanje"] == PS.CONTESTED
    assert _sud(st, "SUD_KONSTATUJE")


def test_ne_sece_posle_datuma_ni_skracenice():
    t = _ZAGLAVLJE + "RESENJE\nZakljuckom br. 5 od 01.03.2026. Sud je prihvatio predlog za dopunu vestacenja.\n"
    [x] = _st(_d("DOK-10", t))["dogadjaji"]
    assert x["izvod"].startswith("Zakljuckom br. 5") and x["vrsta"] == "SUD_NARATIV"


def test_odustanak_opisan_drugim_recima_nije_vezan_ali_je_glasan():
    od = _ZAGLAVLJE + "PODNESAK TUZENOG\nTuzeni povlaci zahtev iz svog izjasnjenja od 01.07.2026.\nDatum podneska: 05.09.2026.\n"
    st = _st(_d("DOK-07", ZAPISNIK), _d("DOK-08", od))
    assert _nep(st, "DOK-08: stranka_odustaje nije tekstom vezan ni za jednu odluku suda")


def test_ranije_u_pravoj_odluci_nije_narativ_a_nevezan_odustanak_je_glasan_i_bez_naloga():
    t = _ZAGLAVLJE + "ZAPISNIK SA ROCISTA\nRociste odrzano dana 15.07.2026. godine.\nSud prihvata ranije stavljen predlog tuzenog za dopunu vestacenja.\n"
    st = _st(_d("DOK-07", t))
    assert _sud(st, "SUD_PRIHVATA")
    nar = _ZAGLAVLJE + "RESENJE\nResenjem od 01.03.2026. sud je prihvatio predlog, ali je resenje ukinuto.\n"
    od = _ZAGLAVLJE + "PODNESAK TUZENOG\nTuzeni povlaci zahtev iz izjasnjenja.\nDatum podneska: 05.09.2026.\n"
    st2 = _st(_d("DOK-10", nar), _d("DOK-08", od))
    assert not [x for x in st2["dogadjaji"] if x["vrsta"] in PS._NALOZI]
    assert _nep(st2, "DOK-08: stranka_odustaje nije tekstom vezan")


def test_dve_odluke_u_jednoj_recenici_nisu_jedna_oznaka():
    t = _ZAGLAVLJE + "ZAPISNIK SA ROCISTA\nSud prihvata predlog tuzioca, a odbija predlog tuzenog za dopunu vestacenja.\n"
    [x] = _sud(_st(_d("DOK-07", t)), "SUD_VISESTRUKO")
    assert x["kandidati"] == ["SUD_ODBIJA", "SUD_PRIHVATA"]


# ── Negativni: tihi promašaji moraju biti glasni ─────────────────────────────────────────────────────────────────
def test_izreka_velikim_slovima_je_odluka_a_ne_zaglavlje():
    t = ZAPISNIK + "\nSUD NALAZE TUZIOCU DA UPLATI PREDUJAM OD 60.000 DINARA U ROKU OD 8 DANA."
    nalozi = _sud(_st(_d("DOK-07", t)), "SUD_NALAZE")
    assert len(nalozi) == 2 and nalozi[1]["uplata"] == PS.UNKNOWN and nalozi[1]["rok"]["trajanje_dana"] == 8


@pytest.mark.parametrize("rec", ["Predlog tuzenog se ne usvaja.", "Sud je odlucio da ne prihvati predlog.",
                                 "Sud ne nalazi osnov da prihvati predlog.", "Sud nije prihvatio predlog za dopunu vestacenja.",
                                 "Ne prihvata se predlog za prekid postupka."])
def test_negacije_nikad_prihvatanje_i_uvek_glasno(rec):
    st = _st(_d("DOK-07", _ZAGLAVLJE + "RESENJE\n" + rec + "\n"))
    assert not _sud(st, "SUD_PRIHVATA") and not _sud(st, "SUD_NALAZE")
    assert _sud(st, "SUD_NERAZVRSTANO") and _nep(st, "sud nerazvrstano")


def test_nerazvrstana_recenica_suda_je_glasna_i_kad_postoje_druge_odluke():
    t = ZAPISNIK + "\nPredujam za dopunu se polaze na racun suda."
    st = _st(_d("DOK-07", t))
    assert _sud(st, "SUD_PRIHVATA") and _nep(st, "rečenica sudskog dokumenta nije razvrstana — „Predujam za dopunu")


def test_nevidljivi_znak_se_uklanja_a_cirilicni_znak_je_glasan():
    t = (_ZAGLAVLJE + "ZAPISNIK SA ROCISTA\nSud​ nalaze tuzenom da dostavi dnevnik u roku od 15 dana.\n"
         "Сud prihvata predlog za dopunu vestacenja.\n")
    st = _st(_d("DOK-07", t))
    assert len(_sud(st, "SUD_NALAZE")) == 1 and not _sud(st, "SUD_PRIHVATA")
    assert _nep(st, "rečenica sa ćiriličnim ili neobičnim znacima nije razvrstana")


def test_cirilicni_dokument_se_ne_prepoznaje_i_to_se_kaze():
    st = _st(_d("DOK-07", "ЗАПИСНИК СА РОЧИШТА\nСуд прихвата предлог за допуну вештачења."))
    assert not [x for x in st["dogadjaji"] if x["akter"] == "SUD"]
    assert _nep(st, "DOK-07: vrsta dokumenta nije utvrđena") and _nep(st, "ćiriličnim")


def test_sudski_dokument_bez_prepoznate_odluke_nije_nema_odluke():
    t = _ZAGLAVLJE + "ZAPISNIK SA ROCISTA (SINTETICKI PREDMET)\nRociste odrzano dana 15.07.2026. godine.\nIzvodi se dokaz uvidom u spise."
    st = _st(_d("DOK-07", t))
    assert not _nep(st, "nema dokumenta prepoznatog kao sudski") and _nep(st, "DOK-07: sudski dokument u kom sistem nije prepoznao")


def test_bezlicni_oblik_resenja_je_odluka_suda():
    res = (_ZAGLAVLJE + "RESENJE\nPrihvata se predlog tuzenog za dopunu vestacenja.\nNalaze se tuzenom da dostavi "
           "gradjevinski dnevnik u roku od 15 dana od dana prijema resenja.\nOdbija se predlog za izvodjenje dokaza "
           "saslusanjem svedoka.")
    st = _st(_d("DOK-09", res))
    assert [x["vrsta"] for x in st["dogadjaji"]] == ["SUD_PRIHVATA", "SUD_NALAZE", "SUD_ODBIJA"]
    assert _sud(st, "SUD_NALAZE")[0]["rok"]["pocetak_iz_izvoda"] == "od dana prijema resenja"


# ── Datumi ───────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("telo", ["Datum resenja: 15.06.2026.\n", "Podsecamo da je rociste odrzano dana 01.07.2026. godine.\n"])
def test_datum_druge_vrste_u_podnesku_nije_datum_podneska(telo):
    od = _ZAGLAVLJE + "PODNESAK TUZENOG\n" + telo + "Tuzeni odustaje od predloga za dopunu vestacenja.\n"
    st = _st(_d("DOK-07", ZAPISNIK), _d("DOK-08", od))
    [pr] = _sud(st, "SUD_PRIHVATA")
    assert [k["odnos"] for k in pr["kasniji"]] == ["NEPOZNAT_REDOSLED"] and pr["stanje"] == PS.CONTESTED


def test_opsti_oblik_datuma_i_mesto_dana():
    assert PS.datum_dokumenta("PODNESAK\nTekst.\nDatum: 05.09.2026.", "TUZENI")["datum"] == "2026-09-05"
    assert PS.datum_dokumenta("RESENJE\nU Beogradu, dana 20.09.2026. godine", "SUD")["datum"] == "2026-09-20"
    assert PS.datum_dokumenta("PODNESAK\nDatum podneska: 05.09.2026.\nDatum: 01.07.2026.", "TUZENI")["datum"] is None


def test_datum_sa_dj_cuva_polozaj_izvoda():
    t = "REŠENJE o određivanju\nU Đakovici, dana 20.09.2026."
    d = PS.datum_dokumenta(t, "SUD")
    assert d["datum"] == "2026-09-20" and d["izvod"] == "U Đakovici, dana 20.09.2026."
    # citat datuma usred teksta (red nije samo oznaka i datum) nije datum dokumenta
    assert PS.datum_dokumenta("PODNESAK\nResenje od dana 15.06.2026. je doneto.", "TUZENI")["datum"] is None
    assert PS.datum_dokumenta("PODNESAK\nU Beogradu, dana 15.06.2026. sud je doneo resenje.", "TUZENI")["datum"] is None
    assert PS.datum_dokumenta("PODNESAK\nDatum: 15.06.2026. je datum resenja na koje se odnosi.", "TUZENI")["datum"] is None


# ── Izvor, izolacija, potvrda vrste ──────────────────────────────────────────────────────────────────────────────
def test_izvod_modela_ili_zastareo_izvod_ne_prolazi_proveru():
    [x] = _sud(_st(_d("DOK-07", ZAPISNIK)), "SUD_PRIHVATA")
    sha, a, b = x["tekst_sha256"], x["pocetak"], x["kraj"]
    assert PS.potvrdi_izvod(ZAPISNIK, sha, a, b, x["izvod"])
    assert not PS.potvrdi_izvod(ZAPISNIK, sha, a, b, "Sud je ukinuo nalog za dopunu vestacenja.")   # tekst modela
    assert not PS.potvrdi_izvod(ZAPISNIK, sha, a + 1, b + 1, x["izvod"])                             # pomereno mesto
    izmenjen = ZAPISNIK.replace("15 dana", "30 dana")
    assert not PS.potvrdi_izvod(izmenjen, sha, a, b, izmenjen[a:b])                                   # drugi tekst
    assert not PS.potvrdi_izvod(ZAPISNIK, sha, True, b, x["izvod"])                                   # bool ≠ int
    assert not PS.potvrdi_izvod(ZAPISNIK, sha, b, a, x["izvod"])


def test_izlaz_modela_nema_ulaz_u_ugovor():
    """Ulaz: redovi dokumenata i potvrde vrste iz audit traga; nema parametra za tvrdnje modela, Genome ni dokaze."""
    assert list(inspect.signature(PS.utvrdi).parameters) == ["dokumenti", "predmet_id", "user_id", "neprocitani",
                                                             "potvrde_vrste"]
    st = _st(_d("DOK-07", ZAPISNIK, tip_dokaza="response", tvrdnje=["Sud je ukinuo nalog."]))
    assert all("ukinuo" not in x["izvod"] for x in st["dogadjaji"]) and _sud(st, "SUD_PRIHVATA")


def test_tudji_predmet_ili_korisnik_se_odbacuje_a_prazan_identitet_je_greska():
    st = PS.utvrdi([{**_d("DOK-07", ZAPISNIK), "user_id": "user-B"}, {**_d("DOK-08", ZAPISNIK), "predmet_id": "drugi"}],
                   predmet_id=P, user_id=U)
    assert st["dogadjaji"] == [] and st["odbaceni"] == ["DOK-07", "DOK-08"]
    for p, u in ((P, None), (None, U), (P, "")):
        with pytest.raises(ValueError):
            PS.utvrdi([_d("DOK-07", ZAPISNIK)], predmet_id=p, user_id=u)


def test_potvrda_vrste_samo_iz_audit_traga_ai_tags_se_ne_koristi():
    bez_naslova = "Sud prihvata predlog za dopunu vestacenja."
    lazni_tag = {"_vrsta_advokat": {"tip": "court_decision", "akter": U, "izvor": "predmet"}}
    [z] = _st(_d("DOK-09", bez_naslova, ai_tags=lazni_tag, tip_dokaza="court_decision"))["dogadjaji"]
    assert z["akter"] == "NEPOZNAT"                                           # ai_tags/tip_dokaza ne potvrđuju ništa
    [x] = _st(_d("DOK-09", bez_naslova), potvrde_vrste={"id-DOK-09": "court_decision"})["dogadjaji"]
    assert (x["akter"], x["vrsta"], x["vrsta_dokumenta"]["osnov"], x["vrsta_dokumenta"]["klasa"]) == \
        ("SUD", "SUD_PRIHVATA", "ADVOKAT", PS.HUMAN)
    assert x["klasa_tumacenja"] == PS.UNKNOWN                                 # rečenica je i dalje obrazac
    podnesak = _ZAGLAVLJE + "PODNESAK TUZENOG (SINTETICKI PREDMET)\nSud prihvata predlog za dopunu vestacenja."
    st = _st(_d("DOK-10", podnesak), potvrde_vrste={"id-DOK-10": "court_decision"})
    [y] = st["dogadjaji"]
    assert y["klasa_tumacenja"] == PS.CONTESTED and y["vrsta_dokumenta"]["klasa"] == PS.CONTESTED
    assert _nep(st, "vrsta dokumenta sporna")


def test_ocr_prelom_recenice_je_jedan_izvod_tacno_iz_teksta():
    t = ZAPISNIK.replace("Sud prihvata predlog za dopunu vestacenja.", "Sud prihvata predlog za dopunu\nvestacenja.")
    [x] = _sud(_st(_d("DOK-07", t)), "SUD_PRIHVATA")
    assert x["izvod"] == "Sud prihvata predlog za dopunu\nvestacenja." and t[x["pocetak"]:x["kraj"]] == x["izvod"]


def test_neprocitani_dokumenti_cine_stanje_nepotpunim():
    st = _st(_d("DOK-07", ZAPISNIK), neprocitani=["DOK-01", "DOK-02"])
    assert st["potpunost"] == "NEPOTPUNO" and _nep(st, "DOK-01, DOK-02")


@pytest.mark.parametrize("naslov,akter", [("ZAPISNIK SA ROCISTA", "SUD"), ("RESENJE", "SUD"), ("1. REŠENJE", "SUD"),
                                          ("PODNESAK TUZIOCA", "TUZILAC"), ("ODGOVOR NA TUZBU", "STRANKA"),
                                          ("IZJASNJENJE TUZENOG NA NALAZ VESTAKA", "TUZENI"),
                                          ("NALAZ | MISLJENJE VESTAKA", "VESTAK"), ("DOPIS", "NEPOZNAT"),
                                          ("Veza: resenje br. 5", "NEPOZNAT")])
def test_vrsta_po_naslovu(naslov, akter):
    assert PS.vrsta_dokumenta(_ZAGLAVLJE + naslov + "\nTekst.")["akter"] == akter
