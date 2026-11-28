# WorkersCompensation.com Daily Decisions — Monitoring Pilot

This folder contains the first scheduled source-monitoring prototype.

## What it does
- Reads the official-source registry in `sources.json`.
- Checks configured HTML source pages.
- Discovers links whose text or URL suggests a decision, opinion, order, appeal, or panel item.
- Deduplicates links using a persistent seen-link registry.
- Produces a Markdown and JSON daily report.
- Reports fetch failures and sources that still require manual review separately.

## What it does not do yet
- It does not establish that every discovered link is a workers' compensation decision.
- It does not reliably extract decision dates, case numbers, holdings, or full text.
- It does not yet monitor all 50 states or every federal court.
- It does not claim that a successful page fetch means all decisions on that source were found.

Every candidate is marked for editorial verification. Source-specific adapters, date extraction, document text extraction, topic classification, and a production database are subsequent milestones.

## Run manually in GitHub
Open the repository's **Actions** tab, choose **Daily Decisions Source Monitor**, and select **Run workflow**. The workflow also runs on its daily schedule.

## Reports
Reports are written to `reports/YYYY-MM-DD.md` and `reports/YYYY-MM-DD.json`. Monitoring state is stored in `data/seen.json`.

## Local test
Requires Python 3.10 or later; no third-party Python packages are needed.

```bash
python daily-decisions-monitor/monitor.py
```

## Operational notes
GitHub Actions scheduled workflows run from the default branch, so this feature branch must be reviewed and merged before the scheduled run will operate from the default branch. The current cron is 12:15 UTC, approximately 7:15 AM Eastern during standard time. Adjust the schedule for daylight-saving time or move the scheduled job to Azure Functions for timezone-aware production scheduling.
