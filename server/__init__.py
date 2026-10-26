"""KYC local server package (Phases 1-3).

Standard library + Pillow + numpy/OpenCV by design for the local-first
build. Same API contract as docs/API.md so this can move to
Supabase+Cloudflare.
"""
__version__ = "0.4.0"
RULES_VERSION = "2026-10-26.3"
# v2 (2026-10-26): consent text now also discloses collection of the
# device type and IP address, used for a location check. Prior (v1)
# consents do not silently cover that collection.
CONSENT_TEXT_VERSION = "v2"
