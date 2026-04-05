from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from biomcp.server import _PUBLIC_TOOL_EXAMPLES, _dispatch

CRITICAL_PUBLIC_TOOLS = [
    "search_pubmed",
    "get_gene_info",
    "run_blast",
    "pathway_analysis",
    "get_drug_targets",
    "search_clinical_trials",
    "multi_omics_gene_report",
    "protein_family_analysis",
]


async def _run_public_tool(tool_name: str) -> dict[str, Any]:
    payload = _PUBLIC_TOOL_EXAMPLES[tool_name][0]
    started = time.perf_counter()
    envelope = json.loads(await _dispatch(tool_name, payload))
    elapsed_s = round(time.perf_counter() - started, 2)
    return {
        "tool": tool_name,
        "status": envelope.get("status"),
        "elapsed_s": elapsed_s,
        "error": envelope.get("error") if envelope.get("status") != "success" else None,
    }


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Run live public-tool contract smoke checks.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("live_contract_results.json"),
        help="Where to write the JSON results report.",
    )
    parser.add_argument(
        "--tools",
        nargs="*",
        default=CRITICAL_PUBLIC_TOOLS,
        help="Specific public tools to exercise. Defaults to the curated critical set.",
    )
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for tool_name in args.tools:
        result = await _run_public_tool(tool_name)
        results.append(result)
        if result["status"] != "success":
            failures.append(result)
        status = result["status"].upper()
        print(f"{tool_name}: {status} ({result['elapsed_s']}s)")
        if result["error"]:
            print(f"  error: {result['error']}")

    payload = {
        "summary": {
            "checked_tools": len(results),
            "failed_tools": len(failures),
            "succeeded_tools": len(results) - len(failures),
        },
        "results": results,
    }
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote report to {args.output}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
