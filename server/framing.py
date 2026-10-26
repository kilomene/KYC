"""Document framing check (live-scanner build, 2026-10-26).

Verifies, with OpenCV contour detection, that a captured document image
actually contains a card-like quadrilateral that roughly fills the
frame — the server-side counterpart of the live scanner's viewfinder.
A random photo, a blank image, or a document photographed from across
the room must not pass this; a card filling the frame must.

Method: greyscale -> Gaussian blur -> Canny edges -> external contours
sorted by area -> approxPolyDP. The largest contour that approximates
to 4 points is the candidate document; its area as a share of the
whole image decides:

    ratio >= 0.25          -> pass
    0.10 <= ratio < 0.25   -> unclear (document present but small in
                              frame)
    no 4-point contour, or ratio < 0.10 -> fail

This check is REQUIRED and decision-bearing for document sessions
(server/flowconfig.py + server/engine.py): fail auto-rejects with
reason document_not_detected, and unclear auto-rejects with reason
document_quality_rescan — the live scanner gates capture on its own
client-side document detection, so a submitted fail/unclear framing
is a bad capture to redo, never a case queued for a human.

If OpenCV is unavailable the check returns 'error' — never a pass
(the fail-closed pattern used by every check in this codebase).
"""
try:
    import cv2
    import numpy as np
except Exception:  # OpenCV missing -> framing check errors, never passes
    cv2 = None
    np = None

PASS_RATIO = 0.25
UNCLEAR_RATIO = 0.10

def check_document_framing(path=None, data=None):
    if cv2 is None:
        return {"status": "error", "findings": {"error": "opencv_unavailable"}, "reason_codes": ["framing_unavailable"]}
    try:
        if data is not None:
            img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        else:
            img = cv2.imread(path)
    except Exception as e:
        return {"status": "fail", "findings": {"error": f"image_unreadable: {e}"}, "reason_codes": ["invalid_image"]}
    if img is None:
        return {"status": "fail", "findings": {"error": "image_unreadable"}, "reason_codes": ["invalid_image"]}
    h, w = img.shape[:2]
    image_area = float(w * h)
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    grey = cv2.GaussianBlur(grey, (5, 5), 0)
    edges = cv2.Canny(grey, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    findings = {"width": w, "height": h, "quad_found": False, "area_ratio": 0.0, "largest_contour_ratio": 0.0}
    if not contours:
        return {"status": "fail", "findings": findings, "reason_codes": ["document_not_detected"]}
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    findings["largest_contour_ratio"] = round(cv2.contourArea(contours[0]) / image_area, 4)
    for cnt in contours[:5]:
        ratio = cv2.contourArea(cnt) / image_area
        if ratio < 0.02:
            break
        approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
        if len(approx) == 4:
            findings["quad_found"] = True
            findings["area_ratio"] = round(ratio, 4)
            break
    if not findings["quad_found"]:
        # Something fills the frame but its edges do not resolve to a
        # clean quadrilateral — a human looks rather than a hard fail.
        if findings["largest_contour_ratio"] >= 0.5:
            return {"status": "unclear", "findings": findings, "reason_codes": ["document_edges_unclear"]}
        return {"status": "fail", "findings": findings, "reason_codes": ["document_not_detected"]}
    ratio = findings["area_ratio"]
    if ratio >= PASS_RATIO:
        return {"status": "pass", "findings": findings, "reason_codes": []}
    if ratio >= UNCLEAR_RATIO:
        return {"status": "unclear", "findings": findings, "reason_codes": ["document_small_in_frame"]}
    return {"status": "fail", "findings": findings, "reason_codes": ["document_too_small_in_frame"]}

def combine_framing(front_res, back_res=None):
    """Combine per-side framing results into one document_framing check
    (worst status wins). Each side's own result stays in the findings."""
    order = {"pass": 0, "unclear": 1, "error": 2, "not_run": 2, "fail": 3}
    findings = {"front": {"status": front_res["status"], **front_res.get("findings", {})}}
    worst = front_res
    if back_res is not None:
        findings["back"] = {"status": back_res["status"], **back_res.get("findings", {})}
        if order.get(back_res["status"], 2) > order.get(worst["status"], 2):
            worst = back_res
    reasons = list(front_res.get("reason_codes", []))
    if back_res is not None:
        reasons += [r for r in back_res.get("reason_codes", []) if r not in reasons]
    return {"status": worst["status"], "findings": findings, "reason_codes": reasons}
