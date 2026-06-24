# -*- coding: utf-8 -*-
"""
Deterministic mapping from blockchain event types to Serbian law.
Pokriva: ZOO (primarno), ZDI, ZSPNFT, ZPDG.
Zero AI — pure lookup tables. Unknown event type raises ValueError immediately.
"""
from __future__ import annotations

from typing import get_args

from .interfaces import BlockchainEvent, EventType, LegalMapping

# ── ZOO — primarna tabela (obligacioni odnosi) ────────────────────────────────
# Svaki EventType mora biti ovde — compile-time check ispod.

MAPPING_TABLE: dict[str, LegalMapping] = {
    "transfer": LegalMapping(
        pravna_kategorija = "obligacioni_odnos",
        zakon             = "ZOO",
        clan              = 262,
        opis              = (
            "Prenos imovine — nastanak obligacionog odnosa. "
            "Poverilac ima pravo zahtevati ispunjenje obaveze (čl. 262 ZOO)."
        ),
    ),
    "payment_failed": LegalMapping(
        pravna_kategorija = "neispunjenje_novcane_obaveze",
        zakon             = "ZOO",
        clan              = 262,
        opis              = (
            "Neuspešna uplata — pravo na ispunjenje ili naknadu štete. "
            "Dužnik je u docnji i odgovara za posledice (čl. 262, 277 ZOO)."
        ),
    ),
    "contract_call": LegalMapping(
        pravna_kategorija = "ugovorna_obaveza",
        zakon             = "ZOO",
        clan              = 124,
        opis              = (
            "Izvršenje ugovorne obaveze putem pametnog ugovora. "
            "Neispunjenje daje osnov za raskid i naknadu štete (čl. 124 ZOO)."
        ),
    ),
    "approval": LegalMapping(
        pravna_kategorija = "ovlascenje_za_raspolaganje",
        zakon             = "ZOO",
        clan              = 88,
        opis              = (
            "Odobrenje za raspolaganje digitalnom imovinom. "
            "Punomoćje za specifičnu transakciju (čl. 88 ZOO)."
        ),
    ),
    "mint": LegalMapping(
        pravna_kategorija = "kreiranje_digitalnog_dobra",
        zakon             = "ZOO",
        clan              = 19,
        opis              = (
            "Kreiranje novog digitalnog dobra (NFT/token). "
            "Nastanak imovinskog prava i obaveze dostave (čl. 19 ZOO)."
        ),
    ),
    "burn": LegalMapping(
        pravna_kategorija = "unistavanje_digitalnog_dobra",
        zakon             = "ZOO",
        clan              = 360,
        opis              = (
            "Trajno uništavanje digitalnog dobra. "
            "Prestanak imovinskog prava — raskid token-ugovora (čl. 360 ZOO)."
        ),
    ),
    # Razmena digitalne imovine za robu/usluge — primarni pravni osnov je ZOO čl. 557
    # (ugovor o razmeni). ZDI ne zabranjuje razmenu, zabranjuje samo zakonsko sredstvo plaćanja.
    "barter_exchange": LegalMapping(
        pravna_kategorija = "ugovor_o_razmeni_digitalna_imovina",
        zakon             = "ZOO",
        clan              = 557,
        opis              = (
            "Ugovor o razmeni (trampa) digitalne imovine za robu ili usluge. "
            "ZOO čl. 557: svaka ugovorna strana se obavezuje da drugoj prenese pravo "
            "svojine na određenoj stvari. Digitalna imovina se tretira kao 'stvar' u "
            "smislu ZOO. ZDI čl. 91 zabranjuje samo zakonsko sredstvo plaćanja — "
            "ne zabranjuje barter. Uslov: transakcija mora proći kroz licenciranog "
            "VASP pružaoca usluga (čl. 29 ZDI)."
        ),
    ),
    # Prekogranični prenos digitalne imovine — primarno reguliše ZDP.
    "cross_border_transfer": LegalMapping(
        pravna_kategorija = "prekogranican_prenos_digitalne_imovine",
        zakon             = "ZDP",
        clan              = 5,
        opis              = (
            "Prekogranični prenos digitalne imovine ka/iz inostranstva. "
            "ZDP čl. 5: tekuće transakcije po osnovu robe/usluga su slobodne. "
            "ZDP čl. 18: obaveza izveštavanja NBS za kapitalne transakcije. "
            "ZDI čl. 29: VASP licenca obavezna za pružaoca u transakciji. "
            "ZSPNFT čl. 37: AML praćenje prekograničnih tokova digitalne imovine."
        ),
    ),
}

