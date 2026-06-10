#!/bin/bash
if [ -f android/gradlew ]; then
  cd android
  chmod +x gradlew
  ./gradlew signingReport 2>&1 | head -30
fi
# Fix ADB permissions
echo "0x18d1" > /tmp/android_vendor 2>/dev/null || true
lsusb 2>/dev/null | grep -i "google\|android\|xiaomi\|oppo\|vivo" || echo "No Android devices detected via USB"
