from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_shared_admin_css_served():
    response = client.get("/static/admin/surf-admin.css")
    assert response.status_code == 200
    assert "--sf-river" in response.text
    assert ".sf-app" in response.text


def test_shared_admin_js_served():
    response = client.get("/static/admin/surf-admin.js")
    assert response.status_code == 200
    assert "window.SurfAdmin" in response.text
    assert "toggleTheme" in response.text


def test_landing_does_not_reference_admin_assets():
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/admin/surf-admin.css" not in response.text
    assert "/static/admin/surf-admin.js" not in response.text
