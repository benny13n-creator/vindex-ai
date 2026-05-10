"""Generate sample_ugovor.docx from sample_ugovor_o_radu.txt via python-docx."""

from pathlib import Path
import docx


def main() -> None:
    fixture_dir = Path(__file__).parent
    txt_path = fixture_dir / "sample_ugovor_o_radu.txt"
    docx_path = fixture_dir / "sample_ugovor.docx"

    text = txt_path.read_text(encoding="utf-8")
    doc = docx.Document()

    for line in text.splitlines():
        doc.add_paragraph(line)

    doc.save(str(docx_path))
    print(f"Written: {docx_path}")


if __name__ == "__main__":
    main()
