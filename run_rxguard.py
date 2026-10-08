#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "reportlab>=4.0.0",
#     "opencv-python>=4.8.0",
#     "paddleocr>=2.7.0",
#     "paddlepaddle>=2.5.0",
#     "pillow>=10.0.0",
#     "spacy>=3.7.0",
#     "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1.tar.gz",
#     "ollama>=0.1.0",
#     "langchain>=0.1.0",
#     "chromadb>=0.4.0",
#     "pypdf>=3.17.0",
#     "pdfplumber>=0.9.0",
#     "sentence-transformers>=2.2.0",
#     "networkx>=3.0",
#     "torch>=2.0.0",
#     "transformers>=4.40.0",
#     "safetensors>=0.4.0",
#     "huggingface_hub>=0.20.0"
# ]
# ///
"""
RxGuard End-to-End Pipeline Runner
Runs the full 9-module clinical safety audit on a prescription image
and generates a professional PDF report.

Usage:
  python run_rxguard.py --image path/to/prescription.jpg --output report.pdf
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add the project root to the python path
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))

def check_dependencies():
    missing = []
    try:
        import spacy
    except ImportError:
        missing.append("spacy")
    try:
        import reportlab
    except ImportError:
        missing.append("reportlab")
    try:
        import paddleocr
    except ImportError:
        missing.append("paddleocr")
        
    if missing:
        print("Warning: Some core packages are missing: " + ", ".join(missing))
        print("To install dependencies, run: venv/bin/pip install -r requirements.txt\n")

def main():
    parser = argparse.ArgumentParser(
        description="RxGuard End-to-End Clinical Prescription Auditor"
    )
    parser.add_argument(
        "--image", 
        required=True, 
        help="Path to the prescription image file (e.g. JPG, PNG)"
    )
    parser.add_argument(
        "--output", 
        default="audit_report.pdf", 
        help="Path where the output PDF report should be written (default: audit_report.pdf)"
    )
    parser.add_argument(
        "--json-out", 
        default="audit_result.json", 
        help="Path where the raw JSON audit results should be written (default: audit_result.json)"
    )
    args = parser.parse_args()

    # Check dependencies first
    check_dependencies()

    image_path = args.image
    if not os.path.exists(image_path):
        print(f"Error: Image file not found: {image_path}", file=sys.stderr)
        return 1

    print(f"[*] Starting RxGuard audit pipeline on: {image_path}")
    print("[*] Importing orchestrator...")
    
    try:
        from backend.orchestrator import audit_prescription
    except ImportError as e:
        print(f"Error importing orchestrator: {e}", file=sys.stderr)
        return 1

    print("[*] Running clinical safety audit modules (1 through 9)...")
    audit_results = audit_prescription(image_path)

    # Save raw JSON results
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2, ensure_ascii=False)
    print(f"[+] Raw JSON results saved to: {args.json_out}")

    # Check if there were critical errors
    errors = audit_results.get("errors", [])
    if errors:
        print("\nNote: Some modules encountered errors during execution:")
        for err in errors:
            print(f"  - Module '{err.get('module')}': {err.get('error')}")
        print("Pipeline continued using available heuristics and fallbacks.\n")

    print("[*] Generating PDF report...")
    try:
        from backend.report_generator import generate_audit_report
        generate_audit_report(audit_results, args.output)
        print(f"[+] Success! PDF safety report written to: {args.output}")
    except ImportError:
        print("Error: Could not generate PDF because 'reportlab' is not installed.")
        print("Please install reportlab to generate the PDF: venv/bin/pip install reportlab")
        return 1
    except Exception as e:
        print(f"Error during PDF report generation: {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
