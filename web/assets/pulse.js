/* AI Pulse: homepage preview and the daily briefing page. Uses element() and categoryClass() from app.js. */

function pulseStorage() {
  try {
    return window.localStorage;
  } catch {
    return null; // blocked storage: everything still renders, the streak is simply not remembered
  }
}

function pulseDate(value, options) {
  return new Intl.DateTimeFormat(undefined, { timeZone: "UTC", ...options }).format(new Date(`${value}T00:00:00Z`));
}

function pulseLongDate(value) {
  return pulseDate(value, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
}

function publishedDate(value) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
}

function pulseMark() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "pulse-glyph");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("points", "1,13 6,13 9,4 14,20 17,11 23,11");
  svg.append(line);
  return svg;
}

function pulseBrand() {
  const brand = element("span", "pulse-brand");
  brand.append(pulseMark(), element("span", "", "AI Pulse"));
  return brand;
}

async function fetchPulse(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = new Error(response.status === 404 ? "not-found" : "failed");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function streakSummary() {
  return PulseStreak.summary(pulseStorage(), PulseStreak.localDateKey());
}

function streakChip(summary) {
  const chip = element("span", "streak-chip");
  chip.append(element("strong", "", String(summary.current)), document.createTextNode(" day streak"));
  chip.title = `Longest streak: ${summary.longest}`;
  return chip;
}

/* ------------------------------------------------------------------ homepage preview */

async function renderPulsePreview(slot) {
  let result;
  try {
    result = await fetchPulse("/api/v1/pulse/today");
  } catch {
    return; // the briefing is an extra; the news feed still works without it
  }
  const edition = result.edition;
  if (!edition) return;

  const summary = streakSummary();
  const section = element("section", "pulse-preview");
  section.setAttribute("aria-labelledby", "pulse-preview-title");

  const head = element("div", "pulse-preview-head");
  const titleRow = element("div", "pulse-preview-title-row");
  const title = element("h2", "pulse-preview-title");
  title.id = "pulse-preview-title";
  title.append(pulseBrand());
  titleRow.append(title, element("span", "pulse-label", result.status === "current" ? "Today's Edition" : "Latest Edition"));
  head.append(titleRow, element("span", "pulse-preview-date", `${pulseDate(edition.date, { month: "short", day: "numeric" })} · No. ${edition.edition_number}`));

  const intro = element("p", "pulse-preview-intro", edition.introduction);
  const list = element("ol", "pulse-preview-list");
  edition.stories.slice(0, 3).forEach((story) => {
    const item = element("li", "");
    const link = element("a", "", story.headline);
    link.href = `/pulse/${edition.date}#story-${story.order}`;
    item.append(link, element("span", `category-tag ${categoryClass(story.category)}`, story.category));
    list.append(item);
  });

  const foot = element("div", "pulse-preview-foot");
  const meta = element("p", "pulse-preview-meta", `${edition.story_count} ${edition.story_count === 1 ? "story" : "stories"} · ${edition.reading_time_minutes} min read`);
  const cta = element("a", "button button-primary", "Read Today's Briefing");
  cta.href = `/pulse/${edition.date}`;
  foot.append(meta, streakChip(summary), cta);

  section.append(head, intro, list, foot);
  slot.append(section);
}

/* ------------------------------------------------------------------ briefing page */

async function renderPulsePage(requestedDate) {
  const main = document.querySelector("#main-content");
  main.replaceChildren(element("p", "notice container", "Loading the briefing…"));
  let result;
  try {
    result = requestedDate
      ? { status: "archive", edition: await fetchPulse(`/api/v1/pulse/${encodeURIComponent(requestedDate)}`) }
      : await fetchPulse("/api/v1/pulse/today");
  } catch (error) {
    main.replaceChildren(pulseMessage(
      error.status === 404 ? "This edition does not exist" : "The briefing could not be loaded",
      error.status === 404 ? "Check the date, or open the latest edition." : "Please refresh the page in a moment.",
    ));
    return;
  }
  if (!result.edition) {
    main.replaceChildren(pulseMessage("No briefing yet", result.message || "The first edition has not been published."));
    return;
  }
  const edition = result.edition;
  document.title = `AI Pulse No. ${edition.edition_number} · AI News Platform`;
  const isLatest = !edition.next_date;

  const page = element("div", "pulse-page");
  page.append(pulseMasthead(edition, result));
  const body = element("div", "container pulse-body");
  if (result.status === "previous" && result.message) body.append(element("p", "pulse-notice", result.message));
  if (edition.mode === "extractive") {
    body.append(element("p", "pulse-notice", "Automated edition: the text below is taken directly from each source. AI-written summaries are switched off."));
  }
  const intro = element("p", "pulse-intro", edition.introduction);
  body.append(intro);

  const stories = element("ol", "pulse-stories");
  edition.stories.forEach((story) => stories.append(pulseStory(story)));
  body.append(stories);

  const end = element("div", "pulse-end");
  end.setAttribute("aria-hidden", "true");
  body.append(end);

  const lower = element("div", "pulse-lower");
  lower.append(pulseChallenge(edition, isLatest), pulseStreakPanel());
  body.append(lower, pulseNavigation(edition));
  page.append(body);
  main.replaceChildren(page);

  if (isLatest) trackBriefingCompletion(end);
  if (window.location.hash) {
    const target = document.getElementById(window.location.hash.slice(1));
    if (target) target.scrollIntoView();
  }
  loadPulseHistory(edition.date);
}

function pulseMessage(title, text) {
  const box = element("div", "container pulse-message");
  box.append(element("h1", "", title), element("p", "", text));
  const link = element("a", "button button-primary", "Back to the news feed");
  link.href = "/";
  box.append(link);
  return box;
}

function pulseMasthead(edition, result) {
  const masthead = element("header", "pulse-masthead");
  const inner = element("div", "container");
  const top = element("div", "pulse-masthead-top");
  top.append(pulseBrand(), element("span", "pulse-label", result.status === "current" ? "Today's Edition" : result.status === "archive" ? "Archive" : "Latest Edition"));
  const minutes = edition.reading_time_minutes;
  const count = edition.story_count;
  const heading = element("h1", "pulse-title", `${count} ${count === 1 ? "story" : "stories"}. ${minutes} ${minutes === 1 ? "minute" : "minutes"}. Stay ahead.`);
  const meta = element("p", "pulse-meta");
  const time = element("time", "", pulseLongDate(edition.date));
  time.dateTime = edition.date;
  meta.append(time, element("span", "", `Edition No. ${edition.edition_number}`), element("span", "", `${count} ${count === 1 ? "story" : "stories"}`), element("span", "", `${minutes} min read`));
  inner.append(top, heading, meta);
  masthead.append(inner);
  return masthead;
}

function pulseStory(story) {
  const item = element("li", "pulse-story");
  item.id = `story-${story.order}`;
  const article = element("article", `pulse-story-card ${categoryClass(story.category)}`);
  article.setAttribute("aria-labelledby", `story-${story.order}-title`);
  const number = element("span", "pulse-number", String(story.order).padStart(2, "0"));
  number.setAttribute("aria-hidden", "true");
  const content = element("div", "pulse-story-content");
  const meta = element("p", "pulse-story-meta");
  meta.append(element("span", "category-tag", story.category), element("span", "", `${story.source_name} · ${publishedDate(story.published_at)}`));
  const headline = element("h2", "pulse-headline", story.headline);
  headline.id = `story-${story.order}-title`;
  content.append(meta, headline, element("p", "pulse-summary", story.summary));
  if (story.why_it_matters) {
    const why = element("div", "pulse-why");
    why.append(element("h3", "", "Why it matters"), element("p", "", story.why_it_matters));
    content.append(why);
  }
  const link = element("a", "pulse-source-link");
  try {
    link.href = safeExternalUrl(story.source_url);
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.append(document.createTextNode(`Read the original at ${story.source_name}`), element("span", "visually-hidden", " (opens in new tab)"));
    link.append(element("span", "", " ↗"));
    link.lastChild.setAttribute("aria-hidden", "true");
    content.append(link);
  } catch {
    content.append(element("p", "notice", "The original link is unavailable."));
  }
  article.append(number, content);
  item.append(article);
  return item;
}

/* The briefing counts as read once the reader reaches its end (latest edition only). */
function trackBriefingCompletion(sentinel) {
  const mark = () => {
    PulseStreak.recordVisit(pulseStorage(), PulseStreak.localDateKey());
    refreshStreakPanel();
  };
  if (!("IntersectionObserver" in window)) return mark();
  const observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      observer.disconnect();
      mark();
    }
  });
  observer.observe(sentinel);
}

