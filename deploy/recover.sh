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
[ -f ~/workspace/KYC/data/kyc-master.key ] || echo "WARNING: data/kyc-master.key missing — encrypted media cannot be read until the master key file is restored"

sudo cp ~/workspace/KYC/deploy/systemd/kyc.service ~/workspace/KYC/deploy/systemd/kyc-tunnel-client.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kyc.service kyc-tunnel-client.service
sleep 4
systemctl is-active kyc.service kyc-tunnel-client.service
curl -s -m 10 http://127.0.0.1:8790/healthz; echo
curl -s -m 15 https://kyc.novamail.store/healthz; echo
