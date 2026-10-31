const categories = ["AI models", "Robotics", "Research", "Policy", "Industry"];
const params = new URLSearchParams(window.location.search);
let nextCursor = null;
let currentFilters = {};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatTime(value) {
  const date = new Date(value);
  const hours = (Date.now() - date.getTime()) / 3600000;
  if (hours >= 0 && hours < 48) {
    if (hours < 1) return "Less than an hour ago";
    const whole = Math.floor(hours);
    return `${whole} ${whole === 1 ? "hour" : "hours"} ago`;
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

const CATEGORY_STYLE = {
  "AI models": { cls: "cat-models", glyph: "✦" },
  "Robotics": { cls: "cat-robotics", glyph: "⚙" },
  "Research": { cls: "cat-research", glyph: "❖" },
  "Policy": { cls: "cat-policy", glyph: "⚖" },
  "Industry": { cls: "cat-industry", glyph: "▲" },
};

function categoryClass(category) {
  return (CATEGORY_STYLE[category] || CATEGORY_STYLE.Industry).cls;
}

function placeholder(category) {
  const box = element("div", `story-placeholder ${categoryClass(category)}`);
  box.setAttribute("aria-hidden", "true");
  box.append(element("span", "placeholder-glyph", (CATEGORY_STYLE[category] || CATEGORY_STYLE.Industry).glyph));
  return box;
}

/** Feed-provided image hot-linked with no referrer; falls back to a category placeholder if it fails. */
function storyMedia(story, className = "story-media") {
  const wrapper = element("div", className);
  wrapper.append(placeholder(story.category));
  if (story.image_url) {
    const image = document.createElement("img");
    image.alt = "";
    image.loading = "lazy";
    image.decoding = "async";
    image.referrerPolicy = "no-referrer";
    image.src = story.image_url;
    image.addEventListener("error", () => image.remove());
    wrapper.append(image);
  }
  return wrapper;
}

function relativeUpdate(value) {
  if (!value) return "waiting for first update";
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.round(minutes / 60)} h ago`;
}

const CREDIBILITY_MARKS = { high: "●", medium: "◐", low: "○" };

function credibilityBadge(label) {
  const badge = element("span", `credibility ${label.toLowerCase()}`);
  const mark = element("span", "", CREDIBILITY_MARKS[label.toLowerCase()]);
  mark.setAttribute("aria-hidden", "true");
  badge.append(mark, document.createTextNode(` ${label} credibility`));
  return badge;
}

function makeCategoryNav(selected) {
  const nav = element("nav", "category-nav");
  nav.setAttribute("aria-label", "News categories");
  const allLink = element("a", "", "All stories");
  allLink.href = "/";
  if (!selected) allLink.setAttribute("aria-current", "page");
  nav.append(allLink);
  for (const category of categories) {
    const link = element("a", "", category);
    link.href = `/category/${encodeURIComponent(category)}`;
    if (category === selected) link.setAttribute("aria-current", "page");
    nav.append(link);
  }
  return nav;
}

function makeStoryCard(story, featured = false) {
  const card = element("article", `story-card ${categoryClass(story.category)}${featured ? " featured" : ""}`);
  const titleHref = `/story/${encodeURIComponent(story.id)}`;
  card.append(storyMedia(story));

  const body = element("div", "story-body");
  const meta = element("div", "story-meta");
  meta.append(element("span", "category-tag", story.category));
  meta.append(credibilityBadge(story.credibility_label));
  meta.append(element("span", "story-time", formatTime(story.published_at)));

  const title = element(featured ? "h2" : "h3", "story-title");
  const titleLink = element("a", "", story.title);
  titleLink.href = titleHref;
  title.append(titleLink);

  const summary = element("p", "story-summary", story.summary || "The source did not provide an excerpt. Open the story for the original link.");
  const footer = element("div", "story-footer");
  const others = story.source_count - 1;
  footer.append(element("span", "story-source", others > 0
    ? `${story.source_name} · +${others} more`
    : story.source_name));
  const detail = element("a", "read-link", "Read story →");
  detail.href = titleHref;
  footer.append(detail);
  body.append(meta, title, summary, footer);
  card.append(body);
  return card;
}

async function loadStoryList(container, filters, cursor = 0) {
  const query = new URLSearchParams({
    date_range: filters.date_range,
    min_credibility: filters.min_credibility,
    sort: filters.sort,
    cursor: String(cursor),
    limit: "20",
  });
  if (filters.category) query.set("category", filters.category);
  if (filters.q) query.set("q", filters.q);
  const response = await fetch(`/api/v1/stories?${query}`);
  if (!response.ok) throw new Error("Stories could not be loaded. Refresh the page to try again.");
  const result = await response.json();

  if (cursor === 0) {
    container.replaceChildren();
    nextCursor = result.next_cursor;
  } else {
    nextCursor = result.next_cursor;
  }
  const lead = result.items.slice(0, 20).findIndex((story) => story.image_url);
  if (cursor === 0 && lead > 0) result.items.unshift(...result.items.splice(lead, 1)); // lead with a story that has a picture
  result.items.forEach((story, index) => {
    const featured = cursor === 0 && index === 0 && currentFilters.sort === "importance" && !currentFilters.q;
    container.append(makeStoryCard(story, featured));
  });
  const counter = document.querySelector("#result-count");
  if (counter) counter.textContent = `${result.total} ${result.total === 1 ? "story" : "stories"}`;

  const empty = document.querySelector("#empty-state");
  if (empty) empty.hidden = result.items.length > 0 || cursor > 0;
  const more = document.querySelector("#load-more");
  if (more) more.hidden = !nextCursor;
}

function savedSettings() {
  try {
    return JSON.parse(localStorage.getItem("readerSettings") || "{}");
  } catch {
    return {};
  }
}

function renderDashboard(category = null) {
  const defaults = savedSettings();
  if (!params.has("date_range") && ["24h", "7d", "30d"].includes(defaults.date_range)) {
    params.set("date_range", defaults.date_range);
  }
  const main = document.querySelector("#main-content");
  main.replaceChildren();
  document.title = `${category || "Dashboard"} · AI News Platform`;
  const hero = element("section", "hero");
  const heroInner = element("div", "container hero-inner");
  heroInner.append(element("p", "eyebrow", category ? "Category" : "Live from vetted sources"));
  heroInner.append(element("h1", "page-title", category || "Today in AI and robotics"));
  heroInner.append(element("p", "page-intro", "Latest AI and robotics stories, ranked by importance and linked to the original source."));
  const stats = element("ul", "hero-stats");
  heroInner.append(stats);
  heroInner.append(makeCategoryNav(category));
  hero.append(heroInner);
  main.append(hero);
  const body = element("div", "container page-body");
  main.append(body);
  fetch("/api/v1/health").then((response) => response.json()).then((health) => {
    for (const text of [`${health.sources_healthy}/${health.sources} sources live`, `Updated ${relativeUpdate(health.last_checked_at)}`]) {
      stats.append(element("li", "", text));
    }
  }).catch(() => {});

  const toolbar = element("form", "toolbar");
  toolbar.id = "filters";
  toolbar.setAttribute("aria-label", "Filter stories");
  const search = field("Search stories", "q", "search", params.get("q") || "");
  search.querySelector("input").placeholder = "Try “robotics”";
  search.querySelector("input").maxLength = 120;
  search.classList.add("search-field");
  toolbar.append(search);
  toolbar.append(selectField("Date range", "date_range", [
    ["24h", "Past 24 hours"], ["7d", "Past 7 days"], ["30d", "Past 30 days"],
  ], params.get("date_range") || "7d"));
  toolbar.append(selectField("Credibility", "min_credibility", [
    ["all", "All levels"], ["medium", "Medium and above"], ["high", "High only"],
  ], params.get("min_credibility") || "all"));
  toolbar.append(selectField("Sort by", "sort", [
    ["importance", "Importance"], ["recent", "Most recent"],
  ], params.get("sort") || "importance"));
  const apply = element("button", "button button-primary", "Apply filters");
  apply.type = "submit";
  toolbar.append(apply);
  toolbar.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(toolbar);
    const next = new URLSearchParams();
    for (const key of ["q", "date_range", "min_credibility", "sort"]) {
      const value = String(formData.get(key) || "").trim();
      if (value) next.set(key, value);
    }
    window.history.replaceState({}, "", `${window.location.pathname}?${next}`);
    initialiseFeed(category, Object.fromEntries(next.entries()));
  });
  body.append(toolbar);

  const heading = element("div", "feed-heading");
  heading.append(element("h2", "", "Top stories"));
  heading.append(element("span", "result-count", "Loading stories…"));
  heading.querySelector(".result-count").id = "result-count";
  body.append(heading);
  const list = element("div", "story-list");
  list.id = "story-list";
  list.setAttribute("aria-live", "polite");
  body.append(list);
  const empty = element("div", "empty-state", "No stories match these filters. If the app has just started, sources are still being fetched; refresh in a minute, or try another date range.");
  empty.id = "empty-state";
  empty.hidden = true;
  body.append(empty);
  const more = element("button", "button load-more", "Load more stories");
  more.id = "load-more";
  more.hidden = true;
  more.addEventListener("click", async () => {
    more.disabled = true;
    try {
      await loadStoryList(list, currentFilters, Number(nextCursor));
    } catch (error) {
      showError(error.message);
    } finally {
      more.disabled = false;
    }
  });
  body.append(more);
  initialiseFeed(category, Object.fromEntries(params.entries()));
}

function field(label, name, type, value) {
  const wrapper = element("div", "field");
  const inputLabel = element("label", "", label);
  inputLabel.htmlFor = name;
  const input = document.createElement("input");
  input.id = name;
  input.name = name;
  input.type = type;
  input.value = value;
  wrapper.append(inputLabel, input);
  return wrapper;
}

function selectField(label, name, options, selected) {
  const wrapper = element("div", "field");
  const selectLabel = element("label", "", label);
  selectLabel.htmlFor = name;
  const select = document.createElement("select");
  select.id = name;
  select.name = name;
  for (const [value, text] of options) {
    const option = element("option", "", text);
    option.value = value;
    option.selected = value === selected;
    select.append(option);
  }
  wrapper.append(selectLabel, select);
  return wrapper;
}

async function initialiseFeed(category, filters) {
  currentFilters = {
    date_range: ["24h", "7d", "30d"].includes(filters.date_range) ? filters.date_range : "7d",
    min_credibility: ["all", "medium", "high"].includes(filters.min_credibility) ? filters.min_credibility : "all",
    sort: ["importance", "recent"].includes(filters.sort) ? filters.sort : "importance",
    q: (filters.q || "").slice(0, 120),
    category,
  };
  try {
    await loadStoryList(document.querySelector("#story-list"), currentFilters);
  } catch (error) {
    showError(error.message);
  }
}

async function renderStory(id) {
  const main = document.querySelector("#main-content");
  main.replaceChildren(element("p", "notice container", "Loading story…"));
  try {
    const response = await fetch(`/api/v1/stories/${encodeURIComponent(id)}`);
    if (!response.ok) throw new Error(response.status === 404 ? "This story could not be found." : "The story could not be loaded.");
    const story = await response.json();
    const article = element("article", "article");
    article.append(storyMedia(story, "article-hero"));
    const meta = element("div", "story-meta");
    meta.append(element("span", "category-tag", story.category));
    meta.append(credibilityBadge(story.credibility_label));
    meta.append(element("span", "", formatTime(story.published_at)));
    article.append(meta, element("h1", "", story.title));
    document.title = `${story.title} · AI News Platform`;

    article.append(articleSection("Excerpt from the source", story.summary || "The source did not provide an excerpt."));
    if (story.impact) article.append(articleSection("Why it matters", story.impact));
    if (story.opportunity) article.append(articleSection("Opportunity", story.opportunity));

    const sourceSection = element("section", "article-section");
    sourceSection.append(element("h2", "", `Sources (${story.sources.length})`));
    const sourceList = element("ul", "source-list");
    for (const source of story.sources) {
      const item = element("li", "source-item");
      const link = element("a", "", source.name);
      try {
        link.href = safeExternalUrl(source.url);
      } catch {
        item.append(element("span", "source-note", "Source link unavailable: invalid URL."));
        sourceList.append(item);
        continue;
      }
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      item.append(link);
      item.append(element("span", "source-note", `Tier ${source.tier} · ${formatTime(source.published_at)}${source.author ? ` · ${source.author}` : ""} · opens in new tab`));
      sourceList.append(item);
    }
    sourceSection.append(sourceList);
    const primary = story.sources[0];
    if (primary) {
      try {
        const original = element("a", "button button-primary", "Read original (opens in new tab)");
        original.href = safeExternalUrl(primary.url);
        original.target = "_blank";
        original.rel = "noopener noreferrer";
        article.append(original);
      } catch { /* invalid source URL: the sources list already reports it */ }
    }
    article.append(sourceSection, shareActions(id));
    const attributions = [...new Set(story.sources.map((source) => source.attribution).filter(Boolean))];
    for (const text of attributions) article.append(element("p", "ai-note", text));
    article.append(element("p", "ai-note", "Excerpts are taken from the linked sources and are not AI-generated. Read the original before relying on them."));
    const shell = element("div", "container");
    shell.append(article);
    main.replaceChildren(shell);
  } catch (error) {
    main.replaceChildren(element("div", "empty-state container", error.message));
  }
}

function articleSection(title, text) {
  const section = element("section", "article-section");
  section.append(element("h2", "", title), element("p", "", text));
  return section;
}

function shareActions(id) {
  const section = element("section", "article-section");
  section.append(element("h2", "", "Share this story"));
  const actions = element("div", "share-actions");
  const status = element("p", "notice", "");
  status.id = "share-status";
  status.setAttribute("role", "status");
  fetch(`/api/v1/stories/${encodeURIComponent(id)}/share-links`)
    .then((response) => {
      if (!response.ok) throw new Error("Share links could not be loaded.");
      return response.json();
    })
    .then((links) => {
      for (const [key, label] of [["whatsapp", "WhatsApp"], ["linkedin", "LinkedIn"], ["facebook", "Facebook"]]) {
        const link = element("a", "button", label);
        link.href = links[key];
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.setAttribute("aria-label", `Share to ${label} (opens in new tab)`);
        actions.append(link);
      }
      const copy = element("button", "button", "Copy link");
      copy.type = "button";
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(links.copy);
          status.textContent = "Link copied.";
        } catch {
          status.textContent = `Copy was unavailable. Select and copy this link: ${links.copy}`;
        }
      });
      actions.append(copy);
    })
    .catch((error) => { status.textContent = error.message; });
  section.append(actions, status);
  return section;
}

function renderSettings() {
  const main = document.querySelector("#main-content");
  main.replaceChildren();
  const hero = element("section", "hero hero-small");
  const heroInner = element("div", "container hero-inner");
  heroInner.append(element("p", "eyebrow", "Your reading preferences"));
  heroInner.append(element("h1", "page-title", "Settings"));
  heroInner.append(element("p", "page-intro", "Set display preferences for this browser. Account sign-in and cross-device settings are not enabled yet."));
  hero.append(heroInner);
  const body = element("div", "container page-body");
  main.append(hero, body);
  const form = element("form", "settings-card");
  const stored = savedSettings();
  const group = element("fieldset", "settings-group");
  group.append(element("legend", "", "Preferred categories"));
  const checkList = element("div", "check-list");
  for (const category of categories) {
    const label = element("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = "categories";
    input.value = category;
    input.checked = (stored.categories || []).includes(category);
    label.append(input, document.createTextNode(category));
    checkList.append(label);
  }
  group.append(checkList);
  form.append(group);
  form.append(radioGroup("Default date range", "date_range", [
    ["24h", "24 hours"], ["7d", "7 days"], ["30d", "30 days"],
  ], stored.date_range || "7d"));
  form.append(radioGroup("Display density", "density", [
    ["comfortable", "Comfortable"], ["compact", "Compact"],
  ], stored.density || "comfortable"));
  const save = element("button", "button button-primary", "Save preferences");
  save.type = "submit";
  const message = element("p", "settings-message", "");
  message.setAttribute("role", "status");
  form.append(save, message);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(form);
    localStorage.setItem("readerSettings", JSON.stringify({
      categories: data.getAll("categories"),
      date_range: data.get("date_range"),
      density: data.get("density"),
    }));
    document.documentElement.dataset.density = String(data.get("density"));
    message.textContent = "Preferences saved in this browser.";
  });
  body.append(form);
}

function radioGroup(title, name, options, selected) {
  const group = element("fieldset", "settings-group");
  group.append(element("legend", "", title));
  const list = element("div", "radio-list");
  for (const [value, text] of options) {
    const label = element("label");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = name;
    input.value = value;
    input.checked = value === selected;
    label.append(input, document.createTextNode(text));
    list.append(label);
  }
  group.append(list);
  return group;
}

function showError(message) {
  const main = document.querySelector("#main-content");
  const alert = element("div", "empty-state", message);
  alert.setAttribute("role", "alert");
  main.prepend(alert);
}

function setupTheme() {
  const themeButton = document.querySelector("#theme-toggle");
  const savedTheme = localStorage.getItem("theme");
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;
  const activeTheme = document.documentElement.dataset.theme
    || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  themeButton.setAttribute("aria-pressed", String(activeTheme === "dark"));
  const prefs = savedSettings();
  if (["comfortable", "compact"].includes(prefs.density)) {
    document.documentElement.dataset.density = prefs.density;
  }
  const path = window.location.pathname;
  if (path === "/settings") document.querySelector("#nav-settings").setAttribute("aria-current", "page");
  else if (path === "/") document.querySelector("#nav-home").setAttribute("aria-current", "page");
  themeButton.addEventListener("click", () => {
    const currentTheme = document.documentElement.dataset.theme
      || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = nextTheme;
    localStorage.setItem("theme", nextTheme);
    themeButton.setAttribute("aria-pressed", String(nextTheme === "dark"));
  });
}

function safeExternalUrl(value) {
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error("A source link used an unsupported URL scheme.");
  }
  return url.href;
}

const pathname = decodeURIComponent(window.location.pathname);
setupTheme();
if (pathname === "/settings") {
  renderSettings();
} else if (pathname.startsWith("/story/")) {
  renderStory(pathname.slice("/story/".length));
} else {
  const category = pathname.startsWith("/category/") ? pathname.slice("/category/".length) : null;
  if (category && !categories.includes(category)) {
    document.querySelector("#main-content").append(element("div", "empty-state container", "Category not found."));
  } else {
    renderDashboard(category);
  }
}
