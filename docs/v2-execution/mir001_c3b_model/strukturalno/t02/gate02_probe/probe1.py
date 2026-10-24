import sys
sys.path.insert(0, ".")
from shared import nacrt_za_sud as NZ, procesno_stanje as PS
from tests.test_mir001_c3b_procesno_stanje_ugovor import BEZ_ZAPISNIKA, DOK06, ODUSTANAK, PREDUJAM, ZAPISNIK, _d

P, U = "pred-1", "user-A"
st = lambda *d: PS.utvrdi(list(d), predmet_id=P, user_id=U)
A = st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK))
C1 = st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", ODUSTANAK))
C2 = st(_d("DOK-06", DOK06), _d("DOK-07", BEZ_ZAPISNIKA))
H2 = st(_d("DOK-07", PREDUJAM))
B = st(_d("DOK-06", DOK06))
def ids(s):
    return {x["vrsta"] + ":" + x["oznaka"]: x["id"] for x in s["dogadjaji"]}
if "--ids" in sys.argv:
    for n, s in [("A", A), ("C1", C1), ("C2", C2), ("H2", H2)]:
        print(n, ids(s))
    sys.exit()
iA = ids(A); iC1 = ids(C1); iH2 = ids(H2)
PRI = iA.get("SUD_PRIHVATA:DOK-07")
ODU = next((v for k, v in iC1.items() if k.endswith("DOK-08")), None)
TUZ06 = next((v for k, v in iA.items() if k.endswith("DOK-06")), None)
H2N = next((v for k, v in iH2.items() if "NALAZE" in k), None)
probes = [
 # bypass attempts (should be omitted)
 ("A", A, "Dopuna veštačenja je izlišna."),
 ("A", A, "Dopuna veštačenja ne doprinosi razjašnjenju stvari."),
 ("A", A, "Dopuna veštačenja bi samo odugovlačila postupak."),
 ("A", A, "Nalaz veštaka je potpun i jasan, pa za dopunom nema mesta."),
 ("A", A, "Nalaz je potpun. Dopuna, stoga, nije potrebna."),
 ("A", A, "Dopuna veštačenja nije\npotrebna."),
 ("A", A, "- dopuna veštačenja: nepotrebna"),
 ("A", A, "**Dopuna veštačenja nije potrebna**"),
 ("A", A, "Dopuna veštačenja nije potrebna; nalaz je potpun"),
 ("A", A, "Dopuna veštačenja NIJE POTREBNA."),
 ("A", A, "Dopuna vestacenja nije potrebna."),
 ("A", A, "Dopuna veštačenja nije potrеbna."),  # cyrillic e
 ("A", A, "Допуна вештачења није потребна."),
 ("A", A, f"Kako je sud [[{PRI}]], dopuna veštačenja nije potrebna."),
 ("A", A, f"Tuženi [[{TUZ06}]], ali dopuna veštačenja nije potrebna."),
 ("A", A, "Prema odluci (DOK-07) dopuna veštačenja nije potrebna, smatra tužilac."),
 ("A", A, "Tužilac ističe da je odluka (DOK-07) bez osnova i da dopuna nije potrebna."),
 ("A", A, f"Sud je [[{PRI}]], te je tim pitanje dopune zatvoreno i dopuna se neće sprovoditi."),
 ("A", A, "Dopuna veštačenja se neće sprovoditi."),
 ("A", A, "Sud je odustao od dopune veštačenja."),
 ("A", A, "Sud je naknadno opozvao odluku o dopuni veštačenja."),
 ("A", A, "Odluka o dopuni veštačenja je stavljena van snage."),
 ("A", A, "Tuženi je dostavio građevinski dnevnik."),
 ("A", A, "Tuženi je podneo građevinski dnevnik sudu."),
 ("A", A, "Građevinski dnevnik je priložen u spis."),
 ("A", A, "Tuženi nije dostavio dnevnik."),
 ("A", A, "Tuženi do danas nije priložio građevinski dnevnik."),
 ("A", A, "Rok od 15 dana za dnevnik je prošao."),
 ("A", A, "Petnaest dana je prošlo, a dnevnik nije dostavljen."),
 ("A", A, "Tuženi je zakasnio sa dnevnikom."),
 ("A", A, "Ostavljeni rok je protekao bezuspešno."),
 ("A", A, "Rok je istekao 30.07.2026."),
 ("H2", H2, "Tužilac je predujam položio na račun suda."),
 ("H2", H2, "Predujam je uredno deponovan."),
 ("H2", H2, "Tužilac je izmirio predujam."),
 ("H2", H2, "Tužilac je ispunio obavezu iz zapisnika (DOK-07)."),
 ("H2", H2, f"Tužilac je postupio po [[{H2N}]]."),
 ("H2", H2, "Troškovi veštačenja su obezbeđeni."),
 ("H2", H2, f"Tužilac je, kako je sud [[{H2N}]], uplatio predujam."),
 ("C1", C1, "Povlačenjem predloga od strane tuženog, dopuna je postala bespotrebna."),
 ("C1", C1, f"Tuženi je [[{ODU}]], pa se dopuna neće održati."),
 ("C1", C1, "Tuženi više ne traži dopunu veštačenja, te je ista izgubila svrhu."),
 ("C1", C1, f"Tuženi je odustao od predloga [[{ODU}]], čime je odluka suda prestala da važi."),
 ("C1", C1, "Kako tuženi odustaje od predloga (DOK-08), dopuna otpada."),
 ("C2", C2, "Tužilac traži da se predlog tuženog za dopunu veštačenja odbije."),
 ("C2", C2, "Predlog tuženog za dopunu veštačenja treba odbiti."),
 ("C2", C2, "Ne postoje razlozi za dopunu veštačenja."),
 ("A", A, "Sud je utvrdio da je hidroizolacija neispravna (DOK-07)."),
 ("A", A, f"Sud je [[{PRI}]] i time potvrdio da je nalaz veštaka nepotpun."),
 ("A", A, "Veštak je nesporno dokazao da je uzrok hidroizolacija."),
 ("A", A, "Na ročištu je sud potvrdio da je tužbeni zahtev osnovan (DOK-07)."),
 ("A", A, "Sud je prihvatio tužbeni zahtev (DOK-07)."),
 ("A", A, "Sud je prihvatio predlog za dopunu veštačenja i tužbeni zahtev (DOK-07)."),
 # legit attributed (should stay)
 ("A", A, f"Iako je sud [[{PRI}]], tužilac smatra da dopuna nije potrebna jer je nalaz potpun."),
 ("A", A, "Tužilac predlaže da sud, imajući u vidu odluku (DOK-07), preispita potrebu za dopunom."),
 ("C1", C1, f"Tuženi je podneskom [[{ODU}]] naveo da odustaje od predloga za dopunu veštačenja."),
 ("A", A, "Tužilac smatra da je nalaz veštaka potpun i jasan."),
 ("A", A, "Tužilac ostaje pri tužbenom zahtevu."),
 ("A", A, "Tužilac je precizirao tužbeni zahtev na iznos od 3.150.000 dinara (DOK-07)."),
 ("H2", H2, "Tužilac moli sud da mu produži rok za uplatu predujma (DOK-07)."),
]
for g, s, t in probes:
    k = NZ.zastiti(t, s)
    stat = "OMIT" if k["izostavljeno"] else "KEEP"
    print(f"{stat} [{g}] {t!r}\n     -> {k['tekst'][:160]!r} {[i['razlog'] for i in k['izostavljeno']]}")
