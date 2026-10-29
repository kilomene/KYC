"""Face match (Phase 2): YuNet detection + SFace embeddings (OpenCV Zoo).

Models live in <repo>/models/ (gitignored, fetched by
scripts/fetch_models.py). If a model is absent, or OpenCV is unavailable,
the check returns status 'error' with reason 'model_missing' — NEVER a
fake pass (the Phase 1 fail-closed pattern).

Decision logic is a pure function of the cosine similarity so it is fully
unit-testable without the models:
  sim >= threshold + margin  -> pass
  sim >= threshold - margin  -> unclear (near threshold: a human looks)
  sim <  threshold - margin  -> fail (face_mismatch)
OpenCV's published SFace cosine threshold is 0.363; it is the default
`pass_threshold`, and both values are tenant-configurable (flow config).
YuNet landmarks from a detection row: [x, y, w, h, re_x, re_y, le_x, le_y,
nose_x, nose_y, rm_x, rm_y, lm_x, lm_y, score] — indices 4..13 are the
5 landmarks FaceRecognizerSF.alignCrop expects in the row's tail.
"""
import math, os

try:
    import cv2
    import numpy as np
except Exception:  # OpenCV missing -> face checks error, never pass
    cv2 = None
    np = None

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"
DEFAULT_THRESHOLD = 0.363  # OpenCV's published SFace cosine threshold
DEFAULT_MARGIN = 0.05

_cache = {}

def models_present():
    return all(os.path.isfile(os.path.join(MODELS_DIR, f)) and os.path.getsize(os.path.join(MODELS_DIR, f)) > 100_000
               for f in (YUNET_FILE, SFACE_FILE))

PRODUCTION_THRESHOLD = 0.6   # YuNet score the platform judges by
RELAXED_THRESHOLD = 0.35     # video-presence rescue only (see video_frames/liveness)

def _detector(width, height, thr=PRODUCTION_THRESHOLD):
    key = ("yunet", width, height, thr)
    if key not in _cache:
        _cache[key] = cv2.FaceDetectorYN_create(os.path.join(MODELS_DIR, YUNET_FILE), "", (width, height), thr, 0.3, 5000)
    return _cache[key]

def _recognizer():
    if "sface" not in _cache:
        _cache["sface"] = cv2.FaceRecognizerSF_create(os.path.join(MODELS_DIR, SFACE_FILE), "")
    return _cache["sface"]

def cosine_similarity(a, b):
    """Pure cosine similarity of two embedding vectors (lists or arrays)."""
    if np is not None:
        a = np.asarray(a, dtype=np.float64).ravel(); b = np.asarray(b, dtype=np.float64).ravel()
        na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
        if na == 0 or nb == 0: return 0.0
        return float(np.dot(a, b) / (na * nb))
    na = math.sqrt(sum(float(x) ** 2 for x in a)); nb = math.sqrt(sum(float(x) ** 2 for x in b))
    if na == 0 or nb == 0: return 0.0
    return sum(float(x) * float(y) for x, y in zip(a, b)) / (na * nb)

def similarity_decision(sim, pass_threshold=DEFAULT_THRESHOLD, margin=DEFAULT_MARGIN):
    """Pure decision on a similarity score -> (status, reason_codes)."""
    if sim is None:
        return "error", ["face_compare_error"]
    if sim >= pass_threshold + margin:
        return "pass", []
    if sim >= pass_threshold - margin:
        return "unclear", ["face_match_near_threshold"]
    return "fail", ["face_mismatch"]

MAX_DETECT_DIM = 1024  # see below: YuNet degrades measurably above this

