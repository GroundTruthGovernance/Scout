"""Earth Engine authentication: per-user OAuth, not a bundled service
account. See docs/ARCHITECTURE.md ("Authentication") for why.

`ee.Authenticate()` opens the user's browser for Google's OAuth consent
screen and stores a token in a per-machine credentials file; `ee.Initialize()`
then reads it. Both are network/browser-interactive and cannot be exercised
in this sandbox (no browser, no network, no Google account) — every method
here is written to be unit-testable by injecting a mock `ee` module, but
the actual end-to-end sign-in flow has never run. That is the first thing
to check by hand on a real machine.
"""

from __future__ import annotations

import os

import ee as _real_ee


class EarthEngineAuth:
    def __init__(self, ee_module=None):
        self.ee = ee_module if ee_module is not None else _real_ee

    def credentials_path(self) -> str:
        return self.ee.oauth.get_credentials_path()

    def is_authenticated(self) -> bool:
        """True if a stored credentials file exists — does not verify the
        token is still valid (that only happens on the next Initialize()/
        API call, which can fail with an auth error even when this
        returns True, e.g. after a revoked grant)."""
        return os.path.exists(self.credentials_path())

    def initialize(self, project: str | None = None) -> None:
        """Raises whatever ee.Initialize() raises (typically an
        ee.EEException) if credentials are missing or invalid — callers
        should catch this and prompt authenticate_interactive()."""
        if project:
            self.ee.Initialize(project=project)
        else:
            self.ee.Initialize()

    def authenticate_interactive(self, auth_mode: str = "notebook") -> None:
        """Blocking call that opens a browser for the OAuth consent
        screen. Must be run off the Qt UI thread — see
        app/ee_auth_worker.py."""
        self.ee.Authenticate(auth_mode=auth_mode)

    def sign_out(self) -> None:
        """Removes the stored credentials file, forcing a fresh sign-in
        next time — the "switch account" / "sign out" case."""
        path = self.credentials_path()
        if os.path.exists(path):
            os.remove(path)
