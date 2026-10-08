"""Index a guideline PDF into the persistent Chroma store the API retrieves evidence from.

    python scripts/ingest_guidelines.py ncdc.pdf --document "NCDC National Treatment Guidelines v2.0 (2025)"

Needs poppler's `pdftotext`. The PDF is split per printed page, then per numbered section
("5.1 Cystitis"); each chunk keeps its document, section and page. The rule-pack rows are
indexed too. The index is evidence for explanations only: it never changes a finding.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.stewardship import config  # noqa: E402
from backend.stewardship.evidence import build_store, chunks_from_pages  # noqa: E402
from backend.stewardship.rulepack import YamlRulePack  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--document", required=True, help="citation title stored with each chunk")
    parser.add_argument("--path", default=str(config.CHROMA_DIR))
    args = parser.parse_args()

    text = subprocess.run(
        ["pdftotext", "-layout", str(args.pdf), "-"], check=True, capture_output=True, text=True
    ).stdout
    pages = text.split("\f")
    store = build_store(YamlRulePack(), path=args.path)
    chunks = chunks_from_pages(pages, document=args.document, prefix=args.pdf.stem)
    store.add(chunks)
    print(f"Indexed {len(chunks)} sections from {args.pdf.name}; store has {store.count()} chunks.")


if __name__ == "__main__":
    main()
