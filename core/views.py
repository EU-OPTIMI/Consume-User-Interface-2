from urllib.parse import urlencode, urljoin

from django.conf import settings
from django.http import HttpResponseRedirect


def auth_logout(request):
    base_url = getattr(settings, "AUTH_SERVICE_BASE_URL", "").strip()
    logout_page = getattr(settings, "AUTH_SERVICE_LOGOUT_PAGE", "/api/auth/logout/")
    print('RequestGET', request.GET)
    next_url =  getattr(settings, "AUTH_LOGOUT_REDIRECT_URL", "http://localhost:8002/consume/")
    print('NEXT URL', next_url)
    #getattr(settings, "AUTH_LOGOUT_REDIRECT_URL", "http://localhost:8002/consume/")
    #request.build_absolute_uri("/")
    print('Logout page:',logout_page )
    print('BASE URL:',base_url)

    if logout_page.startswith("http://") or logout_page.startswith("https://"):
        logout_url = logout_page
        print(logout_page, 'Logout page IF:')
    elif base_url:

        logout_url = urljoin(base_url.rstrip("/") + "/", logout_page.lstrip("/"))
        print('Logout page ELIF:',logout_page )
    else:
        logout_url = logout_page
        print(logout_page, 'Logout page ELSE:')
    print('FINAL URL', logout_url)


    query = urlencode({"next": next_url})
    print('EVERYTHINGINTHEBRACKETS', f"{logout_url}?{query}" )
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
