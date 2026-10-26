"""Deepfake / fake-camera defence for the selfie + liveness path
(owner's order, 2026-10-26: "detect deep fake cameras, deep fake
technology — very sensitive").

Four legs, combined — no single leg is a pretend detector:

  pulse (rPPG)   The cheek-region mean RGB is a time series; living
                 skin carries a real pulse (0.7-3 Hz blood-volume
                 oscillation). Three legs score it (Phase 4 WS2
                 hardening): POS (plane-orthogonal-to-skin, Wang et
                 al. 2017) as the primary, CHROM (de Haan & Jeanne
                 2013) as corroboration, and the original green-
                 channel FFT as fallback — all under a signal-quality
                 gate (face presence, ROI centre jitter, size
                 stability), so a 'pulse measured' verdict means the
                 skin region was stable enough to measure at all.
                 Scored as the pulse band's dominant-peak share + SNR.
  artifacts      FFT analysis of face crops: GAN/diffusion upsampling
                 leaves periodic high-frequency traces. Peak-share
                 score, the same family as the authenticity moire
                 measure but restricted to the face.
  motion         Face-centre trajectory statistics across the
                 challenge: path, jitter, and loop detection
                 (autocorrelation — a looped feed repeats).
  client         Browser-supplied capture signals: the camera track
                 label (a known virtual camera — OBS, ManyCam, Snap
                 Camera, ... — is a HARD finding) and device-motion
                 telemetry (a real handheld phone has micro-motion; a
                 desktop injection rig has no sensor at all).

Decision shape: a virtual-camera label hit FAILS outright
(virtual_camera_detected). No-pulse PLUS high artifacts FAILS
(deepfake_suspected). Partial evidence is an unclear with named
findings + risk points. A pass REQUIRES a present pulse and low
artifacts. Unanalysable media is unclear/error — NEVER a pass.

HONEST LIMIT (measured, WS2 — benchmarks/BIOMETRICS.md §5): rPPG
from a ~4.5 s VP8-compressed webm is a weak signal — frequency
resolution is ~0.22 Hz and the codec crushes subtle chroma
oscillation. The WS2 POS/CHROM legs measure a plausible peak on the
owner's clean take (1.34 Hz, SNR 3.2) but BELOW the evidentiary bar
(share >= 0.30, SNR >= 6), and the attack suite measured the pulse
leg firing on jittered presentations of real photos. That is
exactly why pulse absence alone never fails anyone here (it must
combine with generation artifacts), why pulse presence alone never
passes anyone, and why the leg stays evidence-only. The flow now
records ~9 s liveness clips; until a real longer capture is
measured, no stronger claim is made for this leg.
"""
try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

from . import face as FACE

VIRTUAL_CAMERA_WORDS = ("obs", "manycam", "snap camera", "snapcamera",
                        "virtual", "camo", "xplit", "streamlabs", "mmhmm",
                        "chromacam", "epoccam", "ivcam", "droidcam",
                        "screen", "fake webcam", "akvcam")

ARTIFACT_HIGH = 0.30

def client_signal_findings(client_signals):
    """Pure evaluation of browser-supplied capture signals."""
    out = {"track_label": None, "virtual_camera_hit": None, "motion": None,
           "motion_absent": False, "motion_frozen": False}
    if not isinstance(client_signals, dict):
        return out
    label = str(client_signals.get("track_label") or "")[:160]
    out["track_label"] = label or None
    low = label.lower()
    for w in VIRTUAL_CAMERA_WORDS:
        if w in low:
            out["virtual_camera_hit"] = w
            break
    motion = client_signals.get("motion")
    if isinstance(motion, dict):
        out["motion"] = {k: motion.get(k) for k in ("sensor_present", "samples", "variance")}
        samples = motion.get("samples") or 0
        var = motion.get("variance")
        if motion.get("sensor_present") is False or samples == 0:
            out["motion_absent"] = True
        elif var is not None and samples >= 10 and float(var) < 1e-6:
            out["motion_frozen"] = True
    return out

