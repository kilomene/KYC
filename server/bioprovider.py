"""Biometric provider adapter (Phase 4 WS2, decision D5).

Production face match / liveness today run on OUR OWN models (YuNet +
SFace, server/face.py). The Phase 4 plan requires those models to be
benchmarked against specialist providers instead of believed — so this
module defines the adapter interface every provider must implement,
and ships exactly two kinds of implementation:

  SFaceProvider        provider #1: our own pipeline, implemented
                       through this interface (not beside it). The
                       WS2 benchmark harness (scripts/
                       benchmark_biometrics.py) runs THROUGH this
                       class, which is what proves the interface is
                       real: the measured FAR/FRR numbers are numbers
                       for this adapter's code path.
  ExternalProvider     a named slot for a commercial provider
                       (e.g. "external:face-compare-vendor"). It is
                       deliberately NOT configured: every operation
                       fails closed with status 'error' and reason
                       'provider_not_configured', and `available()`
                       is False. There is no mock, no stub result,
                       and no path by which an unconfigured provider
                       can produce a similarity or a pass.

What a REAL external evaluation still needs (recorded in
docs/CLAIMS-AUDIT.md): a vendor account + API credentials held by the
platform operator, the vendor's data-processing terms reviewed, and
the same LFW protocol + attack suite run through that vendor's
adapter. Until then the external evaluation is OPEN, not failed and
not passed — this module only guarantees it cannot be faked.
"""
import os

from . import face as FACE

# Cosine threshold for the own-model provider: the production default,
# measured in benchmarks/BIOMETRICS.md (WS2). Kept as a reference to
# face.DEFAULT_THRESHOLD so the two can never drift apart silently.
PRODUCTION_THRESHOLD = FACE.DEFAULT_THRESHOLD


class BiometricProvider:
    """Interface every face provider implements.

    compare(path_a, path_b) -> standard check dict:
        {"status": pass|unclear|fail|error|not_run,
         "findings": {"similarity": float|None, "method": str, ...},
         "reason_codes": [...]}
    embed(path) -> (embedding list | None, error dict | None)
    available() -> bool: True only when the provider can really run.
    """

    name = "abstract"

    def available(self):
        return False

    def compare(self, path_a, path_b):
        raise NotImplementedError

    def embed(self, path):
        raise NotImplementedError


class SFaceProvider(BiometricProvider):
    """Provider #1 — our own YuNet + SFace pipeline (server/face.py),
    exposed through the adapter interface."""

    name = "own:sface"

    def __init__(self, pass_threshold=PRODUCTION_THRESHOLD, margin=FACE.DEFAULT_MARGIN):
        self.pass_threshold = pass_threshold
        self.margin = margin

    def available(self):
        return FACE.cv2 is not None and FACE.models_present()

    def embed(self, path):
        """-> (embedding, None) | (None, no-face marker dict) |
        (None, error dict). Mirrors face.extract_face_feature."""
        if not self.available():
            return None, {"status": "error",
                          "findings": {"error": "face_models_not_fetched_run_scripts/fetch_models.py"},
                          "reason_codes": ["model_missing"]}
        feat, face_row, err = FACE.extract_face_feature(path)
        if err:
            return None, err
        if face_row is None:
            return None, None  # no face found — distinct from an error
        return [float(v) for v in feat], None

    def compare(self, path_a, path_b):
        """Face-match two images through the production decision logic."""
        res = FACE.check_face_match(path_a, path_b, self.pass_threshold, self.margin)
        res = dict(res)
        res["findings"] = {**res.get("findings", {}), "provider": self.name}
        return res

    def similarity(self, emb_a, emb_b):
        return FACE.cosine_similarity(emb_a, emb_b)


class ExternalProvider(BiometricProvider):
    """A named commercial-provider slot. NOT configured: fails closed.

    Constructing one records only the vendor slug the operator intends
    to evaluate. No credentials are read, no network call is made, and
    no result is ever fabricated — every operation reports
    'provider_not_configured' until a real adapter is implemented
    against a real vendor account (Phase 4 WS2 remainder, see
    docs/CLAIMS-AUDIT.md).
    """

    def __init__(self, vendor_slug):
        self.name = f"external:{vendor_slug}"

    def available(self):
        return False

    def _not_configured(self):
        return {"status": "error",
                "findings": {"provider": self.name, "error": "provider_not_configured",
                             "note": "no vendor account/credentials configured for this slot; "
                                     "external provider evaluation is open (Phase 4 WS2)"},
                "reason_codes": ["provider_not_configured"]}

    def compare(self, path_a, path_b):
        return self._not_configured()

    def embed(self, path):
        return None, self._not_configured()


# Registry of provider slots the platform knows about. Only
# "own:sface" can run; the external entries exist so the evaluation
# surface is explicit in code, not so they can be selected into a
# production decision (engine/app never consult this registry —
# production calls server/face.py directly, the same code SFaceProvider
# wraps).
PROVIDER_NAMES = ("own:sface", "external:unconfigured-slot")


def get_provider(name="own:sface"):
    """Resolve a provider by name. Unknown names fail closed to an
    unconfigured external slot rather than raising into a decision."""
    if name == "own:sface":
        return SFaceProvider()
    if name and name.startswith("external:"):
        return ExternalProvider(name.split(":", 1)[1] or "unnamed")
    return ExternalProvider(str(name or "unknown"))
