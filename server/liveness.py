"""Active liveness (Phase 2): server-generated movement challenge.

The flow issues a random challenge — a sequence of head movements, e.g.
["left", "up"]. The applicant records a short video (browser
MediaRecorder or an uploaded file). The server samples frames, runs
YuNet face detection per frame, and reduces the video to per-frame
FEATURES:

    {face: bool, cx: float, cy: float, size: float, pix_std: float}
    (cx/cy = face centre normalised to frame width/height)

`analyse_features` is a pure function of those features + the challenge,
so the whole decision logic is unit-testable on synthetic sequences —
no video or model needed. A replayed still photo fails twice over: the
face centre never moves AND the pixel variance never changes.

Statuses: pass | fail (static replay, or face mostly absent) |
unclear (face present but the challenged movement is not clearly made —
a human reviews; honest failures of honest users land here) |
error (video unreadable / models missing — never a pass).
"""
import random

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

from . import face as FACE

DIRECTIONS = ("left", "right", "up", "down")
MIN_FACE_RATIO = 0.8       # face must be present in >= 80% of sampled frames
MOVE_THRESHOLD = 0.045     # normalised centre displacement that counts as a movement
STATIC_CENTRE_RANGE = 0.01  # below this total centre range = no real movement
STATIC_PIX_RANGE = 0.5      # below this std of frame pixel-std = frozen image

def new_challenge(rng=None):
    """A fresh challenge: two distinct directions, in order."""
    rng = rng or random.SystemRandom()
    dirs = rng.sample(list(DIRECTIONS), 2)
    return {"movements": dirs, "version": 1}

def _movement_made(centres, direction, start_idx):
    """Scan centres (list of (cx, cy)) from start_idx for a displacement of
    >= MOVE_THRESHOLD in `direction`. Returns (made, end_idx)."""
    if len(centres) < 2:
        return False, start_idx
    axis = 0 if direction in ("left", "right") else 1
    want_negative = direction in ("left", "up")  # image coords: left/up decrease cx/cy
    ref = centres[start_idx][axis]  # displacement is measured from the segment start
    for i in range(start_idx, len(centres)):
        v = centres[i][axis]
        disp = (ref - v) if want_negative else (v - ref)
        if disp >= MOVE_THRESHOLD:
            return True, i
    return False, start_idx

def analyse_features(features, challenge):
    """Pure analysis of sampled frame features against the challenge.

    A feature's "strict" flag separates production-threshold sightings
    from consistency-anchored relaxed ones (see extract_features).
    Presence counts both — a face the detector glimpses weakly but
    continuously IS present — while movement is judged on strict
    sightings alone: identity-grade geometry is never borrowed from
    a weak box. Features written before the flag existed count as
    strict."""
    movements = list((challenge or {}).get("movements") or [])
    n = len(features)
    findings = {"frames_sampled": n, "challenge": movements}
    if n < 4:
        return {"status": "unclear", "findings": {**findings, "error": "too_few_frames"}, "reason_codes": ["liveness_too_few_frames"]}
    faces = [f for f in features if f.get("face")]
    strict_faces = [f for f in faces if f.get("strict", True)]
    ratio = len(faces) / n
    findings["face_ratio"] = round(ratio, 3)
    findings["strict_face_ratio"] = round(len(strict_faces) / n, 3)
    if ratio < MIN_FACE_RATIO:
        return {"status": "fail", "findings": findings, "reason_codes": ["liveness_face_absent"]}
    centres = [(float(f["cx"]), float(f["cy"])) for f in faces]
    xs = [c[0] for c in centres]; ys = [c[1] for c in centres]
    centre_range = max(max(xs) - min(xs), max(ys) - min(ys))
    findings["centre_range"] = round(centre_range, 4)
    pix = [float(f.get("pix_std", 0.0)) for f in features]
    pix_var = (max(pix) - min(pix)) if pix else 0.0
    findings["pixel_std_range"] = round(pix_var, 3)
    if centre_range < STATIC_CENTRE_RANGE and pix_var < STATIC_PIX_RANGE:
        # A replayed still photo / frozen frame: no head movement AND no
        # pixel change. This is a fail, not a review item.
        return {"status": "fail", "findings": {**findings, "static": True}, "reason_codes": ["liveness_static_replay"]}
    if len(strict_faces) >= 4:
        centres = [(float(f["cx"]), float(f["cy"])) for f in strict_faces]
    elif movements:
        # Present (weakly) but too few identity-grade sightings to
        # judge the challenged movements from: honest unclear, never
        # a pass borrowed from weak geometry and never "absent" —
        # the face WAS there.
        findings["movement_basis"] = "insufficient_strict_frames"
        return {"status": "unclear", "findings": findings, "reason_codes": ["liveness_challenge_incomplete"]}
    made, idx = [], 0
    for d in movements:
        ok, idx2 = _movement_made(centres, d, idx)
        if ok:
            made.append(d); idx = idx2
    findings["movements_made"] = made
    if movements and len(made) == len(movements):
        return {"status": "pass", "findings": findings, "reason_codes": []}
    if not movements:
        # No challenge recorded (shouldn't happen): movement alone decides.
        if centre_range >= MOVE_THRESHOLD:
            return {"status": "pass", "findings": findings, "reason_codes": []}
        return {"status": "unclear", "findings": findings, "reason_codes": ["liveness_movement_unclear"]}
    return {"status": "unclear", "findings": findings, "reason_codes": ["liveness_challenge_incomplete"]}