def _band_score(x, fps):
    """Shared pulse-band scoring of a 1-D signal: detrend, FFT, then
    the 0.7-3.0 Hz band's dominant-peak share + SNR. Present = share
    >= 0.30 of band power AND peak >= 6x the band median."""
    n = len(x)
    x = np.asarray(x, dtype=np.float64)
    x = x - x.mean()
    win = max(3, int(fps))
    trend = np.convolve(x, np.ones(win) / win, mode="same")
    x = x - trend
    spec = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0 / float(fps))
    band = (freqs >= 0.7) & (freqs <= 3.0)
    if int(band.sum()) < 3 or float(spec[band].sum()) <= 0:
        return None
    bs = spec[band]; bf = freqs[band]
    peak = float(bs.max()); total = float(bs.sum())
    median = float(np.median(bs)) or 1e-12
    share = peak / total
    snr = peak / median
    return {"score": round(share, 3), "present": bool(share >= 0.30 and snr >= 6.0),
            "peak_hz": round(float(bf[int(bs.argmax())]), 2), "snr": round(snr, 1)}

def pulse_from_series(series, fps):
    """Pure rPPG scoring of a per-frame green-channel skin series.
    Present = a dominant in-band peak (share >= 0.30 of band power and
    >= 6x the band median). Short clips are honestly unanalysable."""
    n = len(series)
    base = {"frames": n, "fps": round(float(fps), 1) if fps else None}
    if np is None:
        return {**base, "score": None, "present": False, "reason": "numpy_unavailable"}
    if n < 20 or not fps or fps <= 0:
        return {**base, "score": None, "present": False, "reason": "series_too_short"}
    dur = n / float(fps)
    if dur < 2.5:
        return {**base, "score": None, "present": False, "reason": "clip_too_short", "seconds": round(dur, 1)}
    scored = _band_score(series, fps)
    if scored is None:
        return {**base, "score": None, "present": False, "reason": "band_empty", "seconds": round(dur, 1)}
    return {**scored, "frames": n, "seconds": round(dur, 1)}

