# Product Requirements Document: AI News Platform

Status: Draft v1.0
Owner: Product
Last updated: 2026-10-31

## 1. Summary

The AI News Platform is a web application that collects AI, robotics and technology news from vetted external sources, uses an AI intelligence layer to classify, verify, rank and summarise each item, and presents the results as a categorised, searchable news feed. Users can read summaries and analysis, open full article details, change their settings, and share items to WhatsApp, LinkedIn, Facebook or by copying a link.

## 2. Problem

Coverage of AI and robotics is spread across research repositories, company announcements, trade publications and social feeds. Readers who need to keep up have to check many sources, judge which items are credible and important, and repeat stories that appear in several places. Existing aggregators often rank by recency or engagement rather than importance, and rarely explain why an item matters.

## 3. Goals

1. Give readers one daily view of the most important AI and robotics developments.
2. Remove duplicate coverage of the same story.
3. Show a credibility assessment and an importance score for every item.
4. Explain the impact and opportunities behind each item, not only its headline.
5. Make it easy to share an item in one step.

## 4. Non-goals (v1)

- User-generated content or commenting.
- Paid subscriptions or payments.
- Native mobile apps (the web app must be responsive).
- Real-time push alerts (v1 uses scheduled refreshes).
- Full-text republishing of copyrighted articles.
- Personalised recommendation models (v1 uses category and settings filters only).

## 5. Users

| User | Need |
|---|---|
| Industry reader | A short, trustworthy daily summary with impact notes |
| Researcher | Access to research papers, with credibility and duplicate handling |
| Founder or analyst | Importance scores and opportunity analysis to spot trends |
| Admin / operator | Confidence that ingestion is healthy and sources are approved |

## 6. Functional requirements

### 6.1 Sources and ingestion
- FR-1: The system must ingest items from four source types: RSS feeds, official APIs, approved web extraction, and research repositories.
- FR-2: Ingestion must run on a schedule (configurable, default every hour) and must be able to run on demand for a single source.
- FR-3: Every source must be registered in an approved source list with an owner, type, URL, and status. Unregistered sources must not be fetched.
- FR-4: Each fetched item must be parsed and normalised into a common record (title, source, author, published time, URL, body text, language, category hints).

### 6.2 AI intelligence
- FR-5: Duplicate items (same story from several sources) must be detected and grouped under one canonical story.
- FR-6: Each story must be classified into a topic category (e.g., AI models, robotics, research, policy, industry).
- FR-7: Each story must receive a credibility assessment based on source reputation and corroboration.
- FR-8: Each story must receive an importance score that combines recency, reach, credibility and topic weight.
- FR-9: An LLM must produce a short summary and an impact and opportunity analysis for each story.
- FR-10: Every AI output must store the model name, prompt version, and timestamp.

### 6.3 Reading experience
- FR-11: The home dashboard shows top stories ordered by importance, with a short summary, source, time, category, and credibility label.
- FR-12: Category pages list stories in one category, with filters for date range and credibility.
- FR-13: The article details page shows the summary, impact analysis, source link, duplicate sources, and share actions.
- FR-14: The settings page lets users choose preferred categories, default date range and display density.

### 6.4 Sharing
- FR-15: Users can share a story to WhatsApp, LinkedIn or Facebook, or copy a link to clipboard.
- FR-16: Shared links must contain only the story identifier, never user or session data.

### 6.5 Accounts and access
- FR-17: Users must sign in before changing settings. Reading public news may be allowed without sign-in (decision pending, see Open questions).
- FR-18: Access control must enforce role-based permissions for readers and operators.

## 7. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | Dashboard p95 response under 800 ms from cache |
| Freshness | New items visible within 60 minutes of publication by default |
| Availability | 99.5% monthly for reading pages |
| Accessibility | WCAG 2.1 AA for all reading pages |
| Responsiveness | Usable from 360 px width upward |
| Security | See SECURITY.md; SSRF protection, input validation, prompt injection protection |
| Observability | Structured logs and error tracking for ingestion, AI processing and API |
| Auditability | Processing and audit logs retained 12 months |
| Localisation | English at launch; data model ready for other languages |

## 8. Success metrics

- Duplicate rate: at least 30% of raw items grouped under an existing story (measured weekly).
- Summary acceptance: at least 85% of sampled summaries rated accurate by the editorial reviewer.
- Engagement: 40% of weekly readers open at least one article details page.
- Share rate: 5% of article detail views result in a share action.
- Ingestion health: 98% of scheduled fetches succeed per day.

## 9. Assumptions

- Sources permit ingestion of headlines, summaries and links, and allow limited excerpts for summarisation.
- An LLM provider with suitable data-handling terms is available.
- Editorial staff can review a sample of items each week.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Inaccurate AI summaries | Show source link on every item; sample review; prompt versioning |
| Copyright concerns with full text | Store excerpts and links only; summarise rather than copy |
| Malicious or unsafe web content | Approved sources only, SSRF protection, prompt injection protection |
| Source outages or format changes | Per-source health checks and alerts |
| Cost growth from LLM calls | Cache results, deduplicate before summarising, budget alerts |

## 11. Milestones

1. Ingestion for RSS and official APIs, with normalisation.
2. Duplicate detection, classification and credibility assessment.
3. Importance scoring, LLM summaries and impact analysis.
4. Reading experience and settings.
5. Sharing, security hardening and accessibility audit.
6. Pilot with a small reader group, then public launch.

## 12. Open questions

- Must readers sign in to read news, or is reading public?
- Which languages are needed beyond English?
- Who owns editorial sign-off on the approved source list?
- What is the LLM budget per day?