def detect_faces(img, thr=PRODUCTION_THRESHOLD):
    """YuNet detection on a BGR image array. Returns list of face rows
    (largest first) or [] when no face is found. `thr` defaults to the
    production score threshold; a lower value exists ONLY for the
    video-presence rescue in liveness (never for identity).

    WS2 measurement (benchmarks/BIOMETRICS.md): on multi-megapixel
    stills YuNet's boxes shrink and drift as the input grows, and
    past ~1280px on the longest side the SFace alignment breaks —
    measured on the owner's real 2316x3088 selfie against his own
    liveness frame: cosine 0.435 at 512px, 0.390 at 1024, 0.205 at
    1280, -0.052 at 1600, and no face at all at full size in the
    pre-WS2 code. Detection therefore runs on a copy downscaled to
    MAX_DETECT_DIM and the returned boxes/landmarks are rescaled to
    the original coordinate frame for box consumers (portrait-region
    and ROI logic). Embedding consumers use work_image() space
    directly (extract_face_feature, facetrack) so their landmarks
    are native. Images at or below the cap take the exact original
    path — LFW (250px), video frames and flow captures are
    unaffected."""
    h, w = img.shape[:2]
    scale = 1.0
    work = img
    if max(h, w) > MAX_DETECT_DIM:
        scale = MAX_DETECT_DIM / float(max(h, w))
        work = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                          interpolation=cv2.INTER_AREA)
    wh, ww = work.shape[:2]
    det = _detector(ww, wh, thr)
    _, faces = det.detect(work)
    if faces is None or len(faces) == 0:
        return []
    out = []
    for f in faces:
        f = [float(v) for v in f]
        if scale != 1.0:
            inv = 1.0 / scale
            for i in (0, 2, 4, 6, 8, 10, 12):  # x, w, landmark xs
                f[i] *= inv
            for i in (1, 3, 5, 7, 9, 11, 13):  # y, h, landmark ys
                f[i] *= inv
        out.append(np.array(f, dtype=np.float32) if np is not None else f)
    return sorted(out, key=lambda f: f[2] * f[3], reverse=True)

def largest_face(img, thr=PRODUCTION_THRESHOLD):
    faces = detect_faces(img, thr=thr)
    return faces[0] if faces else None

_ROTATIONS = ((0, None), (90, cv2.ROTATE_90_CLOCKWISE),
              (180, cv2.ROTATE_180), (270, cv2.ROTATE_90_COUNTERCLOCKWISE))

def _vote_rotation(frames):
    """Pick the ONE rotation that makes the sampled frames upright:
    most strict detections wins, then highest total detector score.
    Phone recordings have a single fixed orientation, so one vote
    covers the whole clip. Returns the degrees (0/90/180/270)."""
    best_deg, best_key = 0, None
    for deg, code in _ROTATIONS:
        hits, score = 0, 0.0
        for fr in frames[:6]:
            img = fr if code is None else cv2.rotate(fr, code)
            f = largest_face(img)
            if f is not None:
                hits += 1
                score += float(f[14])
        key = (hits, round(score, 3))
        if best_key is None or key > best_key:
            best_deg, best_key = deg, key
    return best_deg

import threading as _threading

_VIDEO_FRAMES_CACHE = {}
_VIDEO_FRAMES_LOCK = _threading.Lock()


def video_frames(video_path, max_frames=30):
    """Sample frames evenly across a video's FULL duration, upright.

    Memoised per file (path + size + mtime + max_frames): a submit
    runs liveness, face track and deepfake over the SAME clip, and
    each used to pay the full decode + rotation vote again (owner
    session 17, 2026-10-29: ~2 minutes of decision time on a 2-core
    box, much of it re-decoding one 9-second video). The cache holds
    at most 2 clips; callers must not mutate the returned frames.
    """
    try:
        st = os.stat(video_path)
        key = (os.path.abspath(video_path), st.st_size, st.st_mtime_ns, max_frames)
    except OSError:
        key = None
    if key is not None:
        with _VIDEO_FRAMES_LOCK:
            hit = _VIDEO_FRAMES_CACHE.get(key)
        if hit is not None:
            return hit
    result = _video_frames_uncached(video_path, max_frames)
    if key is not None:
        with _VIDEO_FRAMES_LOCK:
            _VIDEO_FRAMES_CACHE[key] = result
            while len(_VIDEO_FRAMES_CACHE) > 2:
                _VIDEO_FRAMES_CACHE.pop(next(iter(_VIDEO_FRAMES_CACHE)))
    return result


