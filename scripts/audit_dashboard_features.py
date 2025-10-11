#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple


FEATURES = [
    "alerts_red_flags",
    "drilldown_segmentation",
    "trend_timeseries",
    "custom_dashboards",
    "manager_dept_scorecards",
    "goal_okr",
    "forecasts_simulation",
    "compliance_tracking",
    "report_export_scheduled",
    "benchmarking_external",
]


def scan_files(root: Path, patterns: List[str]) -> List[Tuple[str, str]]:
    hits: List[Tuple[str, str]] = []
    if not root.exists():
        return hits
    # Limit scope to probable source paths
    roots: List[Path] = []
    if (root / "app").exists():
        roots.append(root / "app")
    if (root / "scripts").exists():
        roots.append(root / "scripts")
    if (root / "src").exists():
        roots.append(root / "src")
    if not roots:
        roots = [root]
    for base in roots:
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            try:
                text = p.read_text(errors="ignore")
            except Exception:
                continue
            for pat in patterns:
                if re.search(pat, text, flags=re.IGNORECASE):
                    hits.append((str(p.relative_to(root)), pat))
    return hits


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit dashboard features across frontend and backend")
    ap.add_argument("--frontend", default=os.getenv("FRONTEND_PATH", "../teamflow"), help="Path to frontend repo root")
    args = ap.parse_args()

    backend_root = Path(__file__).resolve().parents[1]
    frontend_root = Path(args.frontend).resolve()

    # Patterns to detect signals
    patt = {
        "alerts_red_flags": [r"/alerts", r"red flag", r"threshold", r"alert\W"],
        "drilldown_segmentation": [r"/reports/|group\s*:\s*\{\$|group_by", r"segment|segmentation", r"department"],
        "trend_timeseries": [r"trend|time series|sparkline|chart\(|Chart\.|Recharts|VictoryChart|line chart"],
        "custom_dashboards": [r"widget", r"custom dashboard|drag|layout|gridster|react-grid-layout"],
        "manager_dept_scorecards": [r"scorecard|department", r"manager"],
        "goal_okr": [r"okr|objective|key result|goal"],
        "forecasts_simulation": [r"forecast|projection|simulate|what-if"],
        "compliance_tracking": [r"compliance|policy|violation|flag"],
        "report_export_scheduled": [r"text/csv|Export CSV|exportCsv|/export\.csv|schedule|cron"],
        "benchmarking_external": [r"benchmark|industry|external|peer"],
    }

    results: Dict[str, Dict[str, object]] = {}
    for feat in FEATURES:
        be_hits = scan_files(backend_root, patt.get(feat, []))
        fe_hits = scan_files(frontend_root, patt.get(feat, []))
        total = len(be_hits) + len(fe_hits)
        # Heuristic for partial vs exists
        if total == 0:
            status = "missing"
        elif feat in {"drilldown_segmentation", "report_export_scheduled"}:
            # These likely exist in limited areas already
            status = "partial"
        else:
            status = "exists" if total > 2 else "partial"
        results[feat] = {
            "status": status,
            "evidence": {
                "backend": be_hits[:5],
                "frontend": fe_hits[:5],
            },
        }

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
