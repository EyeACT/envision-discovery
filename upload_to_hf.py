#!/usr/bin/env python3
"""
Upload trained ENVISION model to Hugging Face Hub.

Usage:
    python upload_to_hf.py
"""

import shutil
from pathlib import Path
from huggingface_hub import HfApi, create_repo

# Configuration
MODEL_DIR = Path(__file__).parent / "models" / "setfit_v6"
MODEL_CARD = Path(__file__).parent / "MODEL_CARD.md"
REPO_ID = "EyeACT/envision-eye-imaging-classifier"

def main():
    print(f"Uploading model to {REPO_ID}")
    
    # Check model exists
    if not MODEL_DIR.exists():
        print(f"Error: Model directory not found: {MODEL_DIR}")
        return
    
    # Copy model card to model directory as README.md
    readme_path = MODEL_DIR / "README.md"
    if MODEL_CARD.exists():
        shutil.copy(MODEL_CARD, readme_path)
        print(f"Copied model card to {readme_path}")
    
    # Initialize API
    api = HfApi()
    
    # Create repo if it doesn't exist
    try:
        create_repo(repo_id=REPO_ID, repo_type="model", exist_ok=True)
        print(f"Repository {REPO_ID} ready")
    except Exception as e:
        print(f"Note: {e}")
    
    # Upload all files
    print(f"Uploading files from {MODEL_DIR}...")
    api.upload_folder(
        folder_path=str(MODEL_DIR),
        repo_id=REPO_ID,
        repo_type="model",
        commit_message="Upload ENVISION eye imaging classifier v1.0"
    )
    
    print(f"\n✅ Model uploaded successfully!")
    print(f"View at: https://huggingface.co/{REPO_ID}")

if __name__ == "__main__":
    main()


