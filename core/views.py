from urllib.parse import urlencode, urljoin

from django.conf import settings
from django.http import HttpResponseRedirect


def auth_logout(request):
    base_url = getattr(settings, "AUTH_SERVICE_BASE_URL", "").strip()
    logout_page = getattr(settings, "AUTH_SERVICE_LOGOUT_PAGE", "/api/auth/logout/")
    next_url = request.GET.get("next") or request.build_absolute_uri("/")

    if logout_page.startswith("http://") or logout_page.startswith("https://"):
        logout_url = logout_page
    elif base_url:
        logout_url = urljoin(base_url.rstrip("/") + "/", logout_page.lstrip("/"))
    else:
        logout_url = logout_page

    query = urlencode({"next": next_url})
    response = HttpResponseRedirect(f"{logout_url}?{query}")

    cookie_names = [
        getattr(settings, "AUTH_SERVICE_SESSION_COOKIE", "sessionid"),
        "sessionid",
        "auth_sessionid",
    ]
    seen = set()
    for name in cookie_names:
        if name in seen:
            continue
        seen.add(name)
        response.delete_cookie(name)

    return response
