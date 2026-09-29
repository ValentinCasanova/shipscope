from rest_framework import authentication
from rest_framework.request import Request


class SessionAuthentication(authentication.SessionAuthentication):
    """DRF's session authentication, answering 401 instead of 403 to signed-out requests.

    DRF answers 401 only when the first authentication class names a scheme for the
    WWW-Authenticate header, and its session authentication names none, so a signed-out
    request would get 403, the same as a request the user isn't allowed to make. With a
    scheme, the frontend can tell "signed out" (401) from "not allowed" (403).

    "Session" isn't a registered HTTP authentication scheme, and that's intended: a
    browser shows its password prompt only for schemes it knows, such as Basic.
    """

    def authenticate_header(self, request: Request) -> str:
        return 'Session realm="api"'