# ── ZDI — Zakon o digitalnoj imovini ─────────────────────────────────────────
# Pokriva event_type-ove gde se primenjuje ZDI.

ZDI_TABLE: dict[str, LegalMapping] = {
    "transfer": LegalMapping(
        pravna_kategorija = "pruzanje_usluga_digitalne_imovine",
        zakon             = "ZDI",
        clan              = 29,
        opis              = (
            "Prenos digitalne imovine — obaveza licenciranja pružaoca usluga. "
            "Nelicencirani prenos može povući administrativnu odgovornost (čl. 29 ZDI)."
        ),
    ),
    "contract_call": LegalMapping(
        pravna_kategorija = "ugovorna_obaveza_digitalna_imovina",
        zakon             = "ZDI",
        clan              = 29,
        opis              = (
            "Izvršenje usluge digitalne imovine kroz pametni ugovor. "
            "Zahteva se licenca i ispunjenje tehničkih uslova (čl. 29 ZDI)."
        ),
    ),
    "approval": LegalMapping(
        pravna_kategorija = "ovlascenje_digitalna_imovina",
        zakon             = "ZDI",
        clan              = 29,
        opis              = (
            "Odobrenje za raspolaganje digitalnom imovinom trećem licu. "
            "Pružalac usluga mora biti licenciran (čl. 29 ZDI)."
        ),
    ),
    "mint": LegalMapping(
        pravna_kategorija = "izdavanje_digitalne_imovine",
        zakon             = "ZDI",
        clan              = 9,
        opis              = (
            "Kreiranje (izdavanje) nove digitalne imovine. "
            "Obavezan beli papir i odobrenje regulatora (čl. 9 ZDI)."
        ),
    ),
    "burn": LegalMapping(
        pravna_kategorija = "definicija_digitalne_imovine",
        zakon             = "ZDI",
        clan              = 2,
        opis              = (
            "Trajno uklanjanje digitalne imovine iz opticaja. "
            "Mora biti usklađeno sa definicijom i pravilima (čl. 2 ZDI)."
        ),
    ),
    "barter_exchange": LegalMapping(
        pravna_kategorija = "razmena_digitalne_imovine_dozvoljena",
        zakon             = "ZDI",
        clan              = 2,
        opis              = (
            "Digitalna imovina se može 'zamenjivati' prema definiciji čl. 2 ZDI. "
            "Čl. 91 ZDI zabranjuje SAMO upotrebu kao zakonsko sredstvo plaćanja — "
            "barter je dozvoljen. Obavezno: korišćenje licenciranog VASP pružaoca "
            "za konverziju u/iz dinara (čl. 29 ZDI)."
        ),
    ),
    "cross_border_transfer": LegalMapping(
        pravna_kategorija = "prekogranican_prenos_vasp_licenca",
        zakon             = "ZDI",
        clan              = 29,
        opis              = (
            "Prekogranični prenos digitalne imovine zahteva učešće licenciranog VASP "
            "pružaoca usluga (čl. 29 ZDI). Nelicencirani prenos može povući "
            "administrativnu odgovornost prema NBS/KHoV."
        ),
    ),
}

# ── ZDP — Zakon o deviznom poslovanju ─────────────────────────────────────────
# Primenjuje se na prekogranične transakcije s digitalnom imovinom.
# Lex specialis za devizni aspekt cross_border_transfer; sekundarni za barter_exchange.

ZDP_TABLE: dict[str, LegalMapping] = {
    "cross_border_transfer": LegalMapping(
        pravna_kategorija = "devizna_transakcija_inostranstvo",
        zakon             = "ZDP",
        clan              = 5,
        weight            = 8,
        opis              = (
            "Tekuća devizna transakcija sa inostranstvom po osnovu robe/usluga slobodna je. "
            "Kompanija iz Srbije koja šalje digitalnu imovinu inostranstvu (ili prima) "
            "po osnovu ugovora o razmeni može to tretirati kao tekuću transakciju (čl. 5 ZDP). "
            "Kapitalne transakcije (investicije, zajmovi) zahtevaju saglasnost NBS (čl. 18 ZDP). "
            "ZDP je lex specialis za devizni aspekt — ima prednost nad ZOO za prekogranično."
        ),
    ),
    "barter_exchange": LegalMapping(
        pravna_kategorija = "devizni_aspekt_razmene",
        zakon             = "ZDP",
        clan              = 5,
        weight            = 8,
        opis              = (
            "Barter ugovor između srpske kompanije i inostrane kompanije može biti "
            "tekuća devizna transakcija (čl. 5 ZDP) ako se radi o razmeni robe/usluga. "
            "Evidencija i izveštavanje NBS obavezni. VASP posrednik kroz koga prolaze "
            "dinari je sam obveznik deviznih propisa."
        ),
    ),
}

