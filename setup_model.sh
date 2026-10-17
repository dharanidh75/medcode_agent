#!/bin/bash

# Exit on any error
set -e

echo "=========================================="
echo " Nexora - Local FAISS Model Setup Script"
echo "=========================================="
echo "This script will generate the dense vector index (.bin) files required by the local model."
echo "Note: This process may take 5-15 minutes depending on your CPU, as it encodes thousands of medical concepts."
echo ""

# Ensure we are in the root directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Check if python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed or not in PATH."
    exit 1
fi

echo "1. Creating Python virtual environment for local model..."
cd src/local_model
python3 -m venv .venv
source .venv/bin/activate

echo "2. Installing dependencies..."
pip install -r requirements.txt

echo "3. Indexing Diagnoses..."
python indexer.py --input ../backend/data/icd102019syst_codes.txt --domain diagnoses

echo "4. Indexing Procedures..."
python indexer.py --input ../backend/data/icd10pcs_codes_2026.txt --domain procedures

echo "5. Indexing Medications..."
python indexer.py --input ../backend/data/rx_dataset.txt --domain medications

echo "=========================================="
echo "Setup Complete!"
echo "The FAISS .bin indices have been successfully generated in src/local_model/data/."
echo "You can now run the backend and local_model services."
