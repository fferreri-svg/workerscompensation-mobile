#!/usr/bin/env python3
"""Pilot source monitor for WorkersCompensation.com Daily Decisions.

This first version discovers candidate links from configured official pages.
It is deliberately conservative: candidates require editorial verification.
It does not claim that a successful page fetch represents complete coverage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SOURCES_FILE = ROOT / "sources.json"
DATA_DIR = ROOT / "data"
SEEN_FILE = DATA_DIR / "seen.json"
REPORT_DIR = ROOT / "reports"
USER_AGENT = "WorkersCompensationCom-DailyDecisions/0.1 (source-monitor; contact: website operator)"
LINK_TERMS = ("decision", "opinion", "order", "award", "appeal", "panel", "en banc", "memorandum")
TOPICS = {
    "Compensability": ("arising out of", "course of employment", "compensab", "work-related", "occupational disease"),
    "Causation": ("causation", "causal", "medical causation", "contributing cause"),
    "Benefits": ("temporary total", "temporary partial", "permanent total", "permanent partial", "indemnity", "wage loss"),
    "Medical Treatment": ("medical treatment", "authorization", "medical necessity", "utilization review", "provider"),
    "Disability / Impairment": ("impairment", "disability rating", "maximum medical improvement", "mmi"),
    "Employment / Coverage": ("independent contractor", "employee status", "employment", "statutory employer", "borrowed servant"),
    "Procedure / Jurisdiction": ("jurisdiction", "statute of limitations", "notice", "venue", "procedure", "evidence"),
    "Subrogation / Liens": ("subrogation", "lien", "third party"),
    "Retaliation": ("retaliation", "discrimination", "whistleblower"),
}

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(" ".join(self._text).split())))
            self._href = None
            self._text = []

def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback

def fetch(url):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"})
    with urlopen(req, timeout=35) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read(5_000_000)
        return response.geturl(), content_type, body

def classify(text):
    low = text.lower()
    found = [topic for topic, terms in TOPICS.items() if any(term in low for term in terms)]
    return found or ["Needs Editorial Classification"]

def candidate_links(source, html):
    parser = LinkParser()
    parser.feed(html)
    results = []
    for href, label in parser.links:
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        absolute = urljoin(source["url"], href)
        searchable = (label + " " + absolute).lower()
        if not any(term in searchable for term in LINK_TERMS):
            continue
        if absolute.rstrip("/") == source["url"].rstrip("/"):
            continue
        title = label or absolute.rsplit("/", 1)[-1] or source["name"]
        results.append({"title": title[:400], "url": absolute})
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Report date YYYY-MM-DD; defaults to UTC today.")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    report_date = args.date or now.date().isoformat()
    registry = load_json(SOURCES_FILE, {"sources": []})
    seen = load_json(SEEN_FILE, {"items": {}})
    seen_items = seen.setdefault("items", {})
    new_items, source_results = [], []

    for source in registry.get("sources", []):
        result = {"id": source["id"], "name": source["name"], "jurisdiction": source["jurisdiction"], "status": "unknown", "checked_at": now.isoformat(), "new_candidates": 0, "error": None}
        if source.get("method") == "manual_review":
            result["status"] = "manual_review_required"
            source_results.append(result)
            continue
        try:
            final_url, content_type, body = fetch(source["url"])
            if "html" not in content_type.lower() and not body.lstrip().startswith(b"<"):
                result["status"] = "fetched_non_html_manual_review"
                source_results.append(result)
                continue
            html = body.decode("utf-8", errors="replace")
            candidates = candidate_links(source, html)
            result["status"] = "checked_candidates_found" if candidates else "checked_no_candidate_links"
            result["final_url"] = final_url
            result["candidate_links_seen"] = len(candidates)
            for item in candidates:
                key = hashlib.sha256((source["id"] + "|" + item["url"]).encode()).hexdigest()
                if key in seen_items:
                    continue
                seen_items[key] = {"first_seen": now.isoformat(), "source_id": source["id"], "url": item["url"]}
                record = {
                    "id": key, "case_name_or_title": item["title"], "jurisdiction": source["jurisdiction"],
                    "court_or_agency": source["name"], "decision_type": source["kind"],
                    "decision_date": None, "publication_date": None, "topics": classify(item["title"]),
                    "source_url": source["url"], "decision_url": item["url"],
                    "review_status": "pending_editorial_verification",
                    "note": "Candidate link discovered from an official source page. Confirm that it is a new workers' compensation decision and verify dates and document text."
                }
                new_items.append(record)
                result["new_candidates"] += 1
        except Exception as exc:
            result["status"] = "source_error"
            result["error"] = str(exc)[:500]
        source_results.append(result)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(seen, indent=2) + "\n", encoding="utf-8")
    report = {
        "report_date": report_date, "generated_at": now.isoformat(),
        "new_candidate_count": len(new_items), "new_candidates": new_items,
        "source_checks": source_results,
        "coverage_notice": "This is a pilot discovery report. A source fetch is not proof of complete coverage. Candidates require verification; source errors and manual-review sources are reported separately."
    }
    (REPORT_DIR / f"{report_date}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [f"# WorkersCompensation.com Daily Decisions — {report_date}", "",
             f"**New candidate links:** {len(new_items)}", "",
             "> Pilot report: candidate links are not confirmed decisions until editorial verification. A source error or manual-review status is not evidence that no decisions were issued.", "",
             "## New candidate decisions"]
    if not new_items:
        lines += ["No new candidate links were identified by the current pilot checks."]
    for item in sorted(new_items, key=lambda x: (x["jurisdiction"], x["case_name_or_title"].lower())):
        lines += [f"### {item['case_name_or_title']}", f"- **Jurisdiction:** {item['jurisdiction']}",
                  f"- **Source:** {item['court_or_agency']}", f"- **Preliminary topics:** {', '.join(item['topics'])}",
                  f"- **Verification:** Pending editorial review", f"- **[Open source document/page]({item['decision_url']})", ""]
    lines += ["## Source monitoring status", "", "| Jurisdiction | Source | Status | New candidates |", "|---|---|---:|---:|"]
    for row in source_results:
        lines.append(f"| {row['jurisdiction']} | {row['name']} | {row['status']} | {row['new_candidates']} |")
    lines += ["", "## Monitoring exceptions", ""]
    errors = [r for r in source_results if r["error"] or "manual_review" in r["status"]]
    if errors:
        for row in errors:
            lines.append(f"- **{row['name']}** — {row['status']}: {row['error'] or 'Automated retrieval not yet configured.'}")
    else:
        lines.append("No source errors were recorded in this run.")
    lines += ["", "---", "*Generated by the WorkersCompensation.com Daily Decisions pilot monitor.*"]
    (REPORT_DIR / f"{report_date}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report generated for {report_date}: {len(new_items)} new candidate links; {len(source_results)} sources checked.")
    print(f"Markdown: {REPORT_DIR / (report_date + '.md')}")
    print(f"JSON: {REPORT_DIR / (report_date + '.json')}")

if __name__ == "__main__":
    main()
