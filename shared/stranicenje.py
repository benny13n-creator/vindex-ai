# -*- coding: utf-8 -*-
"""Straničenje preko PostgREST-a — jedan vlasnik pravila.

PROBLEM KOJI OVO REŠAVA

PostgREST na `.range(offset, kraj)` gde je `offset` IZA poslednjeg reda ne
vraća praznu listu nego grešku::

    PGRST103  Requested range not satisfiable
              "An offset of 500 was requested, but there are only 20 rows."

supabase-py je diže kao `APIError`, pa ruta koja to ne uhvati pada u HTTP 500.
Mereno uživo na registru predmeta sa 20 redova::

    offset=0      -> 200, 20 redova
    offset=20     -> 200, 0 redova      (tačno granicu PostgREST podnosi)
    offset=500    -> 500 Interna greška
    offset=100000 -> 500 Interna greška

To nije teorijski slučaj. Dovoljno je da korisnik obeleži vezu na stranu 3 pa
obriše zapise, ili da nastavi straničenje posle promene filtera — sledeći put
ne dobije „nema više redova" nego srušen ekran.

ZAŠTO OVDE, A NE U SVAKOJ RUTI

Isti obrazac postoji na svakom mestu koje stranicira. Kada pravilo živi u
svakoj ruti posebno, dovoljno je da ga jedna zaboravi — a zaboravljena je
tiho, jer greška se vidi tek na offsetu koji niko ne kuca u razvoju.

ŠTA SE NAMERNO **NE** RADI

Guta se TAČNO `PGRST103`. Svaka druga greška se propagira dalje: pokvaren
upit ili istekao token koji bi se prikazao kao „nema rezultata" je tiha laž,
a tiha laž o podacima je gora od glasnog 500.
"""
from types import SimpleNamespace

#: PostgREST kod za „traženi opseg nije zadovoljiv".
KOD_VAN_OPSEGA = "PGRST103"


def strana_ili_prazna(dohvati_opseg, prebroj):
    """Vraća stranu, ili praznu stranu SA TAČNIM `count` kad je offset iza kraja.

    :param dohvati_opseg: callable koji izvršava upit sa `.range(...)`
    :param prebroj: callable koji izvršava ISTI upit (isti filteri!) samo radi
        broja redova; poziva se isključivo kada opseg padne. Filteri moraju biti
        identični — inače bi prazna strana prijavila ukupan broj svih redova
        umesto broja onih koji odgovaraju pretrazi.
    :returns: objekat sa `.data` i `.count`
    """
    try:
        return dohvati_opseg()
    except Exception as ex:
        if getattr(ex, "code", None) != KOD_VAN_OPSEGA:
            raise
        return SimpleNamespace(data=[], count=prebroj().count)
