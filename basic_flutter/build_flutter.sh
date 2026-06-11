#!/bin/bash

# Flutter Build Script
# This script builds the Flutter app with proper Java configuration

# Set Java 17 environment
export JAVA_HOME=/usr/lib/jvm/java-1.17.0-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH

# Navigate to Flutter project
cd /home/mahmoud/v2/basic_flutter

echo "Building Flutter app with Java 17..."
echo "Java version: $(java -version 2>&1 | head -1)"
echo "Flutter version: $(flutter --version 2>&1 | head -1)"
echo ""

# Build the APK
flutter build apk --release

echo ""
echo "Build complete!"