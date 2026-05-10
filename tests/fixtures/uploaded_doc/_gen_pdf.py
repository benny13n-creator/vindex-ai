"""Generate sample_ugovor.pdf from sample_ugovor_o_radu.txt via reportlab."""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def main() -> None:
    fixture_dir = Path(__file__).parent
    txt_path = fixture_dir / "sample_ugovor_o_radu.txt"
    pdf_path = fixture_dir / "sample_ugovor.pdf"

    text = txt_path.read_text(encoding="utf-8")
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontName = "Helvetica"
    normal.fontSize = 10
    normal.leading = 14

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    story = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            # Escape XML-special chars for Paragraph
            safe = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe, normal))
        else:
            story.append(Spacer(1, 6))

    doc.build(story)
    print(f"Written: {pdf_path}")


if __name__ == "__main__":
    main()
