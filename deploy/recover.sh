#!/usr/bin/env bash
# KYC recovery after a VM replacement: systemd units and apt packages live
# outside the workspace and are wiped; everything in the workspace survives.
# Reinstalls the units, restarts the services, and reports health.
set -e
# Runtime dependencies that live OUTSIDE the workspace and are wiped by a
# VM replacement: tesseract (OCR) and the `cryptography` pip package (WS3
# storage encryption). Restore both BEFORE starting the services; without
# tesseract OCR fails closed, and without cryptography + the master key
# the storage layer fails closed (503 on media reads).
if ! command -v tesseract >/dev/null; then
  echo "tesseract missing — reinstalling..."
  # Bounded apt attempt first. apt on this VM can wedge or 407
  # through the egress proxy (mirror-dependent; measured
  # 2026-10-27: a full lists crawl took ~25 min and some mirrors
  # refuse proxy auth for package fetches while the SAME proxy
  # serves curl fine). The fallback fetches the exact noble .deb
  # set from archive.ubuntu.com with curl and installs via dpkg —
  # 8 MB, seconds, proven in production on 2026-10-27.
  timeout 240 sudo apt-get install -y tesseract-ocr 2>/dev/null || true
  if ! command -v tesseract >/dev/null; then
    echo "apt path failed — curl .deb fallback..."
    _debdir=$(mktemp -d)
    for _u in \
      "pool/main/g/giflib/libgif7_5.2.2-1ubuntu1.2_amd64.deb" \
      "pool/universe/l/leptonlib/liblept5_1.82.0-3build4_amd64.deb" \
      "pool/universe/t/tesseract-lang/tesseract-ocr-eng_4.1.0-2_all.deb" \
      "pool/universe/t/tesseract-lang/tesseract-ocr-osd_4.1.0-2_all.deb" \
      "pool/universe/t/tesseract/libtesseract5_5.3.4-1build5_amd64.deb" \
      "pool/universe/t/tesseract/tesseract-ocr_5.3.4-1build5_amd64.deb"; do
      curl -s -O --max-time 120 --output-dir "$_debdir" "https://archive.ubuntu.com/ubuntu/$_u" || true
    done
    sudo dpkg -i "$_debdir"/*.deb 2>/dev/null || true
    rm -rf "$_debdir"
  fi
  command -v tesseract >/dev/null || \
    echo "WARNING: tesseract install failed — OCR fails closed (error) until installed"
fi
if ! HOME=/home/hatch python3 -c "import cryptography" 2>/dev/null; then
  echo "cryptography missing — reinstalling..."
  python3 -m pip install --user "cryptography>=42" || \
    sudo pip3 install --break-system-packages "cryptography>=42" || \
    echo "WARNING: cryptography install failed — encrypted media reads will 503"
fi
# zxing-cpp powers the barcode layer (PDF417/QR decode + payload
# cross-checks, 2026-10-27). Without it code_decode honestly reports
# the decoder unavailable and finds no codes — restore it too.
if ! HOME=/home/hatch python3 -c "import zxingcpp" 2>/dev/null; then
  echo "zxing-cpp missing — reinstalling..."
  python3 -m pip install --user "zxing-cpp" || \
    sudo pip3 install --break-system-packages "zxing-cpp" || \
    echo "WARNING: zxing-cpp install failed — barcode decoding unavailable until installed"
fi
# Dual-engine OCR (2026-10-28): PaddleOCR is the second reader in
# the unified family. The pip stack lives in the user site (wiped
# by replacement); the PP-OCRv5 mobile models live in ~/.paddlex
# (also wiped). Restore both. Failure here is NOT fatal: ocr2 is
# fail-closed and the platform runs single-engine until restored.
# httpx cannot parse this host's egress-proxy URL, so the models
# are fetched with curl (proven 2026-10-28), never the managed
# downloader. numpy/pandas pins are load-bearing (see DECISIONS).
if ! HOME=/home/hatch python3 -c "import paddleocr" 2>/dev/null; then
  echo "paddleocr missing — reinstalling (large, a few minutes)..."
  mkdir -p ~/workspace/KYC/.tmp/piptmp ~/workspace/KYC/.tmp/pipcache
  TMPDIR=~/workspace/KYC/.tmp/piptmp PIP_CACHE_DIR=~/workspace/KYC/.tmp/pipcache \
    python3 -m pip install --user --break-system-packages \
    "paddleocr==3.7.0" "paddlepaddle==3.3.1" "numpy==1.26.4" "pandas==2.2.3" \
    "opencv-contrib-python==4.10.0.84" 2>/dev/null || \
    echo "WARNING: paddle stack install failed — dual-engine OCR unavailable until installed"
fi
for _m in PP-OCRv5_mobile_det PP-OCRv5_mobile_rec; do
  _md="$HOME/.paddlex/official_models/$_m"
  if [ ! -s "$_md/inference.pdiparams" ]; then
    echo "paddle model $_m missing — fetching..."
    mkdir -p "$_md"
    for _f in config.json inference.json inference.pdiparams inference.yml; do
      curl -sL --max-time 300 -o "$_md/$_f" \
        "https://huggingface.co/PaddlePaddle/$_m/resolve/main/$_f" || true
    done
  fi
done
# Vision-sharpening models (FSRCNN super-resolution, WeChatQR pair,
# ResNet-10 portrait fallback) — same curl treatment; the canonical
# list lives in scripts/fetch_models.py.
for _spec in \
  "fsrcnn_small_x3.pb|https://raw.githubusercontent.com/Saafke/FSRCNN_Tensorflow/master/models/FSRCNN-small_x3.pb" \
  "wechat_detect.prototxt|https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/detect.prototxt" \
  "wechat_detect.caffemodel|https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/detect.caffemodel" \
  "wechat_sr.prototxt|https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/sr.prototxt" \
  "wechat_sr.caffemodel|https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/sr.caffemodel" \
  "face_deploy.prototxt|https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt" \
  "face_res10.caffemodel|https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20180205_fp16/res10_300x300_ssd_iter_140000_fp16.caffemodel"; do
  _name="${_spec%%|*}"; _url="${_spec#*|}"
  if [ ! -s ~/workspace/KYC/models/"$_name" ]; then
    curl -sL --max-time 300 -o ~/workspace/KYC/models/"$_name" "$_url" || true
  fi
done
[ -f ~/workspace/KYC/data/kyc-master.key ] || echo "WARNING: data/kyc-master.key missing — encrypted media cannot be read until the master key file is restored"

sudo cp ~/workspace/KYC/deploy/systemd/kyc.service ~/workspace/KYC/deploy/systemd/kyc-tunnel-client.service ~/workspace/KYC/deploy/systemd/kyc-staging.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kyc.service kyc-tunnel-client.service kyc-staging.service
sleep 4
systemctl is-active kyc.service kyc-tunnel-client.service
curl -s -m 10 http://127.0.0.1:8790/healthz; echo
curl -s -m 15 https://kyc.novamail.store/healthz; echo
