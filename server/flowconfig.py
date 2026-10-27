"""Per-tenant, per-level flow configuration (Phase 2, item 6).

Versioned rows in flow_configs; the active config is the highest version
for (tenant, env, level). No row = the defaults below, which reproduce
the Phase 1/2 built-in behaviour exactly. The decision engine reads the
active config; every decision records the config_version it used.
"""
import json
from .db import new_id, now_iso

# document_framing is a REQUIRED, decision-bearing check for document
# sessions (owner's order, 2026-10-26): a capture with no detectable
# document in frame auto-rejects; it is not a mere risk signal. It is
# conditionally required — credential-seeded sessions without a
# document have no framing result and framing is never inherited
# (server/credentials.py); see server/engine.py.
DEFAULT_REQUIRED = {
    1: ["capture_quality", "document_framing", "document_classification", "data_consistency", "ocr", "expiry_age", "consistency"],
    2: ["capture_quality", "document_framing", "document_classification", "data_consistency", "ocr", "mrz", "expiry_age", "consistency", "authenticity", "face_match", "face_track", "liveness", "deepfake"],
    3: ["capture_quality", "document_framing", "document_classification", "data_consistency", "ocr", "mrz", "expiry_age", "consistency", "authenticity", "face_match", "face_track", "liveness", "deepfake", "poa", "screening_sanctions"],
}
KNOWN_CHECKS = ["capture_quality", "ocr", "mrz", "expiry_age", "consistency",
                "authenticity", "face_match", "liveness", "poa", "screening_sanctions",
                "document_framing", "location_consistency", "vpn_proxy",
                "number_tally",
                "mrz_viz_consistency", "code_decode", "verification_layers", "deepfake",
                "face_track", "biometric_evidence", "document_classification",
                "data_consistency", "document_evidence"]

def default_config(level):
    return {
        "required_checks": list(DEFAULT_REQUIRED.get(level, DEFAULT_REQUIRED[2])),
        "face_pass_threshold": 0.363,   # OpenCV's published SFace cosine threshold
        "face_margin": 0.05,
        "risk_auto_approve_ceiling": 20,  # auto-approve only at band 'low'
        "poa_window_days": 90,
        "screening_threshold": 80,
        "sla_hours": 24,
        "four_eyes": True,
    }

def get_config(db, tenant_id, env, level):
    """-> (config_dict, version_int). Version 0 means 'defaults'."""
    row = db.one("SELECT * FROM flow_configs WHERE tenant_id=? AND env=? AND level=? ORDER BY version DESC LIMIT 1",
                 (tenant_id, env, level))
    if not row:
        return default_config(level), 0
    cfg = default_config(level)
    try:
        cfg.update(json.loads(row["config"] or "{}"))
    except Exception:
        pass
    return cfg, int(row["version"])

def validate_config_patch(patch):
    """Validate a partial config update. Returns (clean_patch, error)."""
    if not isinstance(patch, dict):
        return None, "config must be an object"
    clean = {}
    for k, v in patch.items():
        if k == "required_checks":
            if not isinstance(v, list) or not v or any(c not in KNOWN_CHECKS for c in v):
                return None, f"required_checks must be a non-empty list drawn from {KNOWN_CHECKS}"
            clean[k] = list(dict.fromkeys(v))
        elif k in ("face_pass_threshold", "face_margin"):
            if not isinstance(v, (int, float)) or not (0 <= float(v) <= 1):
                return None, f"{k} must be a number in [0,1]"
            clean[k] = float(v)
        elif k == "risk_auto_approve_ceiling":
            if not isinstance(v, (int, float)) or not (-1 <= float(v) <= 100):
                return None, "risk_auto_approve_ceiling must be in [-1,100]"
            clean[k] = v
        elif k in ("poa_window_days", "sla_hours"):
            if not isinstance(v, int) or v <= 0:
                return None, f"{k} must be a positive integer"
            clean[k] = v
        elif k == "screening_threshold":
            if not isinstance(v, (int, float)) or not (0 <= float(v) <= 100):
                return None, "screening_threshold must be in [0,100]"
            clean[k] = v
        elif k == "four_eyes":
            if not isinstance(v, bool):
                return None, "four_eyes must be a boolean"
            clean[k] = v
        else:
            return None, f"unknown config key: {k}"
    return clean, None

def put_config(db, tenant_id, env, level, patch):
    """Store a new config version = current active merged with patch."""
    current, version = get_config(db, tenant_id, env, level)
    current.update(patch)
    new_version = version + 1
    db.execute("INSERT INTO flow_configs(id,tenant_id,env,level,version,config,created_at) VALUES(?,?,?,?,?,?,?)",
               (new_id(), tenant_id, env, level, new_version, json.dumps(current), now_iso()))
    return current, new_version
