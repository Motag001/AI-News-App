# Design: AI News Platform

Status: Draft v1.0
Related: PRD.md, HLD.md, LLD.md, SECURITY.md

## 1. Design principles

1. Clarity first: one headline, one summary, one source link per story.
2. Trust visible: credibility and source are always shown.
3. Calm reading: restrained colour, generous spacing, no autoplay or pop-ups.
4. Accessible by default: WCAG 2.1 AA for all pages.
5. Share in one step.

## 2. Information architecture

```
Home (Dashboard)
  Categories
    Category page
  Story (Article details)
    Share sheet
Settings
Sign in
Operator (health view, restricted)
```

Navigation: top bar with logo, Dashboard, Categories menu, Settings, and sign-in. On narrow screens the categories and settings collapse into a menu button.

## 3. Key screens

### 3.1 Dashboard
- Header: title "Today in AI and robotics", date and last-updated time.
- Top stories: list of story cards ordered by importance.
- Story card: category label, credibility badge (High, Medium, Low), headline, one-line summary, source name, time since published, duplicate count ("also reported by 3 sources").
- Actions on card: open, share.
- Filter bar: category chips and date range select (24 hours, 7 days, 30 days).

### 3.2 Category page
- Same card layout as dashboard, filtered to one category.
- Credibility filter (All, Medium and above, High only).
- Infinite list replaced by "Load more" button for accessibility.

### 3.3 Article details
- Headline, category, credibility badge with a tooltip explaining the rating.
- Summary section (approximately 80 words).
- Impact section and opportunity section, each under its own heading.
- Sources section: list of duplicate sources with links, showing source name, tier label and published time.
- "Read original" primary button, opening the source in a new tab with a visible "opens in new tab" label.
- Share section: WhatsApp, LinkedIn, Facebook and Copy link buttons.
- A note that summaries are AI-generated and may contain errors, with a link to the original.

### 3.4 Share sheet
- Opens as a dialog on desktop and as a bottom sheet on mobile.
- Buttons with icon and text label. Copy link shows a confirmation message in a live region.
- Escape closes the dialog and returns focus to the trigger.

### 3.5 Settings
- Preferred categories (checkboxes), default date range (radio group), display density (radio group).
- Save button; changes are announced after saving.
- Sign-out button.

### 3.6 Sign in
- Email field, "Send sign-in link" button, and a neutral confirmation message that does not reveal whether the address exists.

### 3.7 Operator health (restricted)
- Table of sources with status, last run time and last result.
- Manual "Run ingest" button per source with confirmation.

### 3.8 AI Pulse
- Homepage: a preview card above the filters (label "Today's Edition", introduction, top three headlines, reading time, streak, "Read Today's Briefing").
- `/pulse`: editorial masthead ("N stories. M minutes. Stay ahead."), date, edition number and reading time; the introduction; numbered story sections with source link and "why it matters"; the Daily AI Challenge (radio group, result announced in a live region, correct/incorrect shown with text and symbols, not colour alone); the reading streak with a 14-day indicator and a note that it is stored on this device only; previous/next edition links and an archive list.
- Serif headlines, hairline rules and one accent colour, no decorative effects; it follows the light/dark tokens and `prefers-reduced-motion`.

## 4. Visual design

### 4.1 Colour
- Neutral base for surfaces and text. Ensure text contrast of at least 4.5:1 against its background.
- One accent colour for primary actions and links.
- Credibility badges use colour plus text label and icon, never colour alone:
  - High: solid mark, text "High credibility"
  - Medium: half mark, text "Medium credibility"
  - Low: outline mark, text "Low credibility"
- Category labels use a small set of neutral tints; no more than six category colours, each with a text label.
- Support light and dark themes; follow the operating system setting by default with a manual toggle.

### 4.2 Typography
- One sans-serif family for interface and body text; a single display weight for headlines.
- Body text 16 px minimum, line-height 1.6.
- Headlines 24 px on cards, 32 px on article details.
- Minimum text size 14 px for metadata.

### 4.3 Spacing and layout
- 4 px base unit; card padding 16 px (comfortable) or 12 px (compact).
- Maximum reading width 68 characters for summaries.
- Desktop: two-column dashboard with a sidebar for filters at 1024 px and above.
- Tablet and mobile: single column, 16 px side margins from 360 px upward.

### 4.4 Iconography
- Single icon set with consistent stroke width.
- Share brand icons used only inside the share sheet, following each platform's guidelines.

## 5. Interaction and motion

- No autoplay, no carousels that move without user action.
- Hover and focus states visible on every interactive element.
- Loading states use skeleton placeholders with reduced-motion fallbacks.
- Honour `prefers-reduced-motion`; disable transitions when set.
- Page transitions limited to fade of 150 ms.

## 6. Content guidelines

- Headlines: keep the source's wording where reasonable; do not invent headlines.
- Summaries: plain language, no hype, state uncertainty where sources disagree.
- Always label AI-generated text.
- Dates: relative for under 48 hours ("3 hours ago"), absolute otherwise, in the reader's time zone.
- Numbers: use digits for counts and percentages.
- Error messages: say what happened and what to do next.

## 7. Accessibility

- Semantic landmarks: header, nav, main, footer.
- Heading order: one h1 per page; no skipped levels.
- Keyboard: all actions reachable by Tab, visible focus ring with 3:1 contrast, skip link to main content.
- Targets: at least 44 by 44 px on touch devices.
- Images and icons: decorative items hidden from assistive technology; meaningful icons have labels.
- Forms: visible labels, error messages linked with `aria-describedby`, errors announced politely.
- Live regions for status messages such as "Link copied" and "Settings saved".
- Tested with screen readers (VoiceOver, NVDA) and keyboard-only use before each release.

## 8. Components

| Component | Variants | Notes |
|---|---|---|
| Story card | default, compact, featured | Shows credibility and duplicate count |
| Credibility badge | high, medium, low | Icon + text, tooltip explains the rating |
| Category chip | selected, default | Toggle button with aria-pressed |
| Button | primary, secondary, text, icon | Minimum 44 px target on touch |
| Share button | per platform | Icon + label |
| Dialog | share, confirm | Focus trap, Escape to close |
| Toast | success, error | Auto-dismiss after 5 s, does not hide content |
| Empty state | no stories, no results | Explains the reason and offers a reset action |

## 9. States and edge cases

- No stories yet: message with date and link to categories.
- Source outage: banner "Some sources are temporarily unavailable" with last-updated time.
- Story flagged for review: not shown to readers; operator sees it in health view.
- Very long titles: wrap to three lines, then truncate with ellipsis; full title on article page.
- Slow network: show cached content with a refresh control.
- Offline: show last loaded content with an offline notice.

## 10. Design handoff

- Tokens (colour, type, spacing) are defined once in a design tokens file and consumed by the frontend.
- Each component documented with states and accessibility notes before development.
- Design reviews use the accessibility checklist in section 7.

## 11. Open design questions

- Whether to show a daily digest email in v1 (currently out of scope).
- Whether the dashboard should show a "what changed since last visit" panel.
