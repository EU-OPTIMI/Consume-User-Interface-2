import logging
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect

logger = logging.getLogger(__name__)


def _parse_json_response(response, context):
    content_type = (response.headers.get("Content-Type") or "").lower()
    if response.status_code != 200 or "json" not in content_type:
        body_preview = response.content[:200].decode("utf-8", errors="replace")
        logger.warning(
            "%s unexpected response status=%s content_type=%s headers=%s body_preview=%s",
            context,
            response.status_code,
            response.headers.get("Content-Type", ""),
            response.headers,
            body_preview,
        )
        return None
    try:
        return response.json()
    except ValueError:
        body_preview = response.content[:200].decode("utf-8", errors="replace")
        logger.warning(
            "%s invalid JSON status=%s content_type=%s body_preview=%s",
            context,
            response.status_code,
            response.headers.get("Content-Type", ""),
            body_preview,
        )
        return None


class RemoteAuthUser:
    def __init__(self, profile):
        self.profile = profile or {}
        self.id = self.profile.get("id") or self.profile.get("uuid")
        self.username = (
            self.profile.get("username")
            or self.profile.get("email")
            or self.profile.get("name")
        )
        self.email = self.profile.get("email")
        self.is_staff = bool(self.profile.get("is_staff", False))
        self.is_superuser = bool(self.profile.get("is_superuser", False))
        self.is_authenticated = True

    @property
    def is_anonymous(self):
        return False

    def __str__(self):
        return self.username or "authenticated-user"


class AuthServiceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.base_url = getattr(settings, "AUTH_SERVICE_BASE_URL", "").rstrip("/")
        self.profile_endpoint = getattr(
            settings, "AUTH_SERVICE_PROFILE_ENDPOINT", "/api/auth/me/"
        )
        self.login_page = getattr(
            settings, "AUTH_SERVICE_LOGIN_PAGE", "/api/auth/login-page/"
        )
        self.session_cookie_name = getattr(
            settings, "AUTH_SERVICE_SESSION_COOKIE", settings.SESSION_COOKIE_NAME
        )
        self.timeout = getattr(settings, "AUTH_SERVICE_TIMEOUT", 3)
        self.verify_ssl = getattr(settings, "AUTH_SERVICE_VERIFY_SSL", True)
        configured_allowlist = tuple(getattr(settings, "AUTH_SERVICE_ALLOWLIST", []))
        builtin_allowlist = (
            "/health",
            "/metrics",
            "/api/auth/profile",
            "/api/auth/profile/",
        )
        self.allowlist = tuple(dict.fromkeys([*configured_allowlist, *builtin_allowlist]))
        self.enforce = getattr(settings, "AUTH_SERVICE_ENFORCE", False)

    def __call__(self, request):
        request.auth_user = None
        request.auth_profile = None

        if not self.base_url or self._is_allowlisted(request.path):
            return self.get_response(request)

        session_token, auth_cookies = self._get_session_cookies(request)
        if not session_token:
            if self.enforce:
                return self._reject_or_redirect(
                    request, "Authentication cookie missing."
                )
            return self.get_response(request)

        profile, failure_reason = self._fetch_profile(auth_cookies)
        if profile:
            user = RemoteAuthUser(profile)
            request.auth_user = user
            request.auth_profile = profile
            request.user = user
            request._cached_user = user
            logger.info("Auth success path=%s user=%s", request.path, user)
        elif self.enforce:
            logger.info("Auth failure path=%s reason=%s", request.path, failure_reason)
            return self._reject_or_redirect(
                request, failure_reason or "Authentication failed."
            )

        return self.get_response(request)

    def _is_allowlisted(self, path):
        return any(path.startswith(prefix) for prefix in self.allowlist)

    def _get_session_cookies(self, request):
        cookie_names = (self.session_cookie_name, "sessionid", "auth_sessionid")
        session_token = None
        cookies = {}
        for name in cookie_names:
            token = request.COOKIES.get(name)
            if token:
                cookies[name] = token
                if session_token is None:
                    session_token = token
        if session_token:
            cookies.setdefault(self.session_cookie_name, session_token)
            cookies.setdefault("sessionid", session_token)
            cookies.setdefault("auth_sessionid", session_token)
        return session_token, cookies

    def _fetch_profile(self, cookies):
        url = urljoin(f"{self.base_url}/", self.profile_endpoint.lstrip("/"))
        try:
            response = requests.get(
                url,
                headers={"Accept": "application/json"},
                cookies=cookies,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        except requests.RequestException:
            return None, "Authentication service unavailable."

        if response.status_code == 200:
            payload = _parse_json_response(response, "Auth profile endpoint")
            if payload is None:
                return None, "Authentication service returned invalid profile payload."
            profile = payload.get("user") or payload.get("data") or payload
            return profile, None

        if response.status_code == 401:
            return None, "Authentication expired or invalid."

        return None, "Authentication service error."

    @staticmethod
    def _reject_unauthorized(message):
        return JsonResponse({"detail": message}, status=401)

    def _reject_or_redirect(self, request, message):
        if request.method in ("GET", "HEAD") and self.login_page:
            next_url = request.build_absolute_uri()
            login_url = urljoin(f"{self.base_url}/", self.login_page.lstrip("/"))
            redirect_url = f"{login_url}?next={next_url}"
            return HttpResponseRedirect(redirect_url)
        return self._reject_unauthorized(message)