def _video_frames_uncached(video_path, max_frames=30):
    """Sample frames evenly across a video's FULL duration, upright.

    Returns (frames, info) with info {total_frames, rotation_degrees}.

    Two field failures drive this (owner session 14, 2026-10-28):
      * MediaRecorder WebM carries a garbage CAP_PROP_FRAME_COUNT (a
        huge negative number), and first-N-sequential sampling judged
        a 9-second performance on its first second. When the reported
        count is implausible the real count is measured with a grab()
        pass, and the samples are spread across the whole clip.
      * The same recording stored its opening sideways (the sensor
        frame is landscape while the phone is held portrait), and no
        stage corrected orientation. One rotation is voted from the
        sampled frames and applied to all of them, so movement and
        identity analysis work in the upright frame the user saw.
    Raises ValueError("video_unreadable") when the file won't open.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("video_unreadable")
    reported = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    plausible = reported > 0 and (fps <= 0 or reported / max(fps, 1.0) <= 3600.0)
    total = reported
    if not plausible:
        total = 0
        while cap.grab():
            total += 1
        cap.release()
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError("video_unreadable")
    if total <= 0:
        cap.release()
        return [], {"total_frames": 0, "rotation_degrees": 0}
    if total <= max_frames:
        targets = set(range(total))
    else:
        targets = sorted({int(round(i * (total - 1) / float(max_frames - 1)))
                          for i in range(max_frames)})
        targets = set(targets)
    frames = []
    i = 0
    while len(frames) < len(targets):
        ok, fr = cap.read()
        if not ok:
            break
        if i in targets:
            frames.append(fr)
        i += 1
    cap.release()
    deg = _vote_rotation(frames) if frames else 0
    if deg:
        code = dict(_ROTATIONS)[deg]
        frames = [cv2.rotate(fr, code) for fr in frames]
    return frames, {"total_frames": total, "rotation_degrees": deg}

_DNN_FACE_NET = None

def detect_face_box_any(img):
    """Portrait-presence fallback (2026-10-28 vision sharpening):
    YuNet first; when YuNet sees no face, a second, architecturally
    different detector (OpenCV DNN ResNet-10 SSD, models fetched
    alongside the YuNet/SFace pair) takes a turn. Returns
    (x, y, w, h) in image pixels or None. PRESENCE ONLY — the box
    carries no landmarks, so it must never feed SFace alignment or
    matching; its job is the document-portrait statistic that
    drives capture coaching (a portrait YuNet misses on a small or
    degraded print is exactly the weak-reference case)."""
    global _DNN_FACE_NET
    row = largest_face(img)
    if row is not None:
        return (float(row[0]), float(row[1]), float(row[2]), float(row[3]))
    if cv2 is None or not hasattr(cv2, "dnn"):
        return None
    proto = os.path.join(MODELS_DIR, "face_deploy.prototxt")
    model = os.path.join(MODELS_DIR, "face_res10.caffemodel")
    if not (os.path.exists(proto) and os.path.exists(model)):
        return None
    try:
        if _DNN_FACE_NET is None:
            _DNN_FACE_NET = cv2.dnn.readNetFromCaffe(proto, model)
        h, w = img.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(img, (300, 300)), 1.0,
                                     (300, 300), (104.0, 177.0, 123.0))
        _DNN_FACE_NET.setInput(blob)
        dets = _DNN_FACE_NET.forward()
        best = None
        for i in range(dets.shape[2]):
            conf = float(dets[0, 0, i, 2])
            if conf < 0.5:
                continue
            x0, y0, x1, y1 = (int(dets[0, 0, i, 3] * w), int(dets[0, 0, i, 4] * h),
                              int(dets[0, 0, i, 5] * w), int(dets[0, 0, i, 6] * h))
            area = max(0, x1 - x0) * max(0, y1 - y0)
            if best is None or area > best[0]:
                best = (area, (float(x0), float(y0), float(x1 - x0), float(y1 - y0)))
        return best[1] if best else None
    except Exception:
        return None

def face_feature(img, face_row):
    """SFace 128-d embedding for an aligned face."""
    rec = _recognizer()
    aligned = rec.alignCrop(img, face_row)
    feat = rec.feature(aligned)
    return feat.ravel()

def work_image(img):
    """The image in detection/embedding space: downscaled to
    MAX_DETECT_DIM when larger. SFace normalises every aligned crop
    to 112x112, so embedding in this space loses nothing measurable
    (LFW operates at 250px) — while embedding at full phone-photo
    resolution measurably corrupts the result, because YuNet's box
    shrinks/drifts with input size (WS2 scale sweep in
    benchmarks/BIOMETRICS.md: same-face cosine vs a video frame
    falls from 0.435 at 512px to -0.05 at 1600px)."""
    h, w = img.shape[:2]
    if max(h, w) <= MAX_DETECT_DIM:
        return img
    scale = MAX_DETECT_DIM / float(max(h, w))
    return cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                      interpolation=cv2.INTER_AREA)

def extract_face_feature(path):
    """-> (feature, face_row, error_dict). On success error_dict is
    None. Detection + embedding both run in work_image space so the
    landmarks alignCrop consumes are native to the image embedded."""
    img = cv2.imread(path)
    if img is None:
        return None, None, {"status": "unclear", "findings": {"error": "image_unreadable"}, "reason_codes": ["face_image_unreadable"]}
    work = work_image(img)
    face = largest_face(work)
    if face is None:
        return None, None, None  # no face found (distinct from an error)
    return face_feature(work, face), face, None

WEAK_REFERENCE_MAX_PX = 80.0  # see face_box_stats

def face_box_stats(path):
    """(width_px, width_share, score) of the largest face in the
    image's work space, or None when no face is detected.

    This is the face-match REFERENCE-quality measure. Calibration on
    genuine documents (2026-10-28, warped renditions): strong
    references — CA driver's licence 123px, Canada passport 122px,
    NY ID 230px; weak references — the owner's NIN slip 56px, NG
    digital NIN card 75px, FRSC licence far-shot 72px, INEC PVC
    far-shot 12px. SFace aligns every face to 112x112, so a sub-80px
    reference is upscaled ~2x before embedding: a genuine holder's
    similarity is measurably depressed (the owner's slip matches his
    own live track at ~0.21 against the 0.363 threshold) while an
    impostor's stays low — a match still identifies, a non-match
    barely excludes. Below WEAK_REFERENCE_MAX_PX a would-be face-match
    FAIL is therefore recorded as unclear (weak reference), never as
    a mismatch; passes stand exactly as measured."""
    img = cv2.imread(path)
    if img is None:
        return None
    work = work_image(img)
    face = largest_face(work)
    if face is None:
        return None
    return float(face[2]), float(face[2]) / work.shape[1], float(face[14])

def _error(reason, detail):
    return {"status": "error", "findings": {"error": detail}, "reason_codes": [reason]}

def check_face_match(doc_path, selfie_path, pass_threshold=DEFAULT_THRESHOLD, margin=DEFAULT_MARGIN):
    """Compare the largest face in the document image with the selfie."""
    if cv2 is None:
        return _error("model_missing", "opencv_unavailable")
    if not models_present():
        return _error("model_missing", "face_models_not_fetched_run_scripts/fetch_models.py")
    if not doc_path or not selfie_path:
        return {"status": "not_run", "findings": {"reason": "document_or_selfie_missing"}, "reason_codes": ["face_match_not_run"]}
    try:
        doc_feat, doc_face, err = extract_face_feature(doc_path)
        if err: return err
        if doc_face is None:
            return {"status": "unclear", "findings": {"face_in_document": False}, "reason_codes": ["no_face_in_document"]}
        self_feat, self_face, err = extract_face_feature(selfie_path)
        if err: return err
        if self_face is None:
            return {"status": "unclear", "findings": {"face_in_document": True, "face_in_selfie": False}, "reason_codes": ["no_face_in_selfie"]}
        sim = cosine_similarity(doc_feat, self_feat)
    except Exception as e:
        return _error("face_compare_error", str(e)[:200])
    status, reasons = similarity_decision(sim, pass_threshold, margin)
    return {"status": status,
            "findings": {"similarity": round(float(sim), 4), "pass_threshold": pass_threshold, "margin": margin,
                         "method": "yunet+sface_cosine", "face_in_document": True, "face_in_selfie": True},
            "reason_codes": reasons}