def extract_features(video_path, max_frames=30, _meta=None):
    """Reduce a video to per-frame features via YuNet.

    Frames come from FACE.video_frames: sampled across the FULL
    duration (container frame-count metadata is unreliable on
    MediaRecorder WebM) and orientation-corrected as one clip.

    Presence rescue (2026-10-28, owner session 14): at a steep camera
    angle or against backlight, YuNet's score for a real, continuously
    present face can sit at 0.31-0.38 — under the 0.6 production
    threshold at EVERY scale and after enhancement. A relaxed second
    look (RELAXED_THRESHOLD) therefore runs per frame, but a relaxed
    sighting counts as presence ONLY when it is anchored: a strict
    sighting exists somewhere in the clip and a neighbouring sampled
    frame holds an accepted face. It never feeds movement geometry
    (analyse_features judges movement on strict sightings alone) and
    never identity. Raises on unreadable video."""
    frames, vinfo = FACE.video_frames(video_path, max_frames)
    if _meta is not None:
        _meta.update(vinfo)
    raw = []      # (strict_face_or_None, relaxed_face_or_None, pix_std, h, w)
    for frame in frames:
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = frame.shape[:2]
        strict = FACE.largest_face(frame)
        relaxed = None
        if strict is None:
            relaxed = FACE.largest_face(frame, thr=FACE.RELAXED_THRESHOLD)
        raw.append((strict, relaxed, float(grey.std()), h, w))
    n = len(raw)
    has_strict = any(r[0] is not None for r in raw)
    accepted_weak = [False] * n
    if has_strict:
        # Forward sweep: anchored by a strict or already-accepted
        # neighbour on the left; backward sweep: anchored from the
        # right. A relaxed sighting with no anchor path to any strict
        # sighting stays rejected.
        prev_ok = False
        for i in range(n):
            if raw[i][0] is not None:
                prev_ok = True
            elif raw[i][1] is not None and prev_ok:
                accepted_weak[i] = True
            if raw[i][0] is None and raw[i][1] is None:
                prev_ok = False
        next_ok = False
        for i in range(n - 1, -1, -1):
            if raw[i][0] is not None:
                next_ok = True
            elif raw[i][1] is not None and next_ok:
                accepted_weak[i] = True
            if raw[i][0] is None and raw[i][1] is None:
                next_ok = False
    features = []
    for i, (strict, relaxed, pix_std, h, w) in enumerate(raw):
        face = strict
        is_strict = strict is not None
        if face is None and accepted_weak[i]:
            face = relaxed
            is_strict = False
        if face is None:
            features.append({"face": False, "strict": False, "cx": 0.0, "cy": 0.0,
                             "size": 0.0, "pix_std": pix_std})
        else:
            cx = (face[0] + face[2] / 2) / w; cy = (face[1] + face[3] / 2) / h
            features.append({"face": True, "strict": is_strict, "cx": float(cx),
                             "cy": float(cy), "size": float(face[2] / w),
                             "pix_std": pix_std})
    return features

def check_liveness(video_path, challenge):
    """Full liveness check on an uploaded challenge video."""
    if not video_path:
        return {"status": "not_run", "findings": {"reason": "liveness_video_missing"}, "reason_codes": ["liveness_not_run"]}
    if cv2 is None:
        return {"status": "error", "findings": {"error": "opencv_unavailable"}, "reason_codes": ["model_missing"]}
    if not FACE.models_present():
        return {"status": "error", "findings": {"error": "face_models_not_fetched_run_scripts/fetch_models.py"}, "reason_codes": ["model_missing"]}
    meta = {}
    try:
        features = extract_features(video_path, _meta=meta)
    except Exception as e:
        return {"status": "error", "findings": {"error": str(e)[:200]}, "reason_codes": ["liveness_video_unreadable"]}
    if not features:
        return {"status": "error", "findings": {"error": "no_frames_extracted"}, "reason_codes": ["liveness_video_unreadable"]}
    res = analyse_features(features, challenge)
    res["findings"] = {**res["findings"], "method": "active_challenge_yunet",
                       "video_total_frames": meta.get("total_frames"),
                       "video_rotation_degrees": meta.get("rotation_degrees"),
                       "weak_frames_accepted": sum(1 for f in features
                                                   if f.get("face") and not f.get("strict", True))}
    return res
