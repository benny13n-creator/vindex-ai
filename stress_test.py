# -*- coding: utf-8 -*-
"""
Vindex AI — Stres test II (teški slučajevi)
Pokretanje: PYTHONIOENCODING=utf-8 C:/Python311/python.exe stress_test.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from main import ask_agent

PITANJA = [
    # 1. ZKP zamka — tajno snimanje
    (
        "ZKP_tajno_snimanje",
        "Okrivljeni je tajno snimio razgovor sa svedokom bez njegovog znanja i to snimanje želi da upotrebi kao dokaz u krivičnom postupku. "
        "Da li je to zakonit dokaz po ZKP Srbije i može li se presuda zasnovati isključivo na njemu?"
    ),
    # 2. Katastar / ozakonjenje — zabrana otuđenja
    (
        "Katastar_ozakonjenje_zabrana",
        "Investitor je ozakonio objekat po Zakonu o ozakonjenju, ali na nepokretnosti postoji zabrana otuđenja upisana u korist banke. "
        "Da li Republički geodetski zavod može odbiti upis i koji pravni lek ima vlasnik?"
    ),
    # 3. Stečaj + hipoteka — redosled naplate radnika
    (
        "Stecaj_hipoteka_radnici",
        "Firma je u stečaju. Celokupna imovina je pod hipotekim obezbeđenjem u korist banke. "
        "Radnici imaju neisplaćene zarade za 6 meseci. Ko ima prioritet u naplati — banka ili radnici, "
        "i koji zakon reguliše ovaj redosled?"
    ),
    # 4. Nasledno pravo — uračunavanje poklona u nužni deo
    (
        "Nasledje_poklon_nuzni_deo",
        "Ostavilac je za života poklonio jednom od naslednika stan vrednosti 100.000 EUR. "
        "Drugi naslednik (nužni naslednik) traži uračunavanje tog poklona u nužni deo. "
        "Koji je rok za podnošenje tužbe za smanjenje raspolaganja i od kog trenutka teče?"
    ),
    # 5. Kripto / digitalna imovina — porez
    (
        "Kripto_porez_Srbija",
        "Fizičko lice je kupilo Bitcoin 2020. godine i prodalo ga 2024. sa profitom od 50.000 EUR. "
        "Koji porez plaća u Srbiji, koja je stopa, koji organ je nadležan i koji je rok za prijavu?"
    ),
    # 6. Ćutanje administracije — drugostepeni postupak
    (
        "Cutanje_administracije_drugostepen",
        "Stranka je izjavila žalbu na prvostepeno rešenje. Drugostepeni organ nije doneo rešenje u zakonskom roku. "
        "Koja je tačna procedura — da li se podnosi tužba upravnom sudu, prigovor, ili nešto treće? "
        "Koji zakon i koji rok važi?"
    ),
    # 7. ZPP — neuredna tužba vs. odbacivanje
    (
        "ZPP_neuredna_tuzba",
        "Sud je doneo rešenje o odbacivanju tužbe zbog neurednosti, a tužilac tvrdi da je dostavio sve "
        "potrebne priloge. Koji pravni lek ima — žalba ili prigovor — u kom roku i kojim sudom?"
    ),
    # 8. Porodični zakon — starateljstvo stranac
    (
        "Porodicni_starateljstvo_stranac",
        "Roditelji stranog državljanina su razveli brak u Srbiji. Jedan roditelj želi da odnese dete u inostranstvo. "
        "Koji sud je nadležan, koji zakon se primenjuje i šta je 'privremena mera' kojom se to sprečava?"
    ),
    # 9. Obligaciono pravo — raskid ugovora zbog više sile
    (
        "Obligaciono_visa_sila_raskid",
        "Ugovor o građenju je prekinut zbog elementarne nepogode (poplava). "
        "Izvođač radova traži naknadu troškova koje je imao pre prekida. "
        "Da li ima pravo i koji je rok za podnošenje zahteva?"
    ),
    # 10. Krivično — zastarelost krivičnog gonjenja
    (
        "KZ_zastarelost_gonjenja",
        "Učinilac je 2010. izvršio krivično delo za koje je zaprećena kazna do 5 godina zatvora. "
        "Krivična prijava podneta je 2024. Da li je nastupila zastarelost krivičnog gonjenja i koji zakon reguliše rokove?"
    ),
    # 11. Autorsko pravo — plagijat softvera
    (
        "Autorsko_plagijat_softvera",
        "Kompanija A je kopirala izvorni kod softvera kompanije B bez dozvole i pustila ga u promet. "
        "Koji zakon reguliše zaštitu softvera u Srbiji, koja su prava oštećenog i pred kojim sudom se vodi postupak?"
    ),
    # 12. ZIO — prigovor izvršenika na rešenje o izvršenju
    (
        "ZIO_prigovor_rok",
        "Dužniku je dostavljeno rešenje o izvršenju na osnovu verodostojne isprave. "
        "Koji je rok za izjavljivanje prigovora, šta se prigovorom može osporiti i koji sud odlučuje?"
    ),
    # 13. Zakon o radu — diskriminacija pri zapošljavanju
    (
        "Zakon_o_radu_diskriminacija",
        "Poslodavac je odbio kandidata starosti 58 godina uz obrazloženje 'ne odgovara profilu'. "
        "Koji zakon reguliše diskriminaciju pri zapošljavanju, ko je teret dokazivanja i koji je rok za tužbu?"
    ),
    # 14. Upravni spor — rok za tužbu
    (
        "Upravni_spor_rok_tuzbe",
        "Ministarstvo je donelo konačno rešenje kojim je odbilo zahtev stranke. "
        "Koji je rok za podnošenje tužbe Upravnom sudu, šta se tužbom može tražiti i da li tužba odlaže izvršenje?"
    ),
    # 15. Zakon o zaštiti potrošača — povraćaj robe
    (
        "Potrosac_povracaj_digitalni_sadrzaj",
        "Potrošač je kupio digitalni sadržaj (e-knjiga) online. Želi da odustane od kupovine u roku od 14 dana. "
        "Da li ima pravo na povraćaj po Zakonu o zaštiti potrošača Srbije i postoje li izuzeci za digitalni sadržaj?"
    ),
]


def run_test():
    print("=" * 70)
    print("VINDEX AI — STRES TEST II (15 teških slučajeva)")
    print("=" * 70)
    print()

    rezultati = []

    for i, (naziv, pitanje) in enumerate(PITANJA, 1):
        print(f"\n[{i:02d}] {naziv}")
        print(f"     Pitanje: {pitanje[:90]}...")
        print("     Procesiranje", end="", flush=True)

        try:
            odg = ask_agent(pitanje)
            if odg.get("status") == "error":
                status = "GREŠKA"
                odgovor = odg.get("message", "?")
                pouzdanost = "N/A"
            else:
                data = odg.get("data", "")
                # Izvuci pouzdanost
                import re
                m = re.search(r"POUZDANOST:\s*(\d+%[^\n]*)", data)
                pouzdanost = m.group(1).strip() if m else "?"
                # Proveri da li je fallback
                if "45% — Odgovor iz opšteg znanja" in data:
                    status = "FALLBACK (45%)"
                elif "0% —" in data or "Nije pronađen u bazi" in data:
                    status = "NIJE PRONAĐEN"
                else:
                    status = "OK"
                # Izvuci pravni osnov
                m2 = re.search(r"PRAVNI OSNOV:\s*([^\n]+)", data)
                odgovor = m2.group(1).strip() if m2 else "?"
        except Exception as e:
            status = f"EXCEPTION: {e}"
            odgovor = ""
            pouzdanost = "N/A"

        print(f"\r     Status: {status}")
        print(f"     Pravni osnov: {odgovor[:80]}")
        print(f"     Pouzdanost: {pouzdanost[:60]}")

        rezultati.append((naziv, status, odgovor, pouzdanost))

    # Sumarni izveštaj
    print("\n" + "=" * 70)
    print("SUMARNI IZVEŠTAJ")
    print("=" * 70)
    ok = sum(1 for _, s, _, _ in rezultati if s == "OK")
    fallback = sum(1 for _, s, _, _ in rezultati if "FALLBACK" in s)
    nije = sum(1 for _, s, _, _ in rezultati if "NIJE" in s)
    greska = sum(1 for _, s, _, _ in rezultati if "GREŠK" in s or "EXCEPTION" in s)

    print(f"  OK (iz baze):   {ok}/15")
    print(f"  Fallback (45%): {fallback}/15")
    print(f"  Nije pronađen:  {nije}/15")
    print(f"  Greška:         {greska}/15")

    print("\nDETALJI PO PITANJU:")
    for naziv, status, osnov, pouzdanost in rezultati:
        ikona = "✓" if status == "OK" else "✗"
        print(f"  {ikona} [{naziv[:30]:<30}] {status:<20} | {pouzdanost[:40]}")

    return rezultati


if __name__ == "__main__":
    run_test()
