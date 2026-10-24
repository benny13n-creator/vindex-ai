import sys
sys.path.insert(0, ".")
from shared import nacrt_za_sud as NZ, procesno_stanje as PS
from tests.test_mir001_c3b_procesno_stanje_ugovor import DOK06, ODUSTANAK, PREDUJAM, ZAPISNIK, _d, _ZAGLAVLJE
st = lambda *d: PS.utvrdi(list(d), predmet_id="pred-1", user_id="user-A")
def pod(naslov, *redovi):
    return _ZAGLAVLJE + naslov + " (SINTETICKI PREDMET)\n" + "\n".join(redovi) + "\nDatum podneska: 20.08.2026. godine."
NEG = pod("PODNESAK TUZIOCA", "Tuzilac navodi da nije uplatio predujam za dopunu vestacenja.")
NAM = pod("PODNESAK TUZIOCA", "Tuzilac navodi da ce uplatiti predujam za dopunu vestacenja.")
MOLBA = pod("PODNESAK TUZIOCA", "Tuzilac navodi da predujam za dopunu vestacenja nije u mogucnosti da uplati u roku.")
UPL = pod("PODNESAK TUZIOCA", "Tuzilac navodi da je uplatio predujam za dopunu vestacenja.")
DNEV = pod("PODNESAK TUZENOG", "Tuzeni navodi da gradjevinski dnevnik nije sacuvan.")
DNEV_NEG = pod("PODNESAK TUZENOG", "Tuzeni navodi da gradjevinski dnevnik nije dostavio jer nije sacuvan.")
DNEV_UPIT = pod("PODNESAK TUZENOG", "Tuzeni navodi da ce gradjevinski dnevnik dostaviti naknadno.")
S = {
 "H2+NEG": st(_d("DOK-07", PREDUJAM), _d("DOK-08", NEG)),
 "H2+NAM": st(_d("DOK-07", PREDUJAM), _d("DOK-08", NAM)),
 "H2+MOLBA": st(_d("DOK-07", PREDUJAM), _d("DOK-08", MOLBA)),
 "H2+UPL": st(_d("DOK-07", PREDUJAM), _d("DOK-08", UPL)),
 "A+DNEV": st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", DNEV)),
 "A+DNEVNEG": st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", DNEV_NEG)),
 "A+DNEVUPIT": st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", DNEV_UPIT)),
 "A": st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK)),
 "C1": st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", ODUSTANAK)),
}
for k, s in S.items():
    if k in ("A", "C1"): continue
    print(k, {x["id"]: (x["vrsta"], x["oznaka"], x["izvod"][:60]) for x in s["dogadjaji"] if x["oznaka"] == "DOK-08"})
def pid(k, oz="DOK-08"):
    return next((x["id"] for x in S[k]["dogadjaji"] if x["oznaka"] == oz), "PS-99")
P = [
 # source exists, shares subject, but does NOT contain claim
 ("A+DNEV", "Tuženi u podnesku (DOK-08) navodi da je građevinski dnevnik dostavio sudu."),
 ("A+DNEV", f"Tuženi u podnesku [[{pid('A+DNEV')}]] navodi da je građevinski dnevnik dostavljen."),
 ("A+DNEV", "Tuženi u podnesku (DOK-08) navodi da je rok za dnevnik istekao."),
 # source has negation
 ("H2+NEG", "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja."),
 ("H2+NEG", f"Tužilac u podnesku [[{pid('H2+NEG')}]] navodi da je predujam uplatio."),
 ("A+DNEVNEG", "Tuženi u podnesku (DOK-08) navodi da je građevinski dnevnik dostavio."),
 # source has intention
 ("H2+NAM", "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja."),
 ("A+DNEVUPIT", "Tuženi u podnesku (DOK-08) navodi da je građevinski dnevnik dostavio."),
 ("H2+MOLBA", "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam u roku."),
 # legit: source actually says it
 ("H2+UPL", "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja."),
 ("A+DNEV", "Tuženi u podnesku (DOK-08) navodi da građevinski dnevnik nije sačuvan."),
 # two claims, source confirms one
 ("H2+UPL", "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam, te je nalog suda time ispunjen."),
 ("H2+UPL", "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam i da je rok za uplatu istekao."),
 ("H2+UPL", "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam, pa dopuna veštačenja može da počne."),
 ("H2+UPL", "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam, a veštak je dopunu već sproveo."),
 ("A+DNEV", "Tuženi u podnesku (DOK-08) navodi da građevinski dnevnik nije sačuvan, pa je nalog suda bespredmetan."),
 ("A+DNEV", "Tuženi u podnesku (DOK-08) navodi da građevinski dnevnik nije sačuvan, čime je obaveza dostave otpala."),
 ("A+DNEV", "Tuženi u podnesku (DOK-08) navodi da građevinski dnevnik nije sačuvan, pa tuženi nije ni mogao da postupi po nalogu."),
 # subject carry over 2 sentences / paragraph
 ("A", "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]]. Tuženi je imao petnaest dana. Isti je dostavljen."),
 ("A", "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]]. Tužilac to ne osporava. Isti je dostavljen."),
 ("A", "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]].\n\nTo je u međuvremenu i učinjeno."),
 ("A", "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]]. Hidroizolacija je izvedena suprotno projektu. Isti je dostavljen."),
 ("A", "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]]. Hidroizolacija je izvedena suprotno projektu. Taj dokument je dostavljen."),
 ("A", "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]]. Tužilac je takođe priložio fotografije. Tuženi je dokument predao."),
 ("A", "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]]. Tuženi je dokument predao."),
 ("A", "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]]. Tražena isprava je stigla u sud."),
 ("A", "Sud je naložio tuženom da dostavi građevinski dnevnik [[PS-05]]. Sud je dokument primio."),
 ("A", "Sud je prihvatio dopunu [[PS-04]]. Veštak je dostavio dopunski nalaz."),
 ("A", "Sud je prihvatio dopunu [[PS-04]]. Veštak je izradio dopunski nalaz."),
 ("A", "Sud je prihvatio dopunu [[PS-04]]. Dopunski nalaz je u spisu."),
 # false omission: pronoun after sentence without order
 ("A", "Hidroizolacija je izvedena suprotno projektu. To je uzrok prokišnjavanja."),
 ("A", "Tužilac je pretrpeo štetu od 3.150.000 dinara. Ista je nastala zbog prokišnjavanja."),
 ("A", "Tuženi je izvođač radova. On je radove završio u martu 2024. godine."),
 ("A", "Tužilac je investitor. On je uredno platio cenu radova."),
 ("A", "Ugovor je zaključen 10.01.2023. Isti je izvršen u celosti od strane tužioca."),
 ("A", "Šteta je utvrđena fotografijama. To je dokazano i nalazom veštaka (DOK-05)."),
 ("A", "Tužilac je obavestio tuženog o nedostacima. Tuženi nije postupio po reklamaciji."),
 ("H2", "Tužilac je investitor. On je uredno platio cenu radova."),
]
S["H2"] = st(_d("DOK-07", PREDUJAM))
for k, t in P:
    r = NZ.zastiti(t, S[k])
    print(("OMIT" if r["izostavljeno"] else "KEEP"), f"[{k}]", repr(t), "|", [(i["id"], i["razlog"][:45]) for i in r["izostavljeno"]])
