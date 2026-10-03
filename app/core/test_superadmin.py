from app.core.superadmin import is_configured_superadmin_email


def test_is_configured_superadmin_email_case_insensitive(monkeypatch):
    monkeypatch.setenv("SUPERADMIN_EMAIL", "TamilSanMia@gmail.com")
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert is_configured_superadmin_email("tamilsanmia@gmail.com")
    get_settings.cache_clear()
