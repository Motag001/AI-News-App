/*
 * AI Pulse reading streak. Everything lives in this browser's localStorage under one key; nothing is sent
 * to the server. Dates are the visitor's local calendar dates (YYYY-MM-DD). Clearing browser data resets it.
 */
(function (root) {
  "use strict";

  var KEY = "aiPulse.v1";
  var MAX_DAYS = 730;
  var MAX_RESULTS = 60;

  function pad(value) {
    return value < 10 ? "0" + value : String(value);
  }

  function localDateKey(date) {
    var d = date || new Date();
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }

  function parseKey(key) {
    var parts = key.split("-");
    return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  }

  function addDays(key, amount) {
    var date = parseKey(key);
    date.setDate(date.getDate() + amount);
    return localDateKey(date);
  }

  function isKey(value) {
    return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
  }

  function emptyState() {
    return { v: 1, days: [], results: {} };
  }

  function load(storage) {
    try {
      var parsed = JSON.parse(storage.getItem(KEY) || "null");
      if (!parsed || parsed.v !== 1 || !Array.isArray(parsed.days)) return emptyState();
      var days = parsed.days.filter(isKey);
      var results = {};
      Object.keys(parsed.results || {}).forEach(function (date) {
        var entry = parsed.results[date];
        if (isKey(date) && entry && Number.isInteger(entry.choice) && typeof entry.correct === "boolean") {
          results[date] = { choice: entry.choice, correct: entry.correct };
        }
      });
      return { v: 1, days: Array.from(new Set(days)).sort(), results: results };
    } catch (error) {
      return emptyState();
    }
  }

  function save(storage, state) {
    try {
      var days = state.days.slice(-MAX_DAYS);
      var dates = Object.keys(state.results).sort().slice(-MAX_RESULTS);
      var results = {};
      dates.forEach(function (date) { results[date] = state.results[date]; });
      storage.setItem(KEY, JSON.stringify({ v: 1, days: days, results: results }));
      return true;
    } catch (error) {
      return false; // storage full or blocked: the page still works, the streak just is not remembered
    }
  }

  /** Consecutive active days ending today, or ending yesterday if today is not done yet. */
  function currentStreak(days, todayKey) {
    var set = new Set(days);
    var cursor = set.has(todayKey) ? todayKey : addDays(todayKey, -1);
    var count = 0;
    while (set.has(cursor)) {
      count += 1;
      cursor = addDays(cursor, -1);
    }
    return count;
  }

  function longestStreak(days) {
    var sorted = Array.from(new Set(days)).sort();
    var best = 0;
    var run = 0;
    var previous = null;
    sorted.forEach(function (key) {
      run = previous !== null && addDays(previous, 1) === key ? run + 1 : 1;
      best = Math.max(best, run);
      previous = key;
    });
    return best;
  }

  /** The last `count` local days, oldest first, flagged active or not. */
  function recentActivity(days, todayKey, count) {
    var set = new Set(days);
    var out = [];
    for (var i = (count || 14) - 1; i >= 0; i -= 1) {
      var key = addDays(todayKey, -i);
      out.push({ date: key, active: set.has(key) });
    }
    return out;
  }

  /** Mark a day complete. Safe to call repeatedly: a day only ever counts once. */
  function recordVisit(storage, todayKey) {
    var state = load(storage);
    if (state.days.indexOf(todayKey) === -1) {
      state.days.push(todayKey);
      state.days.sort();
      save(storage, state);
    }
    return state;
  }

  /** Store the first answer for an edition; later attempts cannot overwrite it. */
  function recordResult(storage, editionDate, choice, correct) {
    var state = load(storage);
    if (!state.results[editionDate]) {
      state.results[editionDate] = { choice: choice, correct: correct };
      save(storage, state);
    }
    return state.results[editionDate];
  }

  function getResult(storage, editionDate) {
    return load(storage).results[editionDate] || null;
  }

  function summary(storage, todayKey) {
    var state = load(storage);
    return {
      current: currentStreak(state.days, todayKey),
      longest: longestStreak(state.days),
      doneToday: state.days.indexOf(todayKey) !== -1,
      recent: recentActivity(state.days, todayKey, 14),
    };
  }

  var api = {
    KEY: KEY, localDateKey: localDateKey, addDays: addDays, load: load, save: save,
    currentStreak: currentStreak, longestStreak: longestStreak, recentActivity: recentActivity,
    recordVisit: recordVisit, recordResult: recordResult, getResult: getResult, summary: summary,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PulseStreak = api;
})(typeof window !== "undefined" ? window : globalThis);
