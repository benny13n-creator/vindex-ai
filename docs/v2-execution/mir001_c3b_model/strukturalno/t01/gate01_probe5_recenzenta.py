import sys
sys.path.insert(0, "C:/vindex-miroslav")
from shared import procesno_stanje as PS
P,U="p","u"
H="PRIVREDNI SUD U PRIMERGRADU\nBroj predmeta: P 9901/2026\n"
ZH=H+"ZAPISNIK SA ROCISTA\nRociste odrzano dana 15.07.2026. godine.\n"
Z=ZH+"Sud prihvata predlog za dopunu vestacenja.\n"
def d(o,t,**k): return {"id":"id-"+o,"predmet_id":P,"user_id":U,"oznaka":o,"tekst":t,**k}
def run(name,*docs,**kw):
    st=PS.utvrdi(list(docs),predmet_id=P,user_id=U,**kw)
    print("=== ",name)
    for x in st["dogadjaji"]:
        print(f"  {x['oznaka']} {x['akter']} {x['vrsta']} kand={x['kandidati']} vd={x['vrsta_dokumenta']['akter']}/{x['vrsta_dokumenta']['klasa']} dat={x['datum_dokumenta']} st={x.get('stanje')} kas={[(k['oznaka'],k['odnos']) for k in x['kasniji']]} rok={x.get('rok',{}).get('trajanje_dana')} upl={x.get('uplata')} | {x['izvod']!r}")
    print("  nep:", [n[:120] for n in st["nepoznato"]])
print("#### N1-N7 recheck")
run("N1a Tuziocu se nalaze", d("DOK-07", Z+"Tuziocu se nalaze da u roku od 8 dana uplati predujam od 60.000 dinara.\n"))
run("N1b Strankama se nalaze", d("DOK-07", Z+"Strankama se nalaze da u roku od 8 dana dostave pisane izjave.\n"))
run("N1c Nakon sto je tuzeni predlozio", d("DOK-07", Z+"Nakon sto je tuzeni predlozio dopunu vestacenja, sud prihvata predlog i odredjuje dopunu.\n"))
run("N1d kako tuzilac predlaze", d("DOK-07", Z+"Sud nalaze tuzenom da dostavi dnevnik, kako tuzilac predlaze, jer sud nalazi da je to potrebno.\n"))
run("N2 inicijal/din", d("DOK-07", ZH+"Sud nalaze vestaku M. Markovicu da u roku od 30 dana dostavi dopunu nalaza.\nSud nalaze tuziocu da uplati predujam od 60.000 din. u roku od 8 dana.\n"))
run("N3 ranije stavljen + odustanak", d("DOK-07", ZH+"Sud prihvata ranije stavljen predlog tuzenog za dopunu vestacenja.\n"), d("DOK-08", H+"PODNESAK TUZENOG\nTuzeni odustaje od predloga za dopunu vestacenja.\nDatum podneska: 05.09.2026.\n"))
run("N4 citat usred / sam red", d("DOK-08", H+"PODNESAK TUZENOG\nTuzeni se poziva na zapisnik: U Beogradu, dana 15.06.2026.\nTuzeni navodi da je postupio.\n"), d("DOK-09", H+"PODNESAK TUZENOG\nTuzeni se poziva na zapisnik sacinjen kako sledi:\nU Beogradu, dana 15.06.2026. godine\nTuzeni navodi da je postupio.\n"))
run("N5 dva naslova", d("DOK-09", H+"Zakljucak suda od 10.07.2026 - odgovor tuzenog\nPODNESAK TUZENOG\nSud nalaze tuzenom da plati.\n"))
print("#### NOVI")
run("A1 Stranke se upozoravaju", d("DOK-07", Z+"Stranke se upozoravaju da ce se u slucaju izostanka smatrati da je tuzba povucena.\n"))
run("A2 Tuzeni se obavezuje u PODNESKU (citat presude)", d("DOK-08", H+"PODNESAK TUZENOG\nTuzeni se obavezuje da tuziocu isplati 100.000 dinara, kako glasi presuda.\nDatum podneska: 05.09.2026.\n"))
run("A2b Tuzeni se obavezuje u ZAPISNIKU (izjava stranke)", d("DOK-07", Z+"Tuzeni se obavezuje da ce do sledeceg rocista dostaviti gradjevinski dnevnik.\n"))
run("A2c Tuzeni se protivi / se saglasava", d("DOK-07", Z+"Tuzeni se protivi predlogu i trazi da se predlog odbija.\nTuzilac se saglasava da se predlog prihvata.\n"))
run("A3 preneseni govor bez 'da'", d("DOK-07", Z+"Prema navodima tuzenog, sud je vec odbio predlog za dopunu vestacenja.\nPo predlogu tuzioca sud odbija predlog tuzenog za izvodjenje dokaza saslusanjem svedoka.\nPunomocnik tuzenog: sud je vec usvojio predlog.\n"))
run("A3b preneseni govor 'kao i da sud'", d("DOK-07", Z+"Punomocnik tuzioca je istakao da je dnevnik dostavljen, kao i da sud treba da odbije predlog.\n"))
run("A4 negacija sa 'se odbija'", d("DOK-07", Z+"Predlog tuzenog se ne odbija, vec se ostavlja za kasnije.\nNe odbija se predlog.\nPredlog se ne prihvata.\n"))
run("A5 CRLF datumi", d("DOK-07", Z.replace("\n","\r\n")), d("DOK-08", (H+"PODNESAK TUZENOG\nTuzeni odustaje od predloga za dopunu vestacenja.\nDatum podneska: 05.09.2026. godine.\n").replace("\n","\r\n")))
run("A6 datum labela/datum u dva reda; 'dana' bez zareza", d("DOK-08", H+"PODNESAK TUZENOG\nTuzeni odustaje od predloga za dopunu vestacenja.\nDatum podneska:\n05.09.2026.\n"), d("DOK-07", ZH.replace("Rociste odrzano dana 15.07.2026. godine.","Rociste odrzano dana 15.07.2026. godine, sa pocetkom u 10 casova.")+"Sud prihvata predlog za dopunu vestacenja.\n"))
run("A7 nominativ glas suda? 'Vestak se obavezuje' / 'Stranka koja ne uplati'", d("DOK-07", ZH+"Vestak se obavezuje da dopunu dostavi u roku od 30 dana.\nStranka koja ne uplati predujam snosi posledice.\n"))
run("A8 presuda izreka 'OBAVEZUJE SE tuzeni'", d("DOK-07", H+"PRESUDA\nOBAVEZUJE SE tuzeni da tuziocu isplati 3.150.000 dinara u roku od 15 dana.\nOdbija se zahtev tuzioca za kamatu.\n"))
run("A9 'se odbija' u podnesku koji opisuje", d("DOK-08", H+"PODNESAK TUZIOCA\nTuzilac predlaze da se odbija predlog tuzenog.\n"))
run("A10 rasprava 'tuzeni predlaze da sud' sa tackom-zarezom", d("DOK-07", Z+"Tuzeni navodi; sud odbija predlog tuzioca za vestacenje.\n"))
