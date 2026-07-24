import io
import zipfile

from app.services.documents import extract_payloads
from app.services.utils import safe_filename


def test_safe_filename_removes_path_and_unsafe_chars():
    assert safe_filename("../../edital: teste?.pdf") == "edital_ teste_.pdf"


def test_zip_is_detected_by_signature_even_with_wrong_extension():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("anexo.txt", "Prazo final: 10 de agosto.")
    payloads = extract_payloads(buffer.getvalue(), "arquivo.pdf", "application/octet-stream")
    assert len(payloads) == 1
    assert payloads[0].filename == "anexo.txt"
    assert "Prazo final" in payloads[0].pages[0][1]
