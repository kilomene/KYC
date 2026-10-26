"""Continuous face tracking (owner's order, 2026-10-26: "real high
super intelligent continuous face tracking — the camera is analysed
across multi frames... instead of relying on the single selfie").

The liveness video frames (plus the selfie and its burst frames) are
reduced to a TRACK: per-frame YuNet detection + SFace embedding, then

  presence     the face must be found in >= 80% of sampled frames;
  trajectory   centre/size path statistics (recorded as findings);
  identity     CONTINUITY — every frame's embedding is compared with
               the track's median embedding, and consecutive frames
               with each other. A mid-stream face swap or an embedding
               jump (the classic injection / deepfake tell) breaks
               continuity: FAIL, face_track_identity_break.

FACE MATCH then compares the document portrait against the track's
AGGREGATE (median) embedding — never a single lucky frame.

Fail-closed: too few trackable frames, low presence, or an unstable
identity are unclear — never a pass. build_track is a pure function of
per-frame (box, centre, size, embedding) records, so the continuity
logic is unit-testable without models or video.
"""
try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

from . import face as FACE

MIN_SAMPLED = 5
MIN_WITH_FACE = 3
MIN_PRESENCE = 0.8

def build_track(frame_faces, pass_threshold=FACE.DEFAULT_THRESHOLD, margin=FACE.DEFAULT_MARGIN):
    """frame_faces: one entry per sampled frame — None, or a dict
    {"centre": (cx, cy), "size": float, "embedding": [...]} (normalised
    centre/size). Returns (check_result, aggregate_embedding_or_None).
    The result carries the aggregate under "aggregate_embedding" for
    the caller's face match; record() ignores extra keys."""
    n = len(frame_faces)
    with_face = [f for f in frame_faces if f]
    presence = (len(with_face) / n) if n else 0.0
    findings = {"frames_sampled": n, "frames_with_face": len(with_face),
                "presence_ratio": round(presence, 3)}
    if n < MIN_SAMPLED or len(with_face) < MIN_WITH_FACE:
        return ({"status": "unclear", "findings": findings,
                 "reason_codes": ["face_track_insufficient"]}, None)
    embs = [list(f["embedding"]) for f in with_face]
    # Aggregate identity: component-wise median embedding.
    if np is not None:
        agg = np.median(np.asarray(embs, dtype=np.float64), axis=0).tolist()
    else:
        agg = [sorted(float(e[i]) for e in embs)[len(embs) // 2] for i in range(len(embs[0]))]
    cosines = [FACE.cosine_similarity(e, agg) for e in embs]
    consecutive = [FACE.cosine_similarity(embs[i], embs[i + 1]) for i in range(len(embs) - 1)]
    findings["identity_min_cosine"] = round(min(cosines), 4)
    findings["identity_mean_cosine"] = round(sum(cosines) / len(cosines), 4)
    if consecutive:
        findings["identity_min_consecutive"] = round(min(consecutive), 4)
    centres = [f["centre"] for f in with_face]
    sizes = [float(f["size"]) for f in with_face]
    steps = [((centres[i + 1][0] - centres[i][0]) ** 2 + (centres[i + 1][1] - centres[i][1]) ** 2) ** 0.5
             for i in range(len(centres) - 1)]
    findings["trajectory"] = {
        "mean_step": round(sum(steps) / len(steps), 4) if steps else 0.0,
        "max_step": round(max(steps), 4) if steps else 0.0,
        "size_mean": round(sum(sizes) / len(sizes), 4),
        "size_std": round((sum((s - sum(sizes) / len(sizes)) ** 2 for s in sizes) / len(sizes)) ** 0.5, 4),
    }
    floor = pass_threshold - margin
    # Identity BREAK on EITHER metric: median collapse catches a slow
    # morph (consecutive stays high while identity drifts away);
    # consecutive collapse catches an abrupt swap (a balanced swap's
    # median is a blend both halves still resemble at ~0.7, so the
    # median leg alone would miss it — measured 2026-10-26).
    # Calibration on the owner's real captures: clean take passes
    # (min-cosine 0.91, min-consecutive 0.87); his hard head-turn take
    # collapses on BOTH metrics (0.13 / 0.10) — at <=24 sampled frames
    # an extreme pose change between samples is indistinguishable
    # from a discontinuity, and fail-closed wins: he re-scans.
    if min(cosines) < floor or (consecutive and min(consecutive) < floor):
        return ({"status": "fail", "findings": findings,
                 "reason_codes": ["face_track_identity_break"], "aggregate_embedding": agg}, agg)
    if presence < MIN_PRESENCE:
        return ({"status": "unclear", "findings": findings,
                 "reason_codes": ["face_track_low_presence"], "aggregate_embedding": agg}, agg)
    if min(cosines) < pass_threshold + margin:
        return ({"status": "unclear", "findings": findings,
                 "reason_codes": ["face_track_identity_unstable"], "aggregate_embedding": agg}, agg)
    return ({"status": "pass", "findings": findings, "reason_codes": [],
             "aggregate_embedding": agg}, agg)

def _frame_record(frame):
    face = FACE.largest_face(frame)
    if face is None:
        return None
    h, w = frame.shape[:2]
    emb = FACE.face_feature(frame, face)
    return {"centre": ((face[0] + face[2] / 2) / w, (face[1] + face[3] / 2) / h),
            "size": float(face[2] / w), "embedding": [float(v) for v in emb]}

def check_face_track(video_path=None, extra_image_paths=None,
                     pass_threshold=FACE.DEFAULT_THRESHOLD, margin=FACE.DEFAULT_MARGIN,
                     max_frames=24):
    """Build the track from a liveness video (+ still/burst images)."""
    if cv2 is None or np is None:
        return {"status": "error", "findings": {"error": "opencv_unavailable"}, "reason_codes": ["model_missing"]}
    if not FACE.models_present():
        return {"status": "error", "findings": {"error": "face_models_not_fetched"}, "reason_codes": ["model_missing"]}
    records = []
    if video_path:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {"status": "error", "findings": {"error": "video_unreadable"}, "reason_codes": ["face_track_video_unreadable"]}
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        step = max(1, total // max_frames) if total > 0 else 1
        i = 0
        while len(records) < max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if i % step == 0:
                try:
                    records.append(_frame_record(frame))
                except Exception:
                    records.append(None)
            i += 1
        cap.release()
    for p in (extra_image_paths or []):
        if not p:
            continue
        try:
            img = cv2.imread(p)
            records.append(_frame_record(img) if img is not None else None)
        except Exception:
            records.append(None)
    if not records:
        return {"status": "not_run", "findings": {"reason": "no_video_or_images"}, "reason_codes": ["face_track_not_run"]}
    res, _agg = build_track(records, pass_threshold, margin)
    res["findings"] = {**res["findings"], "method": "yunet+sface_continuous_track",
                       "sources": {"video": bool(video_path), "extra_images": len(extra_image_paths or [])}}
    return res
