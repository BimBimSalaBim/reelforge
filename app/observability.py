"""Optional Sentry/GlitchTip error tracking (Hermes integration layer).

Reads SENTRY_DSN from the environment; no DSN = pure no-op, so upstream
behaviour is unchanged when the variable is absent. Kept in one module so the
diff against upstream stays tiny and merges stay clean.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("reelforge.observability")


def init_sentry() -> None:
    """Initialise the Sentry SDK once, if a DSN is configured."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk  # local import: optional dependency at runtime

        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("REELFORGE_ENV", "production"),
            traces_sample_rate=0.05,
            send_default_pii=False,
        )
        host = dsn.split("@")[-1] if "@" in dsn else "?"
        log.info("sentry initialized (endpoint %s)", host)
    except Exception as exc:  # pragma: no cover - never take the app down
        log.warning("sentry init skipped: %s", exc)
