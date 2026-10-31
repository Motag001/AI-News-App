const test = require("node:test");
const assert = require("node:assert/strict");
const S = require("../../web/assets/streak.js");

class FakeStorage {
  constructor() { this.data = {}; }
  getItem(key) { return key in this.data ? this.data[key] : null; }
  setItem(key, value) { this.data[key] = String(value); }
}

test("current streak counts consecutive days ending today", () => {
  assert.equal(S.currentStreak(["2026-10-29", "2026-10-30", "2026-10-31"], "2026-10-31"), 3);
});

test("streak survives until the end of the next day (yesterday still counts)", () => {
  assert.equal(S.currentStreak(["2026-10-29", "2026-10-30"], "2026-10-31"), 2);
});

test("a missed day resets the current streak to zero", () => {
  assert.equal(S.currentStreak(["2026-10-28", "2026-10-29"], "2026-10-31"), 0);
});

test("streaks cross month and year boundaries", () => {
  assert.equal(S.currentStreak(["2026-12-30", "2026-12-31", "2027-01-01"], "2027-01-01"), 3);
  assert.equal(S.currentStreak(["2026-02-28", "2026-03-01"], "2026-03-01"), 2);
});

test("leap day is handled", () => {
  assert.equal(S.currentStreak(["2028-02-28", "2028-02-29", "2028-03-01"], "2028-03-01"), 3);
});

test("longest streak finds the best run regardless of order or duplicates", () => {
  const days = ["2026-10-10", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-03", "2026-10-11"];
  assert.equal(S.longestStreak(days), 3);
  assert.equal(S.longestStreak([]), 0);
});

test("recent activity returns 14 days, oldest first, flagging active ones", () => {
  const recent = S.recentActivity(["2026-10-31", "2026-10-25"], "2026-10-31", 14);
  assert.equal(recent.length, 14);
  assert.equal(recent[0].date, "2026-10-18");
  assert.equal(recent[13].date, "2026-10-31");
  assert.deepEqual(recent.filter((day) => day.active).map((day) => day.date), ["2026-10-25", "2026-10-31"]);
});

test("recording a visit twice on the same day counts once and persists", () => {
  const storage = new FakeStorage();
  S.recordVisit(storage, "2026-10-31");
  S.recordVisit(storage, "2026-10-31");
  const state = S.load(storage);
  assert.deepEqual(state.days, ["2026-10-31"]);
  // a new "page load" reads the same data back
  assert.equal(S.summary(storage, "2026-10-31").current, 1);
  assert.equal(S.summary(storage, "2026-10-31").doneToday, true);
});

test("consecutive days across sessions build the streak", () => {
  const storage = new FakeStorage();
  ["2026-10-29", "2026-10-30", "2026-10-31"].forEach((day) => S.recordVisit(storage, day));
  const summary = S.summary(storage, "2026-10-31");
  assert.equal(summary.current, 3);
  assert.equal(summary.longest, 3);
});

test("the first answer for an edition is kept; later attempts cannot change it", () => {
  const storage = new FakeStorage();
  S.recordResult(storage, "2026-10-31", 0, false);
  const second = S.recordResult(storage, "2026-10-31", 1, true);
  assert.deepEqual(second, { choice: 0, correct: false });
  assert.deepEqual(S.getResult(storage, "2026-10-31"), { choice: 0, correct: false });
  assert.equal(S.getResult(storage, "2026-10-30"), null);
});

test("corrupt or hostile stored data is ignored safely", () => {
  const storage = new FakeStorage();
  for (const bad of ["not json", "null", '{"v":2}', '{"v":1,"days":"x"}', '{"v":1,"days":["<script>",5,null,"2026-10-31"],"results":{"x":{"choice":"a"},"2026-10-31":{"choice":1,"correct":true}}}']) {
    storage.setItem(S.KEY, bad);
    const state = S.load(storage);
    assert.ok(Array.isArray(state.days));
  }
  const state = S.load(storage);
  assert.deepEqual(state.days, ["2026-10-31"]);
  assert.deepEqual(Object.keys(state.results), ["2026-10-31"]);
});

test("unavailable or full storage never throws", () => {
  const broken = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("full"); } };
  assert.doesNotThrow(() => S.recordVisit(broken, "2026-10-31"));
  assert.equal(S.summary(broken, "2026-10-31").current, 0);
  assert.doesNotThrow(() => S.summary(null, "2026-10-31"));
});

test("local date key uses the visitor's local calendar date", () => {
  assert.equal(S.localDateKey(new Date(2026, 9, 31, 23, 59)), "2026-10-31");
  assert.equal(S.localDateKey(new Date(2026, 0, 5, 0, 1)), "2026-01-05");
});
