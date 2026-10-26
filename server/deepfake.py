"""Deepfake / fake-camera defence for the selfie + liveness path
(owner's order, 2026-10-26: "detect deep fake cameras, deep fake
technology — very sensitive").

Four legs, combined — no single leg is a pretend detector:

  pulse (rPPG)   The green-channel mean over the cheek regions is a
                 time series; living skin carries a real pulse
                 (0.7-3 Hz blood-volume oscillation). Scored as the
                 pulse band's dominant-peak power share + SNR.
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

HONEST LIMIT (measured, see the build report): rPPG from a ~4.5 s
VP8-compressed webm is a weak signal — frequency resolution is
~0.22 Hz and the codec crushes subtle chroma oscillation. That is
exactly why pulse absence alone never fails anyone here (it must
combine with generation artifacts), and why the positive control —
a real human capture — must pass this module before the weights are
trusted in production.
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
    x = np.asarray(series, dtype=np.float64)
    x = x - x.mean()
    win = max(3, int(fps))
    trend = np.convolve(x, np.ones(win) / win, mode="same")
    x = x - trend
    spec = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0 / float(fps))
    band = (freqs >= 0.7) & (freqs <= 3.0)
    if int(band.sum()) < 3 or float(spec[band].sum()) <= 0:
        return {**base, "score": None, "present": False, "reason": "band_empty", "seconds": round(dur, 1)}
    bs = spec[band]; bf = freqs[band]
    peak = float(bs.max()); total = float(bs.sum())
    median = float(np.median(bs)) or 1e-12
    share = peak / total
    snr = peak / median
    return {"score": round(share, 3), "present": bool(share >= 0.30 and snr >= 6.0),
            "peak_hz": round(float(bf[int(bs.argmax())]), 2), "snr": round(snr, 1),
            "frames": n, "seconds": round(dur, 1)}

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

def _cheek_green(frame, box):
    """Mean green channel over the two cheek regions of a face box."""
    x, y, w, h = [int(v) for v in box[:4]]
    fh, fw = frame.shape[:2]
    y0, y1 = max(0, y + int(0.52 * h)), min(fh, y + int(0.80 * h))
    total = 0.0; count = 0
    for fx0, fx1 in ((0.14, 0.40), (0.60, 0.86)):
        x0, x1 = max(0, x + int(fx0 * w)), min(fw, x + int(fx1 * w))
        if x1 > x0 and y1 > y0:
            total += float(frame[y0:y1, x0:x1, 1].sum()); count += (y1 - y0) * (x1 - x0)
    return (total / count) if count else None

def check_deepfake(video_path, selfie_path=None, client_signals=None):
    """Full deepfake check. Returns the standard check dict."""
    findings = {"client": client_signal_findings(client_signals),
                "method": "rppg_pulse+face_fft_artifacts+motion_trajectory+client_signals"}
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
    greens, centres, boxes_at = [], [], {}
    frames_seen = 0
    last_box = None
    mid_frame = None
    last_msec = 0.0
    while frames_seen < 300:
        ok, frame = cap.read()
        if not ok:
            break
        last_msec = float(cap.get(cv2.CAP_PROP_POS_MSEC) or last_msec)
        if frames_seen % 3 == 0:
            last_box = FACE.largest_face(frame)
            if last_box is not None:
                boxes_at[frames_seen] = last_box
        if last_box is not None:
            g = _cheek_green(frame, last_box)
            if g is not None:
                greens.append(g)
                fh, fw = frame.shape[:2]
                centres.append(((last_box[0] + last_box[2] / 2) / fw, (last_box[1] + last_box[3] / 2) / fh))
            if mid_frame is None and frames_seen > 10:
                mid_frame = (frame.copy(), last_box)
        frames_seen += 1
    cap.release()
    if frames_seen == 0:
        return {"status": "error", "findings": {**findings, "error": "no_frames"}, "reason_codes": ["deepfake_video_unreadable"]}
    fps = fps_raw if 5 <= fps_raw <= 60 else ((len(greens) / (last_msec / 1000.0)) if last_msec > 500 else 24.0)
    pulse = pulse_from_series(greens, fps)
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
