#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/lambda_build"
ZIP_FILE="$SCRIPT_DIR/lambda_function.zip"

echo "Building Lambda package..."

# Clean previous build
rm -rf "$BUILD_DIR"
rm -f "$ZIP_FILE"

# Create build directory
mkdir -p "$BUILD_DIR"

# Copy source files
cp "$SCRIPT_DIR/../src/handler.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/../src/requirements.txt" "$BUILD_DIR/"

# Install dependencies
echo "Installing dependencies..."
pip install -r "$BUILD_DIR/requirements.txt" -t "$BUILD_DIR" --quiet

# Remove unnecessary files to reduce package size
rm -rf "$BUILD_DIR"/*.dist-info
rm -rf "$BUILD_DIR/__pycache__"
rm -f "$BUILD_DIR/requirements.txt"

# Create zip
cd "$BUILD_DIR"
zip -r "$ZIP_FILE" . -q
cd "$SCRIPT_DIR"

# Cleanup
rm -rf "$BUILD_DIR"

echo "Lambda package created: $ZIP_FILE"
