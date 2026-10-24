import sys
sys.path.insert(0, "C:/vindex-miroslav")
from shared import procesno_stanje as PS
H="PRIVREDNI SUD\n"
P=H+"PODNESAK TUZENOG\nTuzeni navodi da je na rocistu odrzanom 15.07.2026. godine raspravljano o predlogu za dopunu vestacenja.\nDatum podneska: 20.07.2026.\n"
def run(n,*t):
    ds=[dict(id=o,predmet_id='p',user_id='u',oznaka=o,tekst=x) for o,x in t]
    st=PS.utvrdi(ds,predmet_id='p',user_id='u'); print("==",n); print("  ",[x[:110] for x in st['nepoznato']])
    print("   dat:",[(x['oznaka'],x['vrsta'],x['datum_dokumenta']) for x in st['dogadjaji'] if x['akter']=='SUD'])
run("R1 zapisnik sa tekstom posle datuma",("DOK-07",H+"ZAPISNIK SA ROCISTA\nRociste odrzano dana 15.07.2026. godine, sa pocetkom u 10 casova.\nSud prihvata predlog za dopunu vestacenja.\n"),("DOK-08",P))
run("R1b 'na rocistu odrzanom dana'",("DOK-07",H+"ZAPISNIK SA ROCISTA\nNa rocistu odrzanom dana 15.07.2026. prisutni su punomocnici.\nSud prihvata predlog za dopunu vestacenja.\n"),("DOK-08",P))
run("R1c RESENJE pominje rociste (nije zapisnik)",("DOK-09",H+"RESENJE\nNa rocistu odrzanom 15.07.2026. godine tuzeni je predlozio dopunu.\nSud odbija predlog tuzenog.\nDoneto dana 01.08.2026.\n"),("DOK-08",P))
run("R1d bez sudskog dok",("DOK-08",P))
run("R1e zapisnik drugog datuma koji pominje raniji",("DOK-10",H+"ZAPISNIK SA ROCISTA\nRociste odrzano dana 10.09.2026.\nKonstatuje se da je na rocistu od 15.07.2026. izveden dokaz.\nSud prihvata predlog.\n"),("DOK-08",P))
