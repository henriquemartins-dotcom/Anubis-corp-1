import httpx

from app.services.pncp import PNCPClient, PNCPTemporaryError


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def get(self, url, params=None):
        self.calls += 1
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        return None


def response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("GET", "https://pncp.gov.br/test"))


def test_temporary_503_is_retried(monkeypatch):
    client = PNCPClient()
    fake = FakeClient([response(503), response(200)])
    client.client.close()
    client.client = fake
    monkeypatch.setattr("app.services.pncp.time.sleep", lambda _: None)
    monkeypatch.setattr("app.services.pncp.settings.pncp_request_delay_seconds", 0)
    monkeypatch.setattr("app.services.pncp.settings.pncp_retry_base_delay_seconds", 0)
    monkeypatch.setattr("app.services.pncp.settings.pncp_max_retries", 5)

    result = client._get("https://pncp.gov.br/test")

    assert result.status_code == 200
    assert fake.calls == 2


def test_temporary_error_is_raised_after_retry_limit(monkeypatch):
    client = PNCPClient()
    fake = FakeClient([response(503), response(503)])
    client.client.close()
    client.client = fake
    monkeypatch.setattr("app.services.pncp.time.sleep", lambda _: None)
    monkeypatch.setattr("app.services.pncp.settings.pncp_request_delay_seconds", 0)
    monkeypatch.setattr("app.services.pncp.settings.pncp_retry_base_delay_seconds", 0)
    monkeypatch.setattr("app.services.pncp.settings.pncp_max_retries", 2)

    try:
        client._get("https://pncp.gov.br/test")
    except PNCPTemporaryError:
        pass
    else:
        raise AssertionError("PNCPTemporaryError esperado")

    assert fake.calls == 2