# ── ZSPNFT — Zakon o sprečavanju pranja novca i finansiranja terorizma ───────
# weight=10: ZSPNFT je LEX SPECIALIS za AML obaveze — uvek primaran nad ZDI i ZOO

ZSPNFT_TABLE: dict[str, LegalMapping] = {
    "transfer": LegalMapping(
        pravna_kategorija = "pracenje_transakcija_aml",
        zakon             = "ZSPNFT",
        clan              = 37,
        weight            = 10,
        opis              = (
            "Prenos digitalne imovine podleže AML praćenju. "
            "Obveznik mora pratiti transakcije radi otkrivanja neobičnih obrazaca (čl. 37 ZSPNFT). "
            "ZSPNFT je lex specialis — ima prednost nad ZDI i ZOO za AML obaveze."
        ),
    ),
    "payment_failed": LegalMapping(
        pravna_kategorija = "sumnjiva_transakcija_aml",
        zakon             = "ZSPNFT",
        clan              = 47,
        weight            = 10,
        opis              = (
            "Neuspela transakcija može biti indikator pranja novca. "
            "Obaveza prijave APML — rok 3 radna dana od sticanja saznanja (čl. 47 ZSPNFT). "
            "Nadzor: APML za AML monitoring; NBS/KHoV za licenciranje VASP subjekta."
        ),
    ),
    "contract_call": LegalMapping(
        pravna_kategorija = "kyc_obaveze_pametni_ugovor",
        zakon             = "ZSPNFT",
        clan              = 7,
        weight            = 10,
        opis              = (
            "Poziv pametnog ugovora zahteva identifikaciju stranaka. "
            "KYC obaveza obveznika pre izvršenja transakcije (čl. 7 ZSPNFT). "
            "Kvalifikacija VASP subjekta vrši se prema čl. 2 ZDI (sekundarni izvor)."
        ),
    ),
    "mint": LegalMapping(
        pravna_kategorija = "kyc_pri_izdavanju",
        zakon             = "ZSPNFT",
        clan              = 7,
        weight            = 10,
        opis              = (
            "Izdavanje digitalne imovine zahteva identifikaciju primalaca. "
            "Obvezna dubinska analiza korisnika (čl. 7 ZSPNFT). "
            "Prag identifikacije: ≥ 15.000 EUR u gotovini ili ekvivalentu (ZSPNFT čl. 9)."
        ),
    ),
    "barter_exchange": LegalMapping(
        pravna_kategorija = "kyc_pri_razmeni",
        zakon             = "ZSPNFT",
        clan              = 7,
        weight            = 10,
        opis              = (
            "Razmena digitalne imovine za robu/usluge zahteva KYC identifikaciju. "
            "Licencirani VASP posrednik je obveznik — mora sprovoditi dubinsku analizu "
            "obe ugovorne strane (čl. 7 ZSPNFT). Prag: ≥ 15.000 EUR ekvivalent (čl. 9 ZSPNFT)."
        ),
    ),
    "cross_border_transfer": LegalMapping(
        pravna_kategorija = "aml_pracenje_prekogranican",
        zakon             = "ZSPNFT",
        clan              = 37,
        weight            = 10,
        opis              = (
            "Prekogranični prenos digitalne imovine podleže pojačanom AML praćenju. "
            "Obveznik prati obrazac transakcija sa inostranstvom (čl. 37 ZSPNFT). "
            "Transakcije sa jurisdikcijama visokog rizika podležu pojačanoj "
            "dubinskoj analizi (čl. 8 ZSPNFT)."
        ),
    ),
}

# ── ZPDG — Zakon o porezu na dohodak građana ─────────────────────────────────