/* ------------------------------------------------------------------ challenge */

function pulseChallenge(edition, countsForStreak) {
  const challenge = edition.challenge;
  const section = element("section", "pulse-challenge");
  section.setAttribute("aria-labelledby", "challenge-title");
  const title = element("h2", "", "Daily AI Challenge");
  title.id = "challenge-title";
  section.append(title);
  if (challenge.question_type === "general") {
    section.append(element("p", "pulse-challenge-kind", "General AI knowledge question, not drawn from today's stories."));
  }

  const form = element("form", "pulse-challenge-form");
  const fieldset = element("fieldset", "");
  fieldset.append(element("legend", "", challenge.question));
  const choices = [];
  challenge.options.forEach((option, index) => {
    const label = element("label", "pulse-option");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "pulse-answer";
    input.value = String(index);
    input.required = true;
    label.append(input, element("span", "", option));
    choices.push({ label, input });
    fieldset.append(label);
  });
  const submit = element("button", "button button-primary", "Check answer");
  submit.type = "submit";
  const result = element("div", "pulse-result");
  result.setAttribute("role", "status");
  result.setAttribute("aria-live", "polite");
  result.tabIndex = -1;
  form.append(fieldset, submit);
  section.append(form, result);

  function showResult(choice, answer) {
    choices.forEach(({ label, input }, index) => {
      input.disabled = true;
      input.checked = index === choice;
      label.classList.toggle("is-correct", index === answer.correct_index);
      label.classList.toggle("is-wrong", index === choice && !answer.correct);
    });
    submit.hidden = true;
    result.replaceChildren(
      element("p", `pulse-verdict ${answer.correct ? "correct" : "incorrect"}`, answer.correct ? "Correct" : "Not quite"),
      element("p", "", `Correct answer: ${answer.correct_answer}`),
      element("p", "pulse-explanation", answer.explanation),
    );
  }

  async function ask(choice) {
    return fetchPulse(`/api/v1/pulse/${encodeURIComponent(edition.date)}/challenge/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ choice }),
    });
  }

  const earlier = PulseStreak.getResult(pulseStorage(), edition.date);
  if (earlier) {
    // Already answered on this device: show the recorded choice; it cannot be changed.
    ask(earlier.choice).then((answer) => showResult(earlier.choice, answer)).catch(() => {
      result.textContent = "You have already answered today's challenge on this device.";
      choices.forEach(({ input }) => { input.disabled = true; });
      submit.hidden = true;
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const picked = form.querySelector("input[name='pulse-answer']:checked");
    if (!picked) return;
    const choice = Number(picked.value);
    submit.disabled = true;
    try {
      const answer = await ask(choice);
      const stored = PulseStreak.recordResult(pulseStorage(), edition.date, choice, answer.correct);
      showResult(stored.choice, stored.choice === choice ? answer : await ask(stored.choice));
      if (countsForStreak) {
        PulseStreak.recordVisit(pulseStorage(), PulseStreak.localDateKey());
        refreshStreakPanel();
      }
      result.focus();
    } catch {
      submit.disabled = false;
      result.textContent = "The answer could not be checked. Please try again.";
    }
  });
  return section;
}

/* ------------------------------------------------------------------ streak panel */

function pulseStreakPanel() {
  const panel = element("section", "pulse-streak");
  panel.id = "pulse-streak";
  panel.setAttribute("aria-labelledby", "streak-title");
  fillStreakPanel(panel);
  return panel;
}

function fillStreakPanel(panel) {
  const summary = streakSummary();
  const title = element("h2", "", "Reading streak");
  title.id = "streak-title";
  const figures = element("dl", "pulse-streak-figures");
  for (const [label, value] of [["Current", summary.current], ["Longest", summary.longest]]) {
    const group = element("div", "");
    group.append(element("dt", "", label), element("dd", "", `${value} ${value === 1 ? "day" : "days"}`));
    figures.append(group);
  }
  const days = element("ul", "pulse-days");
  days.setAttribute("aria-label", "Activity over the last 14 days");
  for (const day of summary.recent) {
    const dot = element("li", `pulse-day${day.active ? " active" : ""}`);
    const name = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(`${day.date}T12:00:00`));
    dot.title = `${name}: ${day.active ? "read" : "no activity"}`;
    dot.append(element("span", "visually-hidden", `${name}: ${day.active ? "read" : "no activity"}`));
    days.append(dot);
  }
  const note = element("p", "pulse-streak-note", summary.doneToday
    ? "Today is complete. Come back tomorrow to keep your streak."
    : "Reach the end of the briefing or answer the challenge to count today.");
  const privacy = element("p", "pulse-streak-privacy", "Streaks are stored only in this browser. They are specific to this device and reset if you clear your browser data.");
  panel.replaceChildren(title, figures, days, note, privacy);
}

function refreshStreakPanel() {
  const panel = document.querySelector("#pulse-streak");
  if (panel) fillStreakPanel(panel);
}

/* ------------------------------------------------------------------ navigation and archive */

function pulseNavigation(edition) {
  const nav = element("nav", "pulse-edition-nav");
  nav.setAttribute("aria-label", "Other editions");
  const previous = element("a", "button", edition.previous_date ? `← ${pulseDate(edition.previous_date, { month: "short", day: "numeric" })}` : "← Earlier");
  const next = element("a", "button", edition.next_date ? `${pulseDate(edition.next_date, { month: "short", day: "numeric" })} →` : "Latest →");
  if (edition.previous_date) previous.href = `/pulse/${edition.previous_date}`;
  else { previous.setAttribute("aria-disabled", "true"); previous.classList.add("is-disabled"); }
  if (edition.next_date) next.href = `/pulse/${edition.next_date}`;
  else { next.setAttribute("aria-disabled", "true"); next.classList.add("is-disabled"); }
  const archive = element("div", "pulse-archive");
  archive.id = "pulse-archive";
  nav.append(previous, next);
  const wrap = element("div", "pulse-edition-wrap");
  wrap.append(nav, archive);
  return wrap;
}

async function loadPulseHistory(currentDate) {
  const archive = document.querySelector("#pulse-archive");
  if (!archive) return;
  try {
    const items = await fetchPulse("/api/v1/pulse/history?limit=14");
    if (items.length < 2) return;
    const details = element("details", "");
    details.append(element("summary", "", "Past editions"));
    const list = element("ul", "");
    for (const item of items) {
      const entry = element("li", "");
      const link = element("a", "", `${pulseDate(item.date, { month: "short", day: "numeric" })} · No. ${item.edition_number}`);
      link.href = `/pulse/${item.date}`;
      if (item.date === currentDate) link.setAttribute("aria-current", "page");
      entry.append(link);
      if (item.lead_headline) entry.append(element("span", "", item.lead_headline));
      list.append(entry);
    }
    details.append(list);
    archive.append(details);
  } catch { /* the archive is optional */ }
}
