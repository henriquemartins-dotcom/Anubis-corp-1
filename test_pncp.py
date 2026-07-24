from app.services.pncp import extract_cnpj, is_allowed_pncp_url, map_publication_record, parse_datetime


def sample_record():
    return {
        "numeroControlePNCP": "12345678000199-1-000321/2026",
        "numeroCompra": "PE-12/2026",
        "anoCompra": 2026,
        "sequencialCompra": 321,
        "processo": "001/2026",
        "objetoCompra": "Contratação de solução de software",
        "modalidadeId": 6,
        "modalidadeNome": "Pregão - Eletrônico",
        "situacaoCompraNome": "Divulgada no PNCP",
        "valorTotalEstimado": 12345.67,
        "dataEncerramentoProposta": "2026-08-10T10:00:00",
        "orgaoEntidade": {"cnpj": "12.345.678/0001-99", "razaoSocial": "Órgão Teste"},
        "unidadeOrgao": {"ufSigla": "SP", "municipioNome": "São Paulo"},
    }


def test_extract_cnpj():
    assert extract_cnpj(sample_record()) == "12345678000199"


def test_map_publication_record():
    mapped = map_publication_record(sample_record())
    assert mapped["pncp_id"] == "12345678000199-1-000321/2026"
    assert mapped["modality_id"] == 6
    assert mapped["organization"] == "Órgão Teste"
    assert mapped["sequence"] == 321


def test_parse_datetime_adds_brasilia_timezone_when_missing():
    parsed = parse_datetime("2026-08-10T10:00:00")
    assert parsed is not None
    assert parsed.tzinfo is not None


def test_pncp_download_url_restriction():
    assert is_allowed_pncp_url("https://pncp.gov.br/pncp-api/v1/arquivo")
    assert is_allowed_pncp_url("https://www.pncp.gov.br/pncp-api/v1/arquivo")
    assert not is_allowed_pncp_url("http://pncp.gov.br/arquivo")
    assert not is_allowed_pncp_url("https://example.com/arquivo")
    assert not is_allowed_pncp_url("file:///etc/passwd")

from datetime import date

from app.schemas import SyncPNCPRequest
from app.services.pncp import iter_date_windows


def test_period_longer_than_one_year_is_accepted():
    request = SyncPNCPRequest(
        data_inicial=date(2024, 1, 1),
        data_final=date(2025, 6, 30),
        modalidades=[4, 6],
    )
    assert (request.data_final - request.data_inicial).days > 365


def test_long_period_is_split_without_gaps_or_overlap():
    windows = list(iter_date_windows(date(2024, 1, 1), date(2025, 6, 30), 30))
    assert windows[0] == (date(2024, 1, 1), date(2024, 1, 30))
    assert windows[-1][1] == date(2025, 6, 30)
    for current, following in zip(windows, windows[1:]):
        assert (following[0] - current[1]).days == 1
        assert (current[1] - current[0]).days <= 29


def test_period_of_multiple_years_has_no_artificial_31_day_limit():
    request = SyncPNCPRequest(
        data_inicial=date(2020, 1, 1),
        data_final=date(2026, 7, 16),
        modalidades=[1, 4, 6],
    )
    assert request.uf is None
    assert request.data_final.year - request.data_inicial.year >= 6


def test_uf_is_optional_and_normalized_when_informed():
    national = SyncPNCPRequest(
        data_inicial=date(2026, 1, 1), data_final=date(2026, 1, 2), modalidades=[6]
    )
    filtered = SyncPNCPRequest(
        data_inicial=date(2026, 1, 1), data_final=date(2026, 1, 2), modalidades=[6], uf="es"
    )
    assert national.uf is None
    assert filtered.uf == "ES"
