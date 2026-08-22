from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from core.auth import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME

MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

# Logout must always be able to clear a stale/invalid session, so it can't
# be gated on a valid CSRF pair either.
EXEMPT_PATHS = {"/logout"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in MUTATING_METHODS and request.url.path not in EXEMPT_PATHS:
            # No session cookie at all -> nothing to protect (covers /login,
            # /register*, anonymous donations, and the Stripe webhook, which
            # never carries browser cookies in the first place). /refresh is
            # checked via refresh_token specifically, since it fires exactly
            # when access_token has already expired.
            if request.cookies.get(ACCESS_COOKIE_NAME) or request.cookies.get(REFRESH_COOKIE_NAME):
                cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)
                header_csrf = request.headers.get(CSRF_HEADER_NAME)
                if not cookie_csrf or not header_csrf or cookie_csrf != header_csrf:
                    return JSONResponse(status_code=403, content={"detail": "CSRF token missing or invalid"})

        return await call_next(request)
