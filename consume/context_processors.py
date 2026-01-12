from urllib.parse import urljoin

from django.conf import settings


def auth_urls(request):
    auth_base = getattr(settings, "AUTH_SERVICE_BASE_URL", "").rstrip("/")
    login_page = getattr(settings, "AUTH_SERVICE_LOGIN_PAGE", "/api/auth/login-page/")
    logout_page = getattr(settings, "AUTH_SERVICE_LOGOUT_PAGE", "/api/auth/logout/")

    auth_login_url = (
        urljoin(f"{auth_base}/", login_page.lstrip("/")) if auth_base else login_page
    )
    auth_logout_url = (
        urljoin(f"{auth_base}/", logout_page.lstrip("/")) if auth_base else logout_page
    )

    return {
        "auth_login_url": auth_login_url,
        "auth_logout_url": auth_logout_url,
        "provider_cookie_name": getattr(
            settings, "PROVIDER_SESSION_COOKIE", "provider_sessionid"
        ),
    }
