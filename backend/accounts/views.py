"""Signing in with Google, and the session that follows (the /api/auth/ endpoints).

Django runs the whole OAuth flow and gives the browser only its session cookie, so no
Google token ever reaches JavaScript (the backend-for-frontend pattern):

1. The sign-in button links to google_login, which stores a new flow in the session
   and redirects to Google.
2. Google redirects back to google_callback, which checks the flow, exchanges the code,
   checks the ID token, and signs the user in with a Django session.
3. The frontend asks the session endpoint who is signed in.

Every failure redirects back into the app with a message, and logs a reason code. No
code, token, state, or email is logged.
"""

import logging
import re
import time
from typing import Any

from django.contrib.auth import login, logout
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations import google

from .services import google_client, google_config, sign_in_with_google

logger = logging.getLogger(__name__)

# Where the session keeps the flows in progress, keyed by their state, so sign-ins
# started in two tabs don't overwrite each other.
FLOWS_SESSION_KEY = "google_oauth_flows"
# How long a flow can wait for Google's redirect.
FLOW_MAX_AGE_SECONDS = 10 * 60
# Flows started and never finished, beyond which the oldest are dropped.
MAX_FLOWS = 5
# Where signing in ends when the app didn't ask for anywhere else.
DEFAULT_NEXT = "/orders"


def _safe_next(value: str | None) -> str:
    """value if it's a path inside the app, otherwise DEFAULT_NEXT.

    Refuses full URLs and anything a browser reads as one, such as //evil.example or
    /\\evil.example, so signing in can't send the user to another site.
    """
    if (
        value
        and value.startswith("/")
        and url_has_allowed_host_and_scheme(value, allowed_hosts=set(), require_https=True)
    ):
        return value
    return DEFAULT_NEXT


def _redirect_uri(request: HttpRequest) -> str:
    """The callback's full URL, as registered with Google for this environment.

    Built from the request: behind CloudFront, Django sees the browser's host and knows
    the browser used HTTPS (settings.py).
    """
    return request.build_absolute_uri(reverse("google-callback"))


def _signin_failed(reason: str, *, cancelled: bool = False) -> HttpResponseRedirect:
    if cancelled:
        logger.info("Google sign-in cancelled at Google")
        return HttpResponseRedirect("/?signin=cancelled")
    logger.warning("Google sign-in failed: %s", reason)
    return HttpResponseRedirect("/?signin=failed")


@never_cache
@require_GET
def google_login(request: HttpRequest) -> HttpResponse:
    """Start signing in: store a new flow in the session, and redirect to Google.

    A plain navigation, not an API call: the browser follows the redirect to Google's
    own screen. ?next= is where the app goes once signed in.
    """
    if not google_config().configured:
        return HttpResponse(
            "Google sign-in isn't configured.", status=503, content_type="text/plain"
        )

    state = google.new_state()
    nonce = google.new_nonce()
    pkce = google.new_pkce_pair()
    now = time.time()
    flows: dict[str, dict[str, Any]] = {
        key: flow
        for key, flow in request.session.get(FLOWS_SESSION_KEY, {}).items()
        if now - flow["started"] < FLOW_MAX_AGE_SECONDS
    }
    flows[state] = {
        "nonce": nonce,
        "verifier": pkce.verifier,
        "next": _safe_next(request.GET.get("next")),
        "started": now,
    }
    # Dicts keep insertion order, so the oldest flows come first.
    request.session[FLOWS_SESSION_KEY] = dict(list(flows.items())[-MAX_FLOWS:])

    return HttpResponseRedirect(
        google_client().authorization_url(
            redirect_uri=_redirect_uri(request),
            state=state,
            nonce=nonce,
            code_challenge=pkce.challenge,
        )
    )


@never_cache
@require_GET
def google_callback(request: HttpRequest) -> HttpResponse:
    """Finish signing in, where Google redirects the browser with ?code and ?state."""
    flow = _take_flow(request, request.GET.get("state", ""))
    error = request.GET.get("error")
    if error:
        # access_denied: the user cancelled on Google's screen. Google's error codes are
        # short snake_case words; anything else is logged as "other", since anyone can
        # put anything in this URL.
        code_name = error if re.fullmatch(r"[a-z_]{1,40}", error) else "other"
        return _signin_failed(f"google_error:{code_name}", cancelled=error == "access_denied")
    if flow is None:
        # No such state in this browser's session: a forged or replayed callback, a
        # sign-in started on another host, or a session cookie that didn't come back.
        return _signin_failed("unknown_state")
    if time.time() - flow["started"] >= FLOW_MAX_AGE_SECONDS:
        return _signin_failed("flow_expired")
    code = request.GET.get("code")
    if not code:
        return _signin_failed("missing_code")

    client = google_client()
    try:
        tokens = client.exchange_code(
            code=code, redirect_uri=_redirect_uri(request), code_verifier=flow["verifier"]
        )
        identity = client.verify_id_token(tokens.id_token, nonce=flow["nonce"])
    except google.GoogleOAuthError as failure:
        # The exception's class and message name the failed check, never a token.
        return _signin_failed(f"{type(failure).__name__}: {failure}")

    user, created = sign_in_with_google(identity)
    if not user.is_active:
        return _signin_failed(f"inactive_user:{user.pk}")
    # Issues a new session ID, so an ID planted before signing in is useless after it.
    login(request, user)
    logger.info("Google sign-in: user %s%s", user.pk, " (new user)" if created else "")
    return HttpResponseRedirect(flow["next"])


def _take_flow(request: HttpRequest, state: str) -> dict[str, Any] | None:
    """Remove the flow for this state from the session and return it, so it's used once."""
    flows = request.session.get(FLOWS_SESSION_KEY, {})
    flow = flows.pop(state, None)
    if flow is not None:
        # Written back only when something changed: a callback without a session then
        # doesn't create one.
        request.session[FLOWS_SESSION_KEY] = flows
    return flow


@method_decorator(never_cache, name="dispatch")
class SessionView(APIView):
    """GET: who is signed in, or {"user": null}. DELETE: sign out.

    GET answers 200 when signed out too: the app asks on every page load, and browsers
    log every 4xx answer to fetch as an error. It also sets the csrftoken cookie, whose
    value the frontend sends as X-CSRFToken on unsafe requests.
    """

    def get_permissions(self) -> list[Any]:
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request: Request) -> Response:
        user = request.user
        if not user.is_authenticated:
            return Response({"user": None})
        return Response(
            {
                "user": {
                    "id": user.pk,
                    "email": user.email,
                    "name": user.get_full_name() or user.email or user.get_username(),
                }
            }
        )

    def delete(self, request: Request) -> Response:
        # DRF's session authentication has already checked the CSRF token.
        user_id = request.user.pk
        logout(request)
        logger.info("Signed out: user %s", user_id)
        return Response(status=204)
