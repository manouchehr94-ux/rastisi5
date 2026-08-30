"""Admin V2 framing policy for the same-origin Deep Workspace.

Django's global XFrameOptionsMiddleware correctly keeps the application at
DENY by default.  The visual Storefront Builder needs one narrow exception:
authenticated dashboard screens explicitly requested with ``?embed=1`` may be
framed by another page on the *same origin*.  SAMEORIGIN keeps third-party
framing blocked and does not weaken CSRF protection.
"""
from __future__ import annotations


class AdminEmbedFrameOptionsMiddleware:
    """Allow only explicit authenticated dashboard embeds, same-origin only."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        user = getattr(request, "user", None)
        is_dashboard = getattr(match, "namespace", None) == "dashboard"
        is_authenticated = bool(user and getattr(user, "is_authenticated", False))
        if request.GET.get("embed") == "1" and is_dashboard and is_authenticated:
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response
