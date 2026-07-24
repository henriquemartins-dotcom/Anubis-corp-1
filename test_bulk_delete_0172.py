from app.schemas import BulkDeleteEditaisRequest


def test_bulk_delete_request_requires_selection():
    try:
        BulkDeleteEditaisRequest()
    except ValueError:
        pass
    else:
        raise AssertionError("empty bulk delete must be rejected")


def test_bulk_delete_request_accepts_closed_mode():
    payload = BulkDeleteEditaisRequest(delete_closed=True)
    assert payload.delete_closed is True


def test_bulk_delete_ui_controls_exist():
    html = open("app/templates/views/base.html", encoding="utf-8").read()
    js = open("app/static/js/app.js", encoding="utf-8").read()
    assert 'id="deleteSelectedButton"' in html
    assert 'id="deleteClosedButton"' in html
    assert '/api/editais/bulk-delete' in js
    assert 'Promise.allSettled' in js
