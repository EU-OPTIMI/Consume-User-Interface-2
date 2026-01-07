import logging
from urllib.parse import urljoin, urlencode

import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect


DEFAULT_ALLOWLIST = [
    "/health",
    "/metrics",
    "/api/auth/profile",
]


class AuthServiceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger(__name__)

    def __call__(self, request):
        if not getattr(settings, "AUTH_SERVICE_ENFORCE", True):
            return self.get_response(request)

        base_url = getattr(settings, "AUTH_SERVICE_BASE_URL", "").strip()
        if not base_url:
            self.logger.warning(
                "Auth enforcement skipped: AUTH_SERVICE_BASE_URL not set path=%s",
                request.path,
            )
            return self.get_response(request)

        if self._is_allowlisted(request.path):
            return self.get_response(request)

        cookies = self._build_cookie_jar(request)
        if not cookies:
            return self._deny(request, "missing_cookie")

        profile_url = self._build_profile_url(base_url)
        try:
            response = requests.get(
                profile_url,
                cookies=cookies,
                timeout=getattr(settings, "AUTH_SERVICE_TIMEOUT", 3),
                verify=getattr(settings, "AUTH_SERVICE_VERIFY_SSL", True),
            )
        except requests.RequestException as exc:
            self.logger.warning(
                "Auth service request failed path=%s reason=%s",
                request.path,
                exc,
            )
            return self._deny(request, "auth_service_error")

        if response.status_code == 200:
            profile = {}
            try:
                profile = response.json() or {}
            except ValueError:
                self.logger.warning(
                    "Auth service returned invalid JSON path=%s", request.path
                )
            request.auth_profile = profile
            request.auth_authenticated = True
            user_id = self._extract_user_id(profile)
            self.logger.info(
                "Auth success path=%s user=%s",
                request.path,
                user_id or "unknown",
            )
            return self.get_response(request)

        if response.status_code == 401:
            return self._deny(request, "unauthenticated")

        self.logger.warning(
            "Auth service unexpected status=%s path=%s",
            response.status_code,
            request.path,
        )
        return self._deny(request, f"status_{response.status_code}")

    def _is_allowlisted(self, path):
        allowlist = list(DEFAULT_ALLOWLIST)
        extra = getattr(settings, "AUTH_SERVICE_ALLOWLIST", [])
        if extra:
            allowlist.extend(extra)
        for entry in allowlist:
            if not entry:
                continue
            if path == entry:
                return True
            if path.startswith(entry.rstrip("/") + "/"):
                return True
        return False

    def _build_cookie_jar(self, request):
        cookie_names = []
        configured = getattr(settings, "AUTH_SERVICE_SESSION_COOKIE", "sessionid")
        cookie_names.append(configured)
        cookie_names.extend(["sessionid", "auth_sessionid"])

        cookies = {}
        seen = set()
        for name in cookie_names:
            if name in seen:
                continue
            seen.add(name)
            value = request.COOKIES.get(name)
            if value:
                cookies[name] = value
        return cookies

    def _build_profile_url(self, base_url):
        endpoint = getattr(settings, "AUTH_SERVICE_PROFILE_ENDPOINT", "/api/auth/me/")
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))

    def _build_login_url(self, base_url, next_url):
        login_page = getattr(
            settings, "AUTH_SERVICE_LOGIN_PAGE", "/api/auth/login-page/"
        )
        if login_page.startswith("http://") or login_page.startswith("https://"):
            login_url = login_page
        else:
            login_url = urljoin(base_url.rstrip("/") + "/", login_page.lstrip("/"))
        query = urlencode({"next": next_url})
        return f"{login_url}?{query}"

    def _is_api_request(self, request):
        accept = request.headers.get("Accept", "")
        content_type = request.headers.get("Content-Type", "")
        if "application/json" in accept.lower():
            return True
        if "application/json" in content_type.lower():
            return True
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return True
        if request.path.startswith("/api/"):
            return True
        return False

    def _deny(self, request, reason):
        self.logger.info(
            "Auth failure path=%s reason=%s",
            request.path,
            reason,
        )
        if request.method in ("GET", "HEAD") and not self._is_api_request(request):
            base_url = getattr(settings, "AUTH_SERVICE_BASE_URL", "").strip()
            next_url = request.build_absolute_uri()
            login_url = self._build_login_url(base_url, next_url)
            return HttpResponseRedirect(login_url)
        return JsonResponse({"detail": "Authentication required."}, status=401)

    def _extract_user_id(self, profile):
        if not isinstance(profile, dict):
            return None
        for key in ("id", "user_id", "uuid", "email", "username"):
            value = profile.get(key)
            if value:
                return value
        return None
