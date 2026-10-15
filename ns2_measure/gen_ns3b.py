# NS3-A confirmation fixtures: transparency groups (nested forms, page group, soft mask) and an exponential
# non-stream object graph (annotation /AP/N). SYNTHETIC only. Usage: gen_ns3b.py <dir> (after gen.py: uses its scan)
import io, os, sys

import fitz
from PIL import Image

OUT = sys.argv[1]
A4 = fitz.Rect(0, 0, 595, 842)


def sacuvaj(d, ime):
    d.save(os.path.join(OUT, ime), garbage=0); d.close()
    print(ime, os.path.getsize(os.path.join(OUT, ime)) // 1024, "KiB", flush=True)


def forma(d, sadrzaj: bytes, resursi: str = "<<>>", grupa=True) -> int:
    x = d.get_new_xref()
    g = "/Group<</S/Transparency/I true/K true>>" if grupa else ""
    d.update_object(x, f"<</Type/XObject/Subtype/Form/BBox[0 0 595 842]{g}/Resources{resursi}>>")
    d.update_stream(x, sadrzaj)
    return x


def postavi(d, pg, sadrzaj: bytes, resursi: str):
    d.xref_set_key(pg.xref, "Resources", resursi)
    c = d.get_new_xref(); d.update_object(c, "<<>>"); d.update_stream(c, sadrzaj)
    d.xref_set_key(pg.xref, "Contents", f"{c} 0 R")


# N ugnežđenih transparentnih grupa preko cele strane (pregled N1)
for n in (1, 2, 4, 8):
    d = fitz.open(); pg = d.new_page(width=595, height=842)
    x = forma(d, b"0.5 g 0 0 595 842 re f")
    for _ in range(n - 1):
        x = forma(d, b"0.9 g 0 0 10 10 re f /G Do", f"<</XObject<</G {x} 0 R>>>>")
    postavi(d, pg, b"/G Do", f"<</XObject<</G {x} 0 R>>>>")
    sacuvaj(d, f"ns3_grupe_{n}.pdf")
# meka maska (ExtGState /SMask luminosity) preko cele strane
d = fitz.open(); pg = d.new_page(width=595, height=842)
m = forma(d, b"0.7 g 0 0 595 842 re f", grupa=True)
postavi(d, pg, b"/S0 gs 0 g 0 0 595 842 re f", f"<</ExtGState<</S0<</SMask<</S/Luminosity/G {m} 0 R>>>>>>>>")
sacuvaj(d, "ns3_smask_gs.pdf")
# obični dokumenti sa providnošću: sken 300 dpi u grupi strane (Word/LibreOffice izvoz), digitalna strana sa
# providnim logom (grupa preko malog dela) i anotacijom
src = fitz.open(os.path.join(OUT, "scan_cyr_1p.pdf"))
d = fitz.open(); d.insert_pdf(src); pg = d[0]
d.xref_set_key(pg.xref, "Group", "<</S/Transparency/CS/DeviceRGB/I true>>")
sacuvaj(d, "ns3_sken_grupa_strane.pdf")
d = fitz.open(); pg = d.new_page(width=595, height=842)
for i in range(30):
    pg.insert_text((50, 60 + i * 19), f"{i + 1}. Digitalni podnesak sa providnim logotipom u zaglavlju.", fontsize=11)
logo = io.BytesIO(); Image.new("RGBA", (400, 200), (200, 30, 30, 120)).save(logo, "PNG")
pg.insert_image(fitz.Rect(400, 20, 560, 100), stream=logo.getvalue())
pg.add_highlight_annot(fitz.Rect(50, 50, 300, 65))
d.xref_set_key(pg.xref, "Group", "<</S/Transparency/CS/DeviceRGB/I true>>")
sacuvaj(d, "ns3_digital_logo_grupa.pdf")
# eksponencijalan graf rečnika kroz /AP/N (pregled N2)
for n in (16, 22):
    d = fitz.open(); pg = d.new_page(width=595, height=842)
    prethodni = d.get_new_xref(); d.update_object(prethodni, "<</x 1>>")
    for _ in range(n):
        x = d.get_new_xref(); d.update_object(x, f"<</a {prethodni} 0 R /b {prethodni} 0 R>>"); prethodni = x
    a = pg.add_rect_annot(fitz.Rect(10, 10, 50, 50))
    d.xref_set_key(a.xref, "AP", f"<</N {prethodni} 0 R>>")
    sacuvaj(d, f"ns3_dag_{n}.pdf")
