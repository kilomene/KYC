"""Continuous face tracking (owner's order, 2026-10-26: "real high
super intelligent continuous face tracking — the camera is analysed
across multi frames... instead of relying on the single selfie").

The liveness video frames (plus the selfie and its burst frames) are
reduced to a TRACK: per-frame YuNet detection + SFace embedding, then

  presence     the face must be found in >= 80% of sampled frames;
  trajectory   centre/size path statistics (recorded as findings);
  identity     CONTINUITY — judged on the track's STRUCTURE, not on
               its single worst frame (2026-10-28 rebuild, owner
               session 15). The old rule failed the track when ANY
               frame's cosine to the median (or any consecutive pair)
               fell below the floor — but the liveness challenge
               itself orders extreme head turns, and a genuine turn
               rotates the embedding through a deep, smooth, fully
               self-consistent dip that RETURNS to the anchor
               identity (measured on the owner's real take: median
               0.85, mean 0.72, one 8-frame excursion bottoming at
               0.25 mid-turn, final frames back at 0.89-0.90). A
               single minimum cannot tell that from a swap; the
               structure can. The track now FAILS only on:
                 * identity collapse — the MEDIAN frame no longer
                   matches the track's own median identity;
                 * majority foreign — >= half the frames sit below
                   the floor against the median identity;
                 * endpoint drift — the first and last segments'
                   median identities are foreign to each other (a
                   morph or a swap that never returned);
                 * a foreign SEGMENT — a cliff-bounded run of >= 4
                   frames whose median identity is foreign to the
                   anchor segment's and which STARTS foreign (a
                   graded entry is a rotating face; an abrupt entry
                   at full foreign identity is a takeover);
                 * a trailing foreign segment of >= 3 frames (the
                   track ends as someone else).
               Shorter foreign runs, a foreign share above a quarter,
               or a median under the pass line are UNCLEAR — never a
               pass, never a break. Documented residual: a live
               accomplice who smoothly takes over mid-challenge,
               performs the movements, and hands back can evade the
               track leg alone; the challenge-response liveness,
               document face match and deepfake legs are the controls
               for that performance, as before.

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
    pass_line = pass_threshold + margin
    # ---- Structural identity continuity (2026-10-28) ----
    # Segments: maximal runs of frames joined by consecutive cosines
    # at or above the cliff line (a hair under the floor — a genuine
    # turn's fastest step measured 0.32 against a 0.313 floor, while a
    # swap's boundary step is ~0.0).
    cliff = floor - 0.05
    segments = [[0]]
    for i, c in enumerate(consecutive):
        if c < cliff:
            segments.append([i + 1])
        else:
            segments[-1].append(i + 1)

    def _seg_median(idxs):
        sub = [embs[i] for i in idxs]
        if np is not None:
            return np.median(np.asarray(sub, dtype=np.float64), axis=0).tolist()
        return [sorted(float(e[k] for e in sub))[len(sub) // 2] for k in range(len(sub[0]))]

    anchor = max(segments, key=lambda s: (len(s), -s[0]))
    anchor_med = _seg_median(anchor)
    seg_info = []
    for s in segments:
        med = _seg_median(s)
        seg_info.append({
            "start": s[0], "length": len(s),
            "vs_anchor": FACE.cosine_similarity(med, anchor_med),
            "entry_vs_anchor": FACE.cosine_similarity(embs[s[0]], anchor_med),
        })
    foreign = [c < floor for c in cosines]
    longest_run, run = 0, 0
    for f in foreign:
        run = run + 1 if f else 0
        longest_run = max(longest_run, run)
    trailing_run = 0
    for f in reversed(foreign):
        if not f:
            break
        trailing_run += 1
    median_cos = sorted(cosines)[len(cosines) // 2]
    findings["identity_median_cosine"] = round(median_cos, 4)
    findings["foreign_frames"] = int(sum(foreign))
    findings["longest_foreign_run"] = int(longest_run)
    findings["segments"] = [{k: (round(v, 4) if isinstance(v, float) else v)
                              for k, v in si.items()} for si in seg_info]

    def _break():
        return ({"status": "fail", "findings": findings,
                 "reason_codes": ["face_track_identity_break"], "aggregate_embedding": agg}, agg)

    # FAIL legs — measured evidence of a different identity, never a
    # single frame's dip.
    if median_cos < floor:
        return _break()                       # collapse / morph end-state
    if sum(foreign) >= len(cosines) / 2:
        return _break()                       # majority foreign
    if len(segments) > 1 and len(segments[0]) >= 4 and len(segments[-1]) >= 4:
        drift = FACE.cosine_similarity(_seg_median(segments[0]), _seg_median(segments[-1]))
        findings["endpoint_drift_cosine"] = round(drift, 4)
        if drift < floor:
            return _break()                   # starts and ends as different people
    for si in seg_info:
        if si["start"] == anchor[0]:
            continue
        if si["vs_anchor"] < floor and si["length"] >= 4 and si["entry_vs_anchor"] < pass_line:
            return _break()                   # abrupt foreign takeover segment
        if si is seg_info[-1] and si["vs_anchor"] < floor and si["length"] >= 3:
            return _break()                   # ends as someone else, never returned
    if trailing_run >= 4 and median_cos < pass_line:
        return _break()
    if presence < MIN_PRESENCE:
        return ({"status": "unclear", "findings": findings,
                 "reason_codes": ["face_track_low_presence"], "aggregate_embedding": agg}, agg)
    # UNCLEAR legs — inconclusive structure: never a pass.
    if (longest_run >= 4 or sum(foreign) > len(cosines) / 4
            or median_cos < pass_line
            or any(si["vs_anchor"] < floor and si["length"] >= 2
                   for si in seg_info if si["start"] != anchor[0])):
        return ({"status": "unclear", "findings": findings,
                 "reason_codes": ["face_track_identity_unstable"], "aggregate_embedding": agg}, agg)
    return ({"status": "pass", "findings": findings, "reason_codes": [],
             "aggregate_embedding": agg}, agg)

def _frame_record(frame):
    # Detection + embedding in work_image space (WS2): for oversized
    # stills this keeps alignCrop landmarks native to the embedded
    # image; centre/size outputs are normalised, so they are
    # unaffected by the working scale. Video frames are already small.
    frame = FACE.work_image(frame)
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
    vinfo = {}
    if video_path:
        # Full-duration, orientation-corrected sampling (FACE.video_
        # frames) — the old first-N sampling judged a 9s clip on its
        # first second whenever the container's frame count lied, and
        # never corrected a sideways recording (owner session 14).
        try:
            vframes, vinfo = FACE.video_frames(video_path, max_frames)
        except Exception:
            return {"status": "error", "findings": {"error": "video_unreadable"}, "reason_codes": ["face_track_video_unreadable"]}
        for frame in vframes:
            try:
                records.append(_frame_record(frame))
            except Exception:
                records.append(None)
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
                       "video_total_frames": vinfo.get("total_frames"),
                       "video_rotation_degrees": vinfo.get("rotation_degrees"),
                       "sources": {"video": bool(video_path), "extra_images": len(extra_image_paths or [])}}
    return res