ZPDG_TABLE: dict[str, LegalMapping] = {
    "transfer": LegalMapping(
        pravna_kategorija = "oporezivanje_prihoda_digitalna_imovina",
        zakon             = "ZPDG",
        clan              = 72,
        opis              = (
            "Prenos digitalne imovine može biti oporeziv događaj. "
            "Prihodi od prenosa oporezuju se po stopi od 15% (čl. 72b ZPDG)."
        ),
    ),
    "mint": LegalMapping(
        pravna_kategorija = "prihod_od_izdavanja",
        zakon             = "ZPDG",
        clan              = 72,
        opis              = (
            "Prihod od kreiranja i prodaje digitalne imovine je oporeziv. "
            "Kapitalna dobit se obračunava prema čl. 72v ZPDG."
        ),
    ),
    "burn": LegalMapping(
        pravna_kategorija = "gubitak_kapitala",
        zakon             = "ZPDG",
        clan              = 72,
        opis              = (
            "Uništavanje digitalne imovine može generisati poreski gubitak. "
            "Kapitalni gubitak se može preneti na naredni period (čl. 72v ZPDG)."
        ),
    ),
    # Razmena digitalne imovine za robu/usluge — oporeziv događaj
    "barter_exchange": LegalMapping(
        pravna_kategorija = "prihod_od_razmene_digitalne_imovine",
        zakon             = "ZPDG",
        clan              = 72,
        opis              = (
            "Kompanija koja primi digitalnu imovinu za pruženu uslugu ili robu "
            "ostvaruje prihod koji je oporeziv. Vrednost u RSD se utvrđuje na dan "
            "transakcije. Kompanija koja daje digitalnu imovinu realizuje kapitalnu "
            "dobit/gubitak (čl. 72b/72v ZPDG). Obaveza: samooporezivanje — obveznik "
            "sam obračunava i plaća porez."
        ),
    ),
}

# ── Compile-time check: svaki EventType mora biti u MAPPING_TABLE ─────────────

_MISSING = set(get_args(EventType)) - set(MAPPING_TABLE)
if _MISSING:
    raise RuntimeError(
        f"MAPPING_TABLE nije exhaustive — nedostaju: {_MISSING}. "
        f"Dodajte unose pre nastavka."
    )

# Agregirana tabela svih zakona (ZDP dodat za devizni aspekt)
_ALL_TABLES: list[dict[str, LegalMapping]] = [
    MAPPING_TABLE,
    ZDI_TABLE,
    ZDP_TABLE,
    ZSPNFT_TABLE,
    ZPDG_TABLE,
]

# AML/Compliance kontekst ključne reči — aktiviraju ZSPNFT prioritet
_AML_KEYWORDS: frozenset[str] = frozenset([
    "aml", "kyc", "pranje", "pranja", "compliance", "sumnjiva",
    "obveznik", "identifikacija", "dubinska analiza", "finansiranje terorizma",
    "str prijava", "apml", "zspnft",
    # Dodatne ključne reči za prekogranične kripto transakcije
    "inostranstvo", "devizn", "nbs saglasnost", "cross_border",
])


def _je_aml_kontekst(query: str) -> bool:
    """Detektuje da li upit spada u AML/Compliance kontekst."""
    q = query.lower()
    return any(kw in q for kw in _AML_KEYWORDS)


class LegalMapper:
    """
    Maps blockchain events to Serbian law — ZOO (primary) + ZDI, ZSPNFT, ZPDG.

    Hijerarhija za AML/Compliance:
      ZSPNFT (lex specialis, weight=10) > ZDI (sekundarni — samo za VASP def.) > ZOO (lex generalis)
    """

    def map(self, event: BlockchainEvent) -> LegalMapping:
        """
        Vraća primarni ZOO LegalMapping za dati event_type.

        Raises:
            ValueError: event.event_type nije u MAPPING_TABLE.
        """
        result = MAPPING_TABLE.get(event.event_type)
        if result is None:
            raise ValueError(
                f"Nepoznat event_type {event.event_type!r}. "
                f"Dostupni tipovi: {list(MAPPING_TABLE)}. "
                f"Azurirajte MAPPING_TABLE u legal_mapper.py."
            )
        return result

    def map_all_laws(
        self,
        event: BlockchainEvent,
        aml_context: bool = False,
    ) -> list[LegalMapping]:
        """
        Vraća sve primenljive LegalMapping objekte iz sva 4 zakona.

        Bez AML konteksta — redosled: ZOO, ZDI, ZSPNFT, ZPDG.
        Sa AML kontekstom — ZSPNFT (weight=10) na vrhu, ZDI sekundarno,
        ZOO se isključuje (nije relevantan za AML obaveze).
        """
        result = []
        for table in _ALL_TABLES:
            mapping = table.get(event.event_type)
            if mapping is not None:
                result.append(mapping)

        if aml_context:
            # Isključi ZOO (lex generalis — ne primenjuje se za AML)
            result = [m for m in result if m.zakon != "ZOO"]
            # Sortiraj: viši weight = primarni (ZSPNFT=10 > ZDI/ZPDG=1)
            result.sort(key=lambda m: m.weight, reverse=True)

        return result

    def map_aml_priority(self, event: BlockchainEvent) -> list[LegalMapping]:
        """
        Convenience metoda — uvek koristi AML hijerarhiju.
        ZSPNFT je primarni izvor, ZDI sekundarni (samo za VASP definiciju).
        """
        return self.map_all_laws(event, aml_context=True)
