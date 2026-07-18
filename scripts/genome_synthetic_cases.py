# -*- coding: utf-8 -*-
"""
Synthetic calibration batch (Faza 1 Reality Validation, 2026-07-18) — 6
constructed Serbian legal scenarios with deliberate ground truth and
deliberate complexity, per founder's explicit requirements:
conflicting facts, incomplete evidence, timeline ambiguity, mixed weak/
strong evidence. NOT real cases — used only to calibrate the pipeline
before a real-anonymized-matters batch.

Each case's GROUND_TRUTH is the answer key used for manual grading against
CASE_GENOME_REALITY_VALIDATION_REPORT.md's 6 measured dimensions. Kept in
this file (not committed data, script itself is fine to commit as a
reusable pattern for the real-matters batch) — the case CONTENT below is
entirely fictional.
"""
import asyncio
from pathlib import Path

from genome_case_dna_evaluate import run_batch

FOUNDER_USER_ID = "384a7149-938b-4b83-99e0-8d7524e0581a"
FOUNDER_EMAIL = "benny13.n@gmail.com"

CASES = [
    {
        "label": "CASE-A",
        "naziv": "[KALIBRACIJA] Otkaz ugovora o radu — Petrović protiv DOO Sever",
        "opis": "Sintetički test slučaj — radni spor, sukobljeni razlozi otkaza",
        "tip": "radni_spor",
        "documents": [
            {"filename": "resenje_o_otkazu.docx", "paragraphs": [
                "REŠENJE O OTKAZU UGOVORA O RADU",
                "Poslodavac DOO Sever otkazuje ugovor o radu zaposlenom Marku Petroviću, "
                "sa danom prestanka radnog odnosa 15.02.2026. godine.",
                "Razlog otkaza: narušavanje radne discipline — zaposleni je dana 03.02.2026. "
                "godine odbio da izvrši nalog nadređenog i napustio radno mesto pre isteka smene.",
                "Zaposlenom se ne dostavlja prethodno obaveštenje o razlozima za otkaz niti mu se "
                "ostavlja rok za izjašnjenje, s obzirom da poslodavac smatra povredu očiglednom.",
                "Pravna pouka: zaposleni ima pravo žalbe u roku od 15 dana.",
            ]},
            {"filename": "zalba_zaposlenog.docx", "paragraphs": [
                "ŽALBA NA REŠENJE O OTKAZU",
                "Ja, Marko Petrović, izjavljujem žalbu na rešenje o otkazu od 15.02.2026.",
                "Navodim da mi nikada nije dostavljeno obaveštenje o razlozima za otkaz niti mi je "
                "ostavljen rok od 8 dana da se izjasnim, što je poslodavac dužan da učini prema "
                "Zakonu o radu pre donošenja rešenja o otkazu.",
                "Takođe navodim da sam 03.02.2026. napustio radno mesto isključivo zbog iznenadne "
                "zdravstvene tegobe, o čemu sam usmeno obavestio kolegu Nikolu Jovanovića.",
                "Prilažem potvrdu Doma zdravlja o poseti dana 03.02.2026. u 14:20h.",
            ]},
            {"filename": "interna_beleska_hr.docx", "paragraphs": [
                "INTERNA BELEŠKA — Sektor ljudskih resursa",
                "Datum: 10.02.2026.",
                "Napomena za internu evidenciju: stvarni razlog za prestanak radnog odnosa "
                "zaposlenog Marka Petrovića je smanjenje obima posla u sektoru proizvodnje, "
                "usled čega se ukida jedno radno mesto.",
                "Disciplinski razlog naveden u rešenju je formalne prirode i koristi se radi "
                "izbegavanja isplate otpremnine po osnovu tehnološkog viška.",
                "Ovaj dokument nije za spoljnu upotrebu.",
            ]},
        ],
    },
    {
        "label": "CASE-B",
        "naziv": "[KALIBRACIJA] Isporuka neispravne robe — Agrocentar protiv MetalProm",
        "opis": "Sintetički test slučaj — ugovorni spor, kompletan dosije, slab dokaz namerno uključen",
        "tip": "ugovorni_spor",
        "documents": [
            {"filename": "ugovor_o_prodaji.docx", "paragraphs": [
                "UGOVOR O PRODAJI ROBE br. 44/2025",
                "Prodavac: MetalProm DOO. Kupac: Agrocentar DOO.",
                "Predmet ugovora: isporuka 500 metalnih profila tipa MP-200, kvaliteta prema "
                "standardu SRPS EN 10025, u roku od 30 dana od uplate avansa.",
                "Cena: 2.400.000,00 RSD. Garancija kvaliteta: 12 meseci od isporuke.",
                "Član 8: Kupac je dužan da reklamaciju istakne u roku od 8 dana od prijema robe, "
                "u suprotnom gubi pravo na reklamaciju.",
            ]},
            {"filename": "zapisnik_o_reklamaciji.docx", "paragraphs": [
                "ZAPISNIK O REKLAMACIJI",
                "Datum prijema robe: 12.01.2026. Datum reklamacije: 18.01.2026. (u roku od 8 dana).",
                "Kupac Agrocentar DOO konstatuje da je 62 od 500 isporučenih profila vidno "
                "deformisano i ne odgovara specifikaciji SRPS EN 10025.",
                "Roba je fotografisana i uskladištena odvojeno, na raspolaganju za veštačenje.",
            ]},
            {"filename": "vestacenje.docx", "paragraphs": [
                "NALAZ I MIŠLJENJE VEŠTAKA — mašinske struke",
                "Veštak je pregledao 62 sporna profila. Utvrđeno je vidno savijanje na krajevima "
                "profila, u meri koja prelazi dozvoljena odstupanja standarda SRPS EN 10025.",
                "Uzrok deformacije se sa sigurnošću ne može utvrditi isključivo vizuelnim pregledom — "
                "deformacija je tipična kako za greške u proizvodnji tako i za neadekvatno "
                "rukovanje robom tokom transporta. Za definitivan zaključak bilo bi potrebno "
                "uvid u dokumentaciju prevoznika, koja nije bila dostupna veštaku.",
                "Veštak ne može sa sigurnošću isključiti da je deformacija nastala u transportu.",
            ]},
        ],
    },
    {
        "label": "CASE-C",
        "naziv": "[KALIBRACIJA] Naknada štete iz saobraćajne nezgode — Ilić protiv NN vozača",
        "opis": "Sintetički test slučaj — namerna vremenska neusaglašenost između svedoka",
        "tip": "naknada_stete",
        "documents": [
            {"filename": "policijski_zapisnik.docx", "paragraphs": [
                "ZAPISNIK O UVIĐAJU SAOBRAĆAJNE NEZGODE",
                "Datum i vreme nezgode: 03.03.2026. godine, oko 18:40h.",
                "Mesto: raskrsnica ulica Bulevar oslobođenja i Cara Dušana.",
                "Učesnici: Jovan Ilić (pešak, povređen) i vozilo NN vozača koje se udaljilo sa "
                "lica mesta pre dolaska policije.",
                "Konstatovane povrede: prelom potkolenice, površinske posekotine.",
            ]},
            {"filename": "medicinski_izvestaj.docx", "paragraphs": [
                "MEDICINSKI IZVEŠTAJ — Urgentni centar",
                "Pacijent Jovan Ilić primljen 05.03.2026. na dalje lečenje preloma potkolenice "
                "zadobijenog u saobraćajnoj nezgodi.",
                "Terapija: gips, fizikalna terapija u trajanju od 6 nedelja. Procenjena privremena "
                "nesposobnost za rad: 8 nedelja.",
            ]},
            {"filename": "izjava_svedoka_1.docx", "paragraphs": [
                "IZJAVA SVEDOKA — Ana Marković",
                "Izjavljujem da sam bila prisutna kada se dogodila nezgoda, otprilike početkom "
                "marta, u večernjim satima. Videla sam vozilo tamne boje kako se udaljava velikom "
                "brzinom neposredno nakon udara pešaka.",
            ]},
            {"filename": "izjava_svedoka_2.docx", "paragraphs": [
                "IZJAVA SVEDOKA — Dragan Simić",
                "Izjavljujem da sam prisustvovao saobraćajnoj nezgodi na pomenutoj raskrsnici "
                "krajem februara meseca 2026. godine, u večernjim satima. Sećam se da je pešak "
                "zadobio povrede noge.",
            ]},
        ],
    },
    {
        "label": "CASE-D",
        "naziv": "[KALIBRACIJA] Sporna zaostavština — naslednici Nikolić",
        "opis": "Sintetički test slučaj — nasledstvo, jak pisani dokaz naspram slabe usmene tvrdnje",
        "tip": "nasledstvo",
        "documents": [
            {"filename": "testament.docx", "paragraphs": [
                "TESTAMENT",
                "Ja, Radoslav Nikolić, pri punoj svesti, sačinjavam ovaj testament dana "
                "10.09.2025. godine, overen kod javnog beležnika pod brojem OPU 1188/2025.",
                "Svu svoju nepokretnu imovinu — stan u ulici Kneza Miloša 22 — ostavljam u "
                "celosti svojoj ćerki Milici Nikolić.",
                "Svoju pokretnu imovinu (automobil i ušteđevinu) ostavljam sinu Draganu Nikoliću.",
            ]},
            {"filename": "izvod_umrlih.docx", "paragraphs": [
                "IZVOD IZ MATIČNE KNJIGE UMRLIH",
                "Radoslav Nikolić, preminuo 02.01.2026. godine.",
            ]},
            {"filename": "izjava_naslednika.docx", "paragraphs": [
                "IZJAVA — Dragan Nikolić",
                "Izjavljujem da mi je otac usmeno, otprilike mesec dana pre smrti, obećao da će "
                "mi ostaviti i polovinu stana, jer je testament navodno sačinio 'u žurbi' i "
                "nameravao je da ga izmeni.",
                "Ne postoji pisani dokaz o ovom razgovoru niti su prisutni bili drugi svedoci.",
            ]},
        ],
    },
    {
        "label": "CASE-E",
        "naziv": "[KALIBRACIJA] Reklamacija kućnog aparata — Vasić protiv TehnoMarket",
        "opis": "Sintetički test slučaj — namerno oskudan dosije, samo jedan dokument",
        "tip": "potrosacki_spor",
        "documents": [
            {"filename": "prigovor_emailom.docx", "paragraphs": [
                "PRIGOVOR POTROŠAČA — imejl prepiska",
                "Poštovani, kupio sam veš mašinu u vašoj prodavnici pre otprilike dva meseca i "
                "ona je prestala da radi nakon svega tri korišćenja. Tražim zamenu ili povraćaj "
                "novca. Očekujem odgovor u zakonskom roku.",
                "Srdačno, Petar Vasić.",
            ]},
        ],
    },
    {
        "label": "CASE-F",
        "naziv": "[KALIBRACIJA] Uznemiravanje na radnom mestu — Todorović protiv DOO Vektor",
        "opis": "Sintetički test slučaj — mešavina svih vrsta složenosti",
        "tip": "radni_spor",
        "documents": [
            {"filename": "prijava_uznemiravanja.docx", "paragraphs": [
                "PRIJAVA UZNEMIRAVANJA NA RADU (MOBING)",
                "Podnosilac: Jelena Todorović. Datum podnošenja: 20.01.2026.",
                "Navodim da me je neposredni rukovodilac Vladimir Rakić tokom perioda "
                "novembar-decembar 2025. godine sistematski ponižavao pred kolegama, dodeljivao "
                "mi zadatke ispod mog nivoa kvalifikacija i isključivao me sa sastanaka tima.",
            ]},
            {"filename": "email_prepiska.docx", "paragraphs": [
                "PREPISKA — interni imejl, decembar 2025.",
                "Kolegica Snežana Pavlović piše: 'Primetila sam da Jelena poslednjih meseci nije "
                "pozivana na jutarnje sastanke, što je neuobičajeno za njenu poziciju.'",
                "U istom nizu poruka, kolega Miloš Đurić odgovara: 'Nisam siguran da je to tačno, "
                "koliko znam Jelena je sama tražila da ne prisustvuje sastancima tog perioda zbog "
                "drugih obaveza.'",
            ]},
            {"filename": "medicinska_dokumentacija.docx", "paragraphs": [
                "MEDICINSKA DOKUMENTACIJA — Specijalista psihijatrije",
                "Pacijentkinja Jelena Todorović se od januara 2026. leči zbog anksioznog "
                "poremećaja koji dovodi u vezu sa dugotrajnim stresom na radnom mestu.",
                "Dijagnoza i tok terapije detaljno dokumentovani u kartonu pacijenta.",
            ]},
            {"filename": "hr_sazetak.docx", "paragraphs": [
                "SAŽETAK — Sektor ljudskih resursa",
                "Primljena je prijava zaposlene. Predmet je prosleđen na dalje postupanje.",
            ]},
        ],
    },
]


async def main():
    out_dir = str(Path(r"C:\Users\Benny\AppData\Local\Temp\claude\C--Users-Benny-moj-prvi-agent-src-moj-prvi-agent-legal-agent\a26c3276-a058-4f42-83db-9d5b4b88b07a\scratchpad") / "genome_synthetic_calibration")
    await run_batch(CASES, FOUNDER_USER_ID, FOUNDER_EMAIL, out_dir)


if __name__ == "__main__":
    asyncio.run(main())
