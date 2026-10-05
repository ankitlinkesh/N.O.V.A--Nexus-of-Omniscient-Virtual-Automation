"""Phase 132: NOVA reads real PDF and Word files.

The extractors existed since Phase 128 but their libraries were never installed, so
every PDF/DOCX was refused. These tests build REAL documents (no mocked extractor):
- a PDF with a text layer is read;
- a scanned PDF (no text layer) is refused with that reason, not read as "empty";
- a password-protected PDF is refused with that reason;
- a .docx's tables are read, in order with its paragraphs (they were skipped);
- the result is still untrusted content.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
docx = pytest.importorskip("docx")

from backend.eva.tools import safe_file_tools as sft  # noqa: E402
from backend.eva.tools.registry import ToolRegistry  # noqa: E402


def _text_pdf(text: str) -> bytes:
    """A minimal one-page PDF with a real text layer (hand-built: pypdf can't draw text)."""
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


@pytest.fixture
def home(tmp_path, monkeypatch):
    (tmp_path / "Downloads").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _read(name: str) -> dict:
    return ToolRegistry().run("file.read_text", path=f"Downloads/{name}")


def test_a_pdf_with_a_text_layer_is_read(home):
    (home / "Downloads" / "invoice.pdf").write_bytes(_text_pdf("Invoice total 4200 rupees"))
    result = _read("invoice.pdf")
    assert result["ok"] is True and result["format"] == "pdf", result
    assert "Invoice total 4200 rupees" in result["text"]
    assert result["untrusted"] is True


def test_a_scanned_pdf_is_refused_with_the_reason(home):
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with (home / "Downloads" / "scan.pdf").open("wb") as handle:
        writer.write(handle)
    result = _read("scan.pdf")
    assert result["ok"] is False and result["error"] == "no_text"
    assert "scanned" in result["message"]


def test_a_password_protected_pdf_is_refused_with_the_reason(home):
    (home / "Downloads" / "plain.pdf").write_bytes(_text_pdf("secret plan"))
    reader = pypdf.PdfReader(str(home / "Downloads" / "plain.pdf"))
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password="hunter2", owner_password="owner", algorithm="AES-128")
    with (home / "Downloads" / "locked.pdf").open("wb") as handle:
        writer.write(handle)
    result = _read("locked.pdf")
    assert result["ok"] is False and result["error"] == "no_text"
    assert "password" in result["message"]
    assert "secret plan" not in str(result)


def test_a_pdf_restricted_only_by_an_owner_password_is_still_read(home):
    (home / "Downloads" / "plain.pdf").write_bytes(_text_pdf("printing restricted"))
    reader = pypdf.PdfReader(str(home / "Downloads" / "plain.pdf"))
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password="", owner_password="owner", algorithm="AES-128")
    with (home / "Downloads" / "restricted.pdf").open("wb") as handle:
        writer.write(handle)
    result = _read("restricted.pdf")
    assert result["ok"] is True and "printing restricted" in result["text"]


def test_docx_tables_are_read_in_order_with_paragraphs(home):
    document = docx.Document()
    document.add_paragraph("Quarterly budget")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Item", "Cost"
    table.cell(1, 0).text, table.cell(1, 1).text = "Laptop", "55000"
    document.add_paragraph("Approved by finance")
    document.save(str(home / "Downloads" / "budget.docx"))
    result = _read("budget.docx")
    assert result["ok"] is True and result["format"] == "docx"
    lines = [line for line in result["text"].split("\n") if line.strip()]
    assert lines == ["Quarterly budget", "Item | Cost", "Laptop | 55000", "Approved by finance"]


def test_a_merged_docx_cell_is_kept_once(home):
    document = docx.Document()
    table = document.add_table(rows=1, cols=3)
    merged = table.cell(0, 0).merge(table.cell(0, 1))
    merged.text = "Total"
    table.cell(0, 2).text = "99"
    document.save(str(home / "Downloads" / "merged.docx"))
    assert _read("merged.docx")["text"].strip() == "Total | 99"


def test_pdf_page_scan_is_bounded():
    assert sft._PDF_MAX_PAGES == 200
