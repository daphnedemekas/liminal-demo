#!/bin/bash
set -e

# Railway auto-detects Python and installs from requirements.txt
# We just need to build the frontend here
cd frontend
npm install
npm run build
cd ..

echo "Build complete! Frontend built successfully."
