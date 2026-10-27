#!/bin/bash
for i in $(seq 1 60); do
  if sudo apt-get install -y tesseract-ocr >> ~/workspace/KYC/deploy/tesseract-reinstall.log 2>&1; then
    echo "TESSERACT_OK $(date)" >> ~/workspace/KYC/deploy/tesseract-reinstall.log
    exit 0
  fi
  sleep 60
done
echo "TESSERACT_FAIL_AFTER_RETRIES $(date)" >> ~/workspace/KYC/deploy/tesseract-reinstall.log
