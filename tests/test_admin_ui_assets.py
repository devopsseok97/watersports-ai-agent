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


def test_shared_admin_theme_contract():
    css = client.get("/static/admin/surf-admin.css")
    js = client.get("/static/admin/surf-admin.js")
    assert css.status_code == 200
    assert js.status_code == 200
    assert '[data-theme="dark"]' in css.text
    assert "setAttribute('data-theme', 'dark')" in js.text or 'setAttribute("data-theme", "dark")' in js.text


def test_landing_does_not_reference_admin_assets():
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/admin/surf-admin.css" not in response.text
    assert "/static/admin/surf-admin.js" not in response.text
