import sys
sys.path.insert(0, ".")
from shared import nacrt_za_sud as NZ, procesno_stanje as PS
from tests.test_mir001_c3b_procesno_stanje_ugovor import BEZ_ZAPISNIKA, DOK06, ODUSTANAK, PREDUJAM, ZAPISNIK, _d
st = lambda *d: PS.utvrdi(list(d), predmet_id="pred-1", user_id="user-A")
A = st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK))
C1 = st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", ODUSTANAK))
C2 = st(_d("DOK-06", DOK06), _d("DOK-07", BEZ_ZAPISNIKA))
H2 = st(_d("DOK-07", PREDUJAM))
B = st(_d("DOK-06", DOK06))
print({x["id"]: x["vrsta"] + ":" + x["oznaka"] for x in A["dogadjaji"]})
print({x["id"]: x["vrsta"] + ":" + x["oznaka"] for x in C1["dogadjaji"]})
print({x["id"]: x["vrsta"] + ":" + x["oznaka"] for x in H2["dogadjaji"]})
P = [
 # pronouns / no subject words
 ("A", A, "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]]. Isti je dostavljen."),
 ("A", A, "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]]. Tuženi je to uradio."),
 ("A", A, "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]]. To je urađeno."),
 ("A", A, "Sud je prihvatio dopunu [[PS-04]]. Ista je izvršena."),
 ("A", A, "Sud je prihvatio dopunu [[PS-04]]. Ona više nema svrhu."),
 ("A", A, "Sud je prihvatio dopunu [[PS-04]]. Međutim, ta radnja je sada suvišna."),
 ("A", A, "Sud je prihvatio dopunu [[PS-04]]. Veštak je to već obavio."),
 ("A", A, "Sud je prihvatio dopunu [[PS-04]]. Takva radnja nema smisla."),
 ("A", A, "Sud je prihvatio dopunu [[PS-04]]. Veštak je završio posao."),
 ("H2", H2, "Sud je naložio uplatu [[PS-02]]. Tužilac je to učinio."),
 ("H2", H2, "Sud je naložio uplatu [[PS-02]]. Novac je prenet na račun suda."),
 ("H2", H2, "Sud je naložio uplatu [[PS-02]]. Iznos od 60.000 dinara je prenet."),
 ("H2", H2, "Sud je naložio uplatu [[PS-02]]. Tužilac je obavezu namirio."),
 ("H2", H2, "Novac za veštaka je obezbeđen."),
 ("H2", H2, "Tužilac je snosio troškove veštaka."),
 # split
 ("A", A, "Dopuna veštačenja je predmet ovog podneska. Ona nije potrebna."),
 ("A", A, "Tuženi je imao 15 dana. Ništa nije dostavio."),
 ("A", A, "Tuženi je imao 15 dana. Tih 15 dana je prošlo."),
 ("A", A, "Tuženi nije postupio."),
 ("A", A, "Tuženi je ostao pasivan."),
 # synonyms of subject
 ("A", A, "Tuženi je predao dnevnik radova."),
 ("A", A, "Knjiga gradilišta je predata sudu."),
 ("A", A, "Dodatni nalaz nije neophodan."),
 ("A", A, "Dodatni nalaz veštaka je bespotreban."),
 ("A", A, "Dodatna ekspertiza ne bi ništa promenila."),
 ("A", A, "Dopunsko veštačenje je nepotrebno."),
 ("A", A, "Dopunsko veštačenje ne treba sprovoditi."),
 ("A", A, "Novo veštačenje ne treba sprovoditi."),
 ("A", A, "Dnevnik radova je predat."),
 ("C2", C2, "Dopunsko veštačenje treba odbiti."),
 ("C2", C2, "Zahtev tuženog za novo veštačenje treba odbiti."),
 # stav with acknowledgement but asserting state
 ("A", A, "Iako je sud [[PS-04]], dopuna je već izvršena, smatra tužilac."),
 ("A", A, "Iako je sud [[PS-04]], tužilac smatra da je dopuna već sprovedena."),
 ("A", A, "Iako je sud [[PS-05]], tužilac ističe da je tuženi dnevnik već dostavio."),
 ("H2", H2, "Iako je sud [[PS-02]], tužilac smatra da je predujam uplaćen."),
 ("A", A, "Iako je sud [[PS-04]], tužilac smatra da je ta odluka prestala da važi."),
 ("C1", C1, "Iako je sud [[PS-04]], tužilac smatra da je odustankom tuženog [[PS-09]] odluka bez dejstva."),
 ("C1", C1, "Iako je sud [[PS-04]], tužilac smatra da se dopuna neće sprovesti jer je tuženi odustao [[PS-09]]."),
 ("A", A, "Iako je sud [[PS-05]], tužilac ističe da je rok istekao."),
 # fake paraphrase subset
 ("A", A, "Sud je prihvatio predlog (DOK-07)."),
 ("A", A, "Sud je prihvatio predlog tužioca (DOK-07)."),
 ("A", A, "Sud je prihvatio predlog za dopunu veštačenja tužioca (DOK-07)."),
 ("A", A, "Sud je [[PS-04]] prihvatio predlog tužioca."),
 ("A", A, "Sud je prihvatio [[PS-04]] i tužbeni zahtev."),
 ("A", A, "Sud je naložio tuženom da dostavi dnevnik (DOK-07), a tuženi je to i uradio."),
 ("A", A, "Sud je naložio tuženom da dostavi dnevnik (DOK-07), što je tuženi i uradio."),
 ("A", A, "Sud je zakazao ročište za 18.11.2026. (DOK-07) radi zaključenja rasprave."),
 ("A", A, "Sud je zakazao ročište za 18.11.2026. godine radi izvođenja dopune (DOK-07)."),
 ("A", A, "Sud je odredio da je nalaz veštaka nepotpun (DOK-07)."),
 ("A", A, "Prema zapisniku (DOK-07), sud prihvata predlog i odbija primedbe tužioca."),
 ("C1", C1, "Tuženi je [[PS-09]]; dopuna je time otpala."),
 ("C1", C1, "Tuženi je [[PS-09]]. Samim tim, dopuni nema mesta."),
 ("C1", C1, "Tuženi je [[PS-09]]. Samim tim, dopuna se ukida."),
 ("C1", C1, "Tuženi je [[PS-09]]. Samim tim, veštak neće raditi dopunu."),
 # legit (should KEEP)
 ("A", A, "Iako je sud prihvatio dopunu (DOK-07), tužilac smatra da nije potrebna jer je nalaz potpun."),
 ("A", A, "Iako je sud [[PS-04]], tužilac predlaže da sud tu odluku preispita, jer je nalaz potpun i jasan."),
 ("C1", C1, "Tuženi je podneskom [[PS-09]] naveo da odustaje od predloga za dopunu veštačenja."),
 ("A", A, "Tužilac smatra da je nalaz veštaka potpun i jasan."),
 ("A", A, "Nalaz veštaka je jasan, potpun i u skladu sa pravilima struke."),
 ("A", A, "Tuženi u izjašnjenju (DOK-06) tvrdi da veštak nije izvršio uvid u građevinski dnevnik."),
 ("A", A, "Prema čl. 154 ZOO, ko drugome prouzrokuje štetu dužan je da je naknadi."),
 ("A", A, "Tužilac je precizirao tužbeni zahtev na iznos od 3.150.000 dinara (DOK-07)."),
 ("A", A, "Tužilac ostaje pri tužbenom zahtevu u celosti."),
 ("A", A, "Hidroizolacija je izvedena suprotno projektu, što je uzrok prokišnjavanja."),
 ("A", A, "Tužilac predlaže da sud, imajući u vidu odluku [[PS-04]], preispita potrebu za dopunom."),
 ("A", A, "Tužilac se ne protivi dopuni veštačenja."),
 ("A", A, "Tužilac predlaže da sud obaveže tuženog da naknadi troškove postupka."),
 ("A", A, "Tužilac moli sud da veštaku [[PS-04]] odredi primeren rok."),
 ("A", A, "Građevinski dnevnik je ključan dokaz o redosledu radova."),
 ("A", A, "Tužilac smatra da građevinski dnevnik nije od značaja za ocenu uzroka štete."),
 ("H2", H2, "Tužilac moli sud da mu produži rok za uplatu predujma [[PS-02]]."),
 ("C2", C2, "Ukoliko sud na ročištu 15.07.2026. nije odlučio o predlogu, tužilac se protivi dopuni veštačenja."),
 ("C2", C2, "Tuženi u podnesku (DOK-07) navodi da je na ročištu raspravljano o dopuni."),
 ("B", B, "Tužilac se protivi predlogu tuženog za dopunu veštačenja, jer je nalaz potpun."),
 ("B", B, "Tužilac smatra da dopuna veštačenja nije potrebna, jer je nalaz potpun."),
]
for g, s, t in P:
    k = NZ.zastiti(t, s)
    print(("OMIT" if k["izostavljeno"] else "KEEP"), f"[{g}]", repr(t), "|", [i["razlog"][:50] for i in k["izostavljeno"]])
