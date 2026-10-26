#!/usr/bin/env bash
# KYC recovery after a VM replacement: systemd units and apt packages live
# outside the workspace and are wiped; everything in the workspace survives.
# Reinstalls the units, restarts the services, and reports health.
set -e
sudo cp ~/workspace/KYC/deploy/systemd/kyc.service ~/workspace/KYC/deploy/systemd/kyc-tunnel-client.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kyc.service kyc-tunnel-client.service
sleep 4
systemctl is-active kyc.service kyc-tunnel-client.service
curl -s -m 10 http://127.0.0.1:8790/healthz; echo
command -v tesseract >/dev/null || echo "WARNING: tesseract missing — OCR fails closed (error) until reinstalled: sudo apt-get install -y tesseract-ocr"
curl -s -m 15 https://kyc.novamail.store/healthz; echo
