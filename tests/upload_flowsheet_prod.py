"""Upload a flowsheet JSON payload to the v2 production upsert endpoint.

Usage:
    python tests/upload_flowsheet_prod.py \
        --api-key "$PRISMA_API_KEY" \
        --payload reference_data/prisma_v2/dac_min_2026-07-01.json

Defaults:
    on_exists=append
    appendix=_2026-07-01
    screening_analysis_name=dac_screening_2026-07-01 (recommended)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from prisma_api.prisma_api_v2 import PrismaAPIv2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload one flowsheet JSON file to PrISMa v2 production via upsert_flowsheets()."
    )
    parser.add_argument(
        "--payload",
        default="reference_data/prisma_v2/dac_min_2026-07-01.json",
        help="Path to flowsheet JSON payload file.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("PRISMA_API_KEY", ""),
        help="Production API key. If omitted, uses PRISMA_API_KEY.",
    )
    parser.add_argument(
        "--appendix",
        default="_2026-07-01",
        help="Appendix value used when on_exists=append.",
    )
    parser.add_argument(
        "--screening-analysis-name",
        default="dac_screening_2026-07-01",
        help="Optional screening analysis name passed to upsert (recommended for production).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if not args.api_key:
        raise SystemExit("Missing API key. Pass --api-key or set PRISMA_API_KEY.")

    payload_path = Path(args.payload)
    if not payload_path.exists():
        raise SystemExit(f"Payload file not found: {payload_path}")

    with payload_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    api_v2 = PrismaAPIv2(key=args.api_key, dev=False, return_format="json")
    result = api_v2.upsert_flowsheets(
        [payload],
        screening_analysis_name=args.screening_analysis_name,
        on_exists="append",
        appendix=args.appendix,
    )

    print("Upload completed.")
    print(f"Payload: {payload_path}")
    print("Endpoint mode: append")
    print(f"Appendix: {args.appendix}")
    print(f"Screening analysis name: {args.screening_analysis_name}")
    print("Response:")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
