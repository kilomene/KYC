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
    """Pure analysis of sampled frame features against the challenge."""
    movements = list((challenge or {}).get("movements") or [])
    n = len(features)
    findings = {"frames_sampled": n, "challenge": movements}
    if n < 4:
        return {"status": "unclear", "findings": {**findings, "error": "too_few_frames"}, "reason_codes": ["liveness_too_few_frames"]}
    faces = [f for f in features if f.get("face")]
    ratio = len(faces) / n
    findings["face_ratio"] = round(ratio, 3)
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

def extract_features(video_path, max_frames=30):
    """Sample frames from a video with OpenCV and reduce each to features
    via YuNet. Requires cv2 + models; raises on unreadable video."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("video_unreadable")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    idxs = set()
    if total > 0:
        step = max(1, total // max_frames)
        idxs = set(range(0, total, step))
    features = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if total > 0 and i not in idxs:
            i += 1
            if i > total:
                break
            continue
        i += 1
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face = FACE.largest_face(frame)
        if face is None:
            features.append({"face": False, "cx": 0.0, "cy": 0.0, "size": 0.0, "pix_std": float(grey.std())})
        else:
            h, w = frame.shape[:2]
            cx = (face[0] + face[2] / 2) / w; cy = (face[1] + face[3] / 2) / h
            features.append({"face": True, "cx": float(cx), "cy": float(cy), "size": float(face[2] / w), "pix_std": float(grey.std())})
        if len(features) >= max_frames:
            break
    cap.release()
    return features

def check_liveness(video_path, challenge):
    """Full liveness check on an uploaded challenge video."""
    if not video_path:
        return {"status": "not_run", "findings": {"reason": "liveness_video_missing"}, "reason_codes": ["liveness_not_run"]}
    if cv2 is None:
        return {"status": "error", "findings": {"error": "opencv_unavailable"}, "reason_codes": ["model_missing"]}
    if not FACE.models_present():
        return {"status": "error", "findings": {"error": "face_models_not_fetched_run_scripts/fetch_models.py"}, "reason_codes": ["model_missing"]}
    try:
        features = extract_features(video_path)
    except Exception as e:
        return {"status": "error", "findings": {"error": str(e)[:200]}, "reason_codes": ["liveness_video_unreadable"]}
    if not features:
        return {"status": "error", "findings": {"error": "no_frames_extracted"}, "reason_codes": ["liveness_video_unreadable"]}
    res = analyse_features(features, challenge)
    res["findings"] = {**res["findings"], "method": "active_challenge_yunet"}
    return res
