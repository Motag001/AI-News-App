# Data Sources: AI News Platform

Status: Draft v1.0
Related: LLD.md (fetchers), SECURITY.md (SSRF), PRD.md

## 1. Purpose

This document lists the source categories the platform may ingest, the rules for adding a source, and the operational requirements for each. The machine-readable list is `sources/registry.yaml`. A source must appear in the registry to be fetched.

## 2. Source categories

| Category | Fetcher | Examples (candidates, not yet approved) |
|---|---|---|
| RSS feeds | RssFetcher | Technology publications (e.g., MIT Technology Review, TechCrunch), robotics trade publications |
| Official APIs | ApiFetcher | AI company announcement and blog feeds offering APIs (e.g., OpenAI, Google, Anthropic) |
| Approved web extraction | WebExtractFetcher | Official announcement pages from research labs and governments, where RSS is not offered |
| Research repositories | ResearchRepoFetcher | arXiv (AI and robotics categories), university research news pages |

Each candidate must go through the approval process before activation.

## 3. Approval requirements

Every source must have:

1. Owner: a named person accountable for the source.
2. Terms check: written confirmation that the terms allow automated access for the stated purpose, or that the access method is public and permitted (for example, a documented feed or API).
3. Robots check: robots.txt reviewed for web extraction; disallowed paths are not fetched.
4. Tier: 1 (primary: official announcements, research repositories), 2 (established publication), 3 (other, requires corroboration before high credibility).
5. Rate limit: requests per minute agreed with the source or set to conservative default (1 request per 10 seconds per domain).
6. Copyright position: excerpts and links only; no full-text republication.
7. Contact: an address for takedown or change requests.

## 4. Registry format

```yaml
# sources/registry.yaml
- id: arxiv-ai
  name: arXiv AI category
  type: research
  url: https://export.arxiv.org/api/query
  owner: research-desk
  tier: 1
  status: active
  schedule_minutes: 120
  rate_limit_per_minute: 6
  allowed_paths: []
  terms_checked_on: 2026-10-01
  terms_reference: "https://info.arxiv.org/help/api/tou.html"
  copyright_position: excerpts_and_links
  contact: research-desk@example.org
```

Fields are validated by the source schema in `shared/config/`. Missing fields block registration.

## 5. Ingestion rules

- Only `active` sources are scheduled. `paused` and `disabled` sources are not fetched.
- Fetch only the allowed paths listed for the source.
- Respect `ETag`, `Last-Modified` and rate-limit headers.
- Store a maximum excerpt of 2,000 characters per item.
- Store original URLs; do not rewrite links except to remove tracking parameters.
- Record the fetch time for every item.
- Items older than the source's first-seen date are not back-filled beyond 7 days on first run.

## 6. Quality and health

Per-source metrics tracked daily:
- Fetch success rate (target 98%).
- Items per day and change from its 14-day average.
- Duplicate rate.
- Parse failures.
- Average credibility score of its items.

Automatic actions:
- Three consecutive failed runs: status set to `paused` and an operator alert sent.
- Parse failure rate above 30% for a day: alert the owner.
- Credibility drift (sudden large change): alert editorial review.

## 7. Removal and takedown

- Owners may request pause or removal at any time.
- Takedown requests from rights holders are actioned within 2 working days: source paused, items removed from public views, audit entry written.
- Removal retains the registry history entry with reason.

## 8. Licences and attribution

- Each story shows the original source name and links to it.
- Summaries are AI-generated and labelled as such.
- Where a source licence requires attribution text, it is stored in the registry and displayed on the article page.

## 9. Open items

- Confirmation of which official APIs permit commercial display of excerpts.
- Whether any source requires a licence fee.
- Language coverage beyond English.
