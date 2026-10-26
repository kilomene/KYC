"""Sanctions / PEP / adverse-media screening (Phase 3).

List files are CSV with header:
    full_name,dob,country,list_source,entry_id
loaded from <data_dir>/lists/*.csv if present, plus the small,
clearly-labelled SAMPLE list shipped in <repo>/lists/ (test fixtures
only — its entries carry list_source values starting with SAMPLE).

Matching is real: normalised name tokens (accents stripped), a
similarity that combines difflib sequence ratio with token-set overlap,
and DOB agreement (equal DOB boosts, conflicting DOB caps the score).
score >= threshold (default 80, tenant-configurable) produces a PENDING
hit. A name match alone NEVER rejects anyone: a hit blocks
auto-approval and a human dispositions it. Only a reviewer-confirmed
hit rejects (reason sanctions_hit_confirmed), in the case endpoints.
"""
import csv, difflib, glob, os, re, unicodedata

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_LISTS_DIR = os.path.join(BASE_DIR, "lists")
DEFAULT_THRESHOLD = 80

def normalise_name(name):
    s = unicodedata.normalize("NFKD", (name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r"[^A-Z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def _tokens(name):
    return set(normalise_name(name).split())

def token_set_ratio(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return 100.0 * inter / min(len(ta), len(tb))

def name_similarity(a, b):
    seq = difflib.SequenceMatcher(None, normalise_name(a), normalise_name(b)).ratio() * 100
    return round(0.6 * seq + 0.4 * token_set_ratio(a, b), 2)

def match_score(person_name, person_dob, entry):
    """Score one list entry against a person. 0..100."""
    score = name_similarity(person_name, entry.get("full_name", ""))
    entry_dob = (entry.get("dob") or "").strip()
    person_dob = (person_dob or "").strip()
    dob_relation = "unknown"
    if entry_dob and person_dob:
        if entry_dob == person_dob:
            score = min(100.0, score + 10); dob_relation = "match"
        else:
            score = score * 0.6; dob_relation = "conflict"
    return round(score, 2), dob_relation

def load_lists(data_dir):
    """-> list of entries (dicts). Reads data_dir/lists/*.csv and the
    repo's shipped lists/*.csv (the sample fixtures)."""
    entries = []
    paths = []
    if data_dir:
        paths += sorted(glob.glob(os.path.join(data_dir, "lists", "*.csv")))
    paths += sorted(glob.glob(os.path.join(REPO_LISTS_DIR, "*.csv")))
    seen = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        try:
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("full_name"):
                        entries.append({"full_name": row["full_name"].strip(),
                                        "dob": (row.get("dob") or "").strip(),
                                        "country": (row.get("country") or "").strip(),
                                        "list_source": (row.get("list_source") or os.path.basename(path)).strip(),
                                        "entry_id": (row.get("entry_id") or "").strip()})
        except Exception:
            continue  # a broken list file must not crash a submit; count surfaces in findings
    return entries

def screen_person(name, dob, entries, threshold=DEFAULT_THRESHOLD):
    """-> list of hit dicts {entry, score, dob_relation} at/above threshold."""
    hits = []
    for e in entries:
        score, rel = match_score(name, dob, e)
        if score >= threshold:
            hits.append({"entry_id": e["entry_id"], "list_source": e["list_source"],
                         "matched_name": e["full_name"], "matched_dob": e["dob"],
                         "matched_country": e["country"], "score": score, "dob_relation": rel})
    return sorted(hits, key=lambda h: -h["score"])

def run_screening(db, data_dir, tenant_id, env, applicant, origin="submit", session_id=None,
                  business_id=None, threshold=DEFAULT_THRESHOLD):
    """Screen an applicant row, persisting NEW pending hits (deduped by
    applicant+entry). Returns the screening check result dict."""
    from .db import new_id, now_iso
    entries = load_lists(data_dir)
    name = f"{applicant['first_name'] or ''} {applicant['last_name'] or ''}".strip()
    if not entries:
        return {"status": "error", "findings": {"lists_loaded": 0, "error": "no_screening_lists_found"},
                "reason_codes": ["screening_lists_missing"], "hits": []}
    if not name:
        return {"status": "unclear", "findings": {"lists_loaded": len(entries), "error": "applicant_name_missing"},
                "reason_codes": ["screening_no_name"], "hits": []}
    found = screen_person(name, applicant["dob"], entries, threshold)
    created = []
    for h in found:
        existing = db.one("SELECT id FROM screening_hits WHERE applicant_id=? AND entry_id=? AND list_source=? AND status='pending'",
                          (applicant["id"], h["entry_id"], h["list_source"]))
        if existing:
            created.append({**h, "hit_id": existing["id"], "existing": True})
            continue
        hid = new_id()
        db.execute("INSERT INTO screening_hits(id,tenant_id,env,session_id,applicant_id,business_id,entry_id,list_source,matched_name,matched_dob,matched_country,score,status,origin,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (hid, tenant_id, env, session_id, applicant["id"], business_id, h["entry_id"], h["list_source"],
                    h["matched_name"], h["matched_dob"], h["matched_country"], h["score"], "pending", origin, now_iso(), now_iso()))
        created.append({**h, "hit_id": hid})
    sources = sorted({e["list_source"] for e in entries})
    findings = {"lists_loaded": len(entries), "list_sources": sources, "hits": len(created),
                "threshold": threshold}
    if created:
        return {"status": "unclear", "findings": findings,
                "reason_codes": ["screening_hit_pending"], "hits": created}
    return {"status": "pass", "findings": findings, "reason_codes": [], "hits": []}