def _pos_signal(rgb, fps):
    """POS (Wang et al. 2017): plane-orthogonal-to-skin projection.
    rgb is an (n, 3) array of per-frame skin-region mean RGB. Sliding
    windows of ~1.6 s are temporally normalised, projected onto the
    plane orthogonal to the skin-tone direction, alpha-tuned and
    overlap-added — the standard published algorithm, which cancels
    specular/motion chroma changes the raw green channel cannot."""
    n = len(rgb)
    win = max(8, int(round(fps * 1.6)))
    if n < win:
        win = n
    out = np.zeros(n, dtype=np.float64)
    counts = np.zeros(n, dtype=np.float64)
    step = max(1, win // 2)
    for start in range(0, n - win + 1, step):
        seg = rgb[start:start + win].astype(np.float64)
        mean = seg.mean(axis=0)
        if np.any(mean <= 0):
            continue
        norm = seg / mean  # temporal normalisation per channel
        s1 = norm[:, 1] - norm[:, 2]            # G - B
        s2 = norm[:, 1] + norm[:, 2] - 2.0 * norm[:, 0]  # G + B - 2R
        alpha = (float(np.std(s1)) / float(np.std(s2))) if float(np.std(s2)) > 1e-12 else 0.0
        h = s1 + alpha * s2
        h = h - h.mean()
        out[start:start + win] += h
        counts[start:start + win] += 1.0
    counts[counts == 0] = 1.0
    return out / counts

def _chrom_signal(rgb, fps):
    """CHROM (de Haan & Jeanne 2013): chrominance projection
    X = 3R - 2G, Y = 1.5R + G - 1.5B on temporally normalised RGB,
    alpha = std(X)/std(Y), pulse = X - alpha*Y."""
    mean = rgb.mean(axis=0)
    if np.any(mean <= 0):
        return np.zeros(len(rgb))
    norm = rgb / mean
    x = 3.0 * norm[:, 0] - 2.0 * norm[:, 1]
    y = 1.5 * norm[:, 0] + norm[:, 1] - 1.5 * norm[:, 2]
    alpha = (float(np.std(x)) / float(np.std(y))) if float(np.std(y)) > 1e-12 else 0.0
    s = x - alpha * y
    return s - s.mean()

def pulse_from_rgb_series(rgb_series, fps, method="pos"):
    """Pure rPPG scoring of a per-frame skin RGB series via POS
    (default) or CHROM. Same band scoring + honesty contract as the
    green leg: too short / band-empty is unanalysable (score None),
    never a fabricated absence or presence."""
    n = len(rgb_series)
    base = {"frames": n, "fps": round(float(fps), 1) if fps else None, "method": method}
    if np is None:
        return {**base, "score": None, "present": False, "reason": "numpy_unavailable"}
    if n < 20 or not fps or fps <= 0:
        return {**base, "score": None, "present": False, "reason": "series_too_short"}
    dur = n / float(fps)
    if dur < 2.5:
        return {**base, "score": None, "present": False, "reason": "clip_too_short", "seconds": round(dur, 1)}
    rgb = np.asarray(rgb_series, dtype=np.float64)
    if rgb.ndim != 2 or rgb.shape[1] != 3:
        return {**base, "score": None, "present": False, "reason": "series_malformed", "seconds": round(dur, 1)}
    sig = _pos_signal(rgb, float(fps)) if method == "pos" else _chrom_signal(rgb, float(fps))
    if float(np.std(sig)) <= 1e-12:
        return {**base, "score": None, "present": False, "reason": "signal_flat", "seconds": round(dur, 1)}
    scored = _band_score(sig, fps)
    if scored is None:
        return {**base, "score": None, "present": False, "reason": "band_empty", "seconds": round(dur, 1)}
    return {**scored, "frames": n, "seconds": round(dur, 1)}

def signal_quality(centres, sizes, face_ratio):
    """Quality gate for the pulse leg (WS2 hardening). A 'pulse
    measured' result must come from a stable skin region: the face
    present in most frames, centre jitter small (smooth tracking —
    detection flicker and ROI hopping produce frame-to-frame jumps),
    and face size not swinging wildly. Returns the metrics + the
    verdict; the metrics are recorded either way."""
    q = {"face_ratio": round(float(face_ratio), 3) if face_ratio is not None else None,
         "centre_jitter": None, "size_cv": None, "quality_ok": False}
    if len(centres) >= 8:
        steps = [abs(float(centres[i + 1][0]) - float(centres[i][0])) + abs(float(centres[i + 1][1]) - float(centres[i][1]))
                 for i in range(len(centres) - 1)]
        q["centre_jitter"] = round(float(sum(steps) / len(steps)), 4)
    if len(sizes) >= 8:
        m = float(sum(float(s) for s in sizes) / len(sizes))
        if m > 0:
            var = sum((float(s) - m) ** 2 for s in sizes) / len(sizes)
            q["size_cv"] = round(float((var ** 0.5) / m), 3)
    q["quality_ok"] = bool(
        (q["face_ratio"] or 0.0) >= 0.6
        and q["centre_jitter"] is not None and q["centre_jitter"] <= 0.06
        and (q["size_cv"] is None or q["size_cv"] <= 0.35))
    return q

def combine_pulse(green, pos, chrom, quality):
    """Combine the three rPPG legs under the quality gate.

    A pulse counts as PRESENT only when POS (the strongest leg —
    chrominance projection, resistant to the specular/motion artefacts
    that fool the raw green channel) measures one AND the signal
    quality gate passes. If POS is unanalysable (score None) the green
    leg may carry the result, labelled as a fallback. CHROM is
    recorded as corroboration either way. Every leg's own verdict is
    preserved in the returned dict — the gate never rewrites a leg."""
    methods_present = [m for m, r in (("pos", pos), ("chrom", chrom), ("green", green))
                       if r and r.get("present")]
    out = {"green": green, "pos": pos, "chrom": chrom,
           "methods_present": methods_present,
           "signal_quality": quality,
           "score": None, "present": False}
    if not quality.get("quality_ok"):
        primary = pos if (pos and pos.get("score") is not None) else green
        out["score"] = primary.get("score") if primary else None
        out["reason"] = "signal_quality_gate"
        if primary and primary.get("peak_hz") is not None:
            out["peak_hz"] = primary["peak_hz"]
        return out
    if pos and pos.get("present"):
        out.update({"present": True, "score": pos.get("score"),
                    "peak_hz": pos.get("peak_hz"), "method_used": "pos"})
        return out
    if pos and pos.get("score") is None and green and green.get("present"):
        out.update({"present": True, "score": green.get("score"),
                    "peak_hz": green.get("peak_hz"), "method_used": "green_fallback"})
        return out
    primary = pos if (pos and pos.get("score") is not None) else green
    out["score"] = primary.get("score") if primary else None
    if primary and primary.get("peak_hz") is not None:
        out["peak_hz"] = primary["peak_hz"]
    out["method_used"] = "pos" if primary is pos else "green"
    return out

def _artifact_score(bgr_img, face_box):
    """Periodic-peak share of the face crop's high-frequency FFT band."""
    if bgr_img is None or face_box is None:
        return None
    x, y, w, h = [int(v) for v in face_box[:4]]
    crop = bgr_img[max(0, y):y + h, max(0, x):x + w]
    if crop.size == 0:
        return None
    grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    grey = cv2.resize(grey, (128, 128)).astype(np.float64)
    grey -= grey.mean()
    F = np.abs(np.fft.rfft2(grey))
    hh, ww = F.shape
    fy = np.minimum(np.arange(hh), hh - np.arange(hh))
    radius = np.sqrt(fy[:, None] ** 2 + np.arange(ww)[None, :] ** 2)
    band = F[radius > 0.35 * radius.max()]
    if band.size == 0:
        return None
    return round(float(band.max()) / (float(np.sqrt((band ** 2).sum())) or 1e-9), 3)

def _cheek_rgb(frame, box):
    """Mean (R, G, B) over the two cheek regions of a face box — the
    skin ROI series the POS/CHROM rPPG legs project."""
    x, y, w, h = [int(v) for v in box[:4]]
    fh, fw = frame.shape[:2]
    y0, y1 = max(0, y + int(0.52 * h)), min(fh, y + int(0.80 * h))
    totals = np.zeros(3, dtype=np.float64); count = 0
    for fx0, fx1 in ((0.14, 0.40), (0.60, 0.86)):
        x0, x1 = max(0, x + int(fx0 * w)), min(fw, x + int(fx1 * w))
        if x1 > x0 and y1 > y0:
            region = frame[y0:y1, x0:x1]  # BGR
            totals += np.array([region[:, :, 2].sum(), region[:, :, 1].sum(), region[:, :, 0].sum()])
            count += (y1 - y0) * (x1 - x0)
    if not count:
        return None
    return tuple(float(v) for v in (totals / count))  # (R, G, B)

def _cheek_green(frame, box):
    """Mean green channel over the two cheek regions of a face box."""
    rgb = _cheek_rgb(frame, box)
    return rgb[1] if rgb else None

def check_deepfake(video_path, selfie_path=None, client_signals=None):
    """Full deepfake check. Returns the standard check dict."""
    findings = {"client": client_signal_findings(client_signals),
                "method": "rppg_pos+chrom+green+face_fft_artifacts+motion_trajectory+client_signals"}
    if findings["client"]["virtual_camera_hit"]:
        return {"status": "fail", "findings": findings, "reason_codes": ["virtual_camera_detected"]}
    if not video_path:
        return {"status": "not_run", "findings": {**findings, "reason": "liveness_video_missing"},
                "reason_codes": ["deepfake_not_run"]}
    if cv2 is None or np is None:
        return {"status": "error", "findings": {**findings, "error": "opencv_unavailable"}, "reason_codes": ["model_missing"]}
    if not FACE.models_present():
        return {"status": "error", "findings": {**findings, "error": "face_models_not_fetched"}, "reason_codes": ["model_missing"]}
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"status": "error", "findings": {**findings, "error": "video_unreadable"}, "reason_codes": ["deepfake_video_unreadable"]}
    fps_raw = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    greens, rgbs, centres, sizes, boxes_at = [], [], [], [], {}
    frames_seen = 0
    last_box = None
    mid_frame = None
    last_msec = 0.0
    while frames_seen < 640:  # ~10 s at 60 fps, ~21 s at 30 fps (WS2 longer window)
        ok, frame = cap.read()
        if not ok:
            break
        last_msec = float(cap.get(cv2.CAP_PROP_POS_MSEC) or last_msec)
        if frames_seen % 3 == 0:
            last_box = FACE.largest_face(frame)
            if last_box is not None:
                boxes_at[frames_seen] = last_box
        if last_box is not None:
            rgb = _cheek_rgb(frame, last_box)
            if rgb is not None:
                rgbs.append(rgb)
                greens.append(rgb[1])
                fh, fw = frame.shape[:2]
                centres.append(((last_box[0] + last_box[2] / 2) / fw, (last_box[1] + last_box[3] / 2) / fh))
                sizes.append(float(last_box[2] / fw))
            if mid_frame is None and frames_seen > 10:
                mid_frame = (frame.copy(), last_box)
        frames_seen += 1
    cap.release()
    if frames_seen == 0:
        return {"status": "error", "findings": {**findings, "error": "no_frames"}, "reason_codes": ["deepfake_video_unreadable"]}
    fps = fps_raw if 5 <= fps_raw <= 60 else ((len(greens) / (last_msec / 1000.0)) if last_msec > 500 else 24.0)
    face_ratio_pre = (len(greens) / frames_seen) if frames_seen else 0.0
    quality = signal_quality(centres, sizes, face_ratio_pre)
    pulse = combine_pulse(pulse_from_series(greens, fps),
                          pulse_from_rgb_series(rgbs, fps, "pos"),
                          pulse_from_rgb_series(rgbs, fps, "chrom"),
                          quality)
    findings["pulse"] = pulse
    findings["frames_seen"] = frames_seen
    findings["face_frames"] = len(greens)
    # Generation artifacts: video mid-frame face + selfie face.
    art_scores = []
    if mid_frame is not None:
        s = _artifact_score(mid_frame[0], mid_frame[1])
        if s is not None:
            art_scores.append(s)
    if selfie_path:
        try:
            simg = cv2.imread(selfie_path)
            sbox = FACE.largest_face(simg) if simg is not None else None
            s = _artifact_score(simg, sbox)
            if s is not None:
                art_scores.append(s)
        except Exception:
            pass
    artifact = max(art_scores) if art_scores else None
    findings["artifact_score"] = artifact
    findings["artifact_high"] = bool(artifact is not None and artifact >= ARTIFACT_HIGH)
    # Motion naturalness from the centre trajectory.
    motion = {"points": len(centres)}
    if len(centres) >= 8:
        cx = np.array([c[0] for c in centres]); cy = np.array([c[1] for c in centres])
        step = np.sqrt(np.diff(cx) ** 2 + np.diff(cy) ** 2)
        accel = np.abs(np.diff(step)) if len(step) > 1 else np.array([0.0])
        motion["path"] = round(float(step.sum()), 3)
        motion["mean_step"] = round(float(step.mean()), 4)
        motion["jitter"] = round(float(accel.mean()), 4)
        if len(cx) >= 24:
            xc = cx - cx.mean()
            denom = float((xc ** 2).sum()) or 1e-12
            ac = [float((xc[:-k] * xc[k:]).sum()) / denom for k in range(6, len(cx) // 2)]
            motion["loop_autocorr_max"] = round(max(ac), 3) if ac else None
            motion["loop_suspect"] = bool(ac and max(ac) > 0.95)
    findings["motion"] = motion
    face_ratio = (len(greens) / frames_seen) if frames_seen else 0.0
    findings["face_ratio"] = round(face_ratio, 3)
    # ---- combine (see module docstring for the doctrine) ----
    if pulse.get("present") and not findings["artifact_high"]:
        return {"status": "pass", "findings": findings, "reason_codes": []}
    if pulse.get("score") is not None and not pulse.get("present") and findings["artifact_high"]:
        return {"status": "fail", "findings": findings, "reason_codes": ["deepfake_suspected"]}
    if face_ratio < 0.5:
        return {"status": "unclear", "findings": findings, "reason_codes": ["deepfake_unanalysable"]}
    return {"status": "unclear", "findings": findings, "reason_codes": ["deepfake_signals_present"]}
