#!/usr/bin/env python3
"""Download the OpenCV Zoo face models used by Phase 2 face checks.

Models (from https://github.com/opencv/opencv_zoo, licences in that repo:
YuNet — MIT; SFace — Apache 2.0; the .onnx files are downloaded at setup
time, they are NOT committed to this repo — models/ is gitignored):

  * face_detection_yunet_2023mar.onnx   (YuNet face detector)
  * face_recognition_sface_2021dec.onnx (SFace face recogniser — this is
    the SFace model file opencv_zoo actually ships; there is no
    "2023dec" SFace file in that repo)

The .onnx files in opencv_zoo are Git LFS objects, so downloads go
through media.githubusercontent.com (a plain raw.githubusercontent fetch
returns the 131-byte LFS pointer, not the model).

Usage: python3 scripts/fetch_models.py
If a model is absent at runtime, the face checks return status 'error'
with reason 'model_missing' — never a fake pass.
"""
import os, sys, urllib.request

BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
FILES = {
    "face_detection_yunet/face_detection_yunet_2023mar.onnx": "face_detection_yunet_2023mar.onnx",
    "face_recognition_sface/face_recognition_sface_2021dec.onnx": "face_recognition_sface_2021dec.onnx",
}
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

# Vision-sharpening models (2026-10-28), plain raw downloads with
# per-file minimum plausible sizes: FSRCNN-small super-resolution,
# the WeChatQRCode detector pair (files live on the opencv_3rdparty
# mirror's wechat_qrcode BRANCH), and the ResNet-10 SSD face
# detector used as the portrait-presence fallback. All optional at
# runtime — every consumer fails closed to its primary path.
RAW_FILES = {
    "https://raw.githubusercontent.com/Saafke/FSRCNN_Tensorflow/master/models/FSRCNN-small_x3.pb":
        ("fsrcnn_small_x3.pb", 5_000),
    "https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/detect.prototxt":
        ("wechat_detect.prototxt", 10_000),
    "https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/detect.caffemodel":
        ("wechat_detect.caffemodel", 100_000),
    "https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/sr.prototxt":
        ("wechat_sr.prototxt", 1_000),
    "https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/sr.caffemodel":
        ("wechat_sr.caffemodel", 5_000),
    "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt":
        ("face_deploy.prototxt", 10_000),
    "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20180205_fp16/res10_300x300_ssd_iter_140000_fp16.caffemodel":
        ("face_res10.caffemodel", 1_000_000),
}

def main():
    os.makedirs(MODELS_DIR, exist_ok=True)
    ok = True
    for src, name in FILES.items():
        dest = os.path.join(MODELS_DIR, name)
        if os.path.isfile(dest) and os.path.getsize(dest) > 100_000:
            print(f"[models] {name} already present ({os.path.getsize(dest)} bytes)")
            continue
        url = f"{BASE}/{src}"
        print(f"[models] downloading {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kyc-fetch-models"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
                f.write(r.read())
            print(f"[models] {name}: {os.path.getsize(dest)} bytes")
            if os.path.getsize(dest) < 100_000:
                print(f"[models] WARNING: {name} looks too small — download may have failed"); ok = False
        except Exception as e:
            print(f"[models] FAILED {name}: {e}"); ok = False
    for url, (name, min_size) in RAW_FILES.items():
        dest = os.path.join(MODELS_DIR, name)
        if os.path.isfile(dest) and os.path.getsize(dest) > min_size:
            print(f"[models] {name} already present ({os.path.getsize(dest)} bytes)")
            continue
        print(f"[models] downloading {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kyc-fetch-models"})
            with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
                f.write(r.read())
            print(f"[models] {name}: {os.path.getsize(dest)} bytes")
            if os.path.getsize(dest) < min_size:
                print(f"[models] WARNING: {name} looks too small — download may have failed"); ok = False
        except Exception as e:
            print(f"[models] FAILED {name}: {e}"); ok = False
    print("[models] OK" if ok else "[models] INCOMPLETE — face checks will report model_missing")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
