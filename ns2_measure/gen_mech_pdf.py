# NS2b mechanism: wrap matrix JPEGs (unchanged bytes) into one-page A4 PDFs. Usage: gen_mech_pdf.py <fxm dir>
import os, sys, zlib
import fitz

D = sys.argv[1]
NAMES = ["m_prog_444_40", "m_prog_420_40", "m_prog_422_40", "m_prog_gray_40", "m_prog_cmyk_40", "m_prog_444_20",
         "m_base_444_40", "m_base_cmyk_40", "t_seqms_444_40", "t_arith_prog_444_40", "t_arith_seq_444_40"]
for n in NAMES:
    src = os.path.join(D, n + ".jpg")
    if not os.path.exists(src):
        continue
    j = open(src, "rb").read()
    for flate in ((False, True) if n == "m_prog_444_40" else (False,)):
        d = fitz.open(); p = d.new_page(width=595, height=842); p.insert_image(p.rect, stream=j)
        if flate:
            x = p.get_images(full=True)[0][0]
            d.update_stream(x, zlib.compress(j), compress=False)
            d.xref_set_key(x, "Filter", "[/FlateDecode /DCTDecode]")
        out = os.path.join(D, ("pdfz_" if flate else "pdf_") + n + ".pdf")
        d.save(out); d.close()
        print(out, os.path.getsize(out) // 1024, "KiB")
