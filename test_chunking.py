from app.services.chunking import chunk_pages, normalize_text


def test_normalize_text_removes_excess_spacing():
    assert normalize_text("A   B\n\n\nC") == "A B\n\nC"


def test_chunk_pages_preserves_page_number_and_overlap():
    text = " ".join(f"palavra{i}" for i in range(500))
    chunks = chunk_pages([(7, text)], chunk_size=300, overlap=50)
    assert len(chunks) > 1
    assert all(chunk.page_number == 7 for chunk in chunks)
    assert chunks[0].chunk_index == 0
    assert chunks[-1].content
