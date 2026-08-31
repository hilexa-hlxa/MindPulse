/**
 * Checks the scheduling arithmetic — mostly the overnight quiet window,
 * which wraps past midnight and is the easiest part to get subtly wrong.
 * Run with: node test/pulse.test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ctx = { console, Date, Math, Object, String, parseInt, Promise, Set, Array };
ctx.self = ctx;
vm.createContext(ctx);
for (const f of ["bag.js", "pulse.js"]) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../lib", f), "utf8"), ctx);
}
const Pulse = ctx.MPPulse;

let failures = 0;
function check(name, fn) {
  try {
    fn();
    console.log("  ok   " + name);
  } catch (e) {
    failures++;
    console.log("  FAIL " + name + "\n       " + e.message);
  }
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

/**
 * A local-time Date on an arbitrary fixed day.
 *
 * The minute is required. Omitting it would build an Invalid Date, whose
 * getHours() is NaN — which windowAt() reads as "outside every window", so a
 * test written that way would pass while checking nothing at all. Better to
 * fail on the spot than to pass for the wrong reason.
 */
function at(hh, mm, day) {
  if (typeof mm !== "number") throw new Error("at() needs an explicit minute, e.g. at(9, 0)");
  return new Date(2026, 2, day || 10, hh, mm, 0, 0);
}

const overnight = { enabled: true, from: "22:00", to: "07:00" };
const daytime = { enabled: true, from: "13:00", to: "14:00" };

check("an overnight window covers both sides of midnight", () => {
  assert(Pulse.inQuiet(at(23, 0), overnight), "23:00 should be quiet");
  assert(Pulse.inQuiet(at(3, 0), overnight), "03:00 should be quiet");
  assert(Pulse.inQuiet(at(22, 0), overnight), "22:00 starts the window");
  assert(!Pulse.inQuiet(at(21, 59), overnight), "21:59 is before the window");
  assert(!Pulse.inQuiet(at(7, 0), overnight), "07:00 ends the window");
  assert(!Pulse.inQuiet(at(12, 0), overnight), "midday is not quiet");
});

check("a same-day window stays within the day", () => {
  assert(Pulse.inQuiet(at(13, 30), daytime), "13:30 should be quiet");
  assert(!Pulse.inQuiet(at(12, 0), daytime), "12:00 is before the window");
  assert(!Pulse.inQuiet(at(14, 0), daytime), "14:00 ends the window");
});

check("a window that is off, or has no width, never applies", () => {
  assert(!Pulse.inQuiet(at(23, 0), { enabled: false, from: "22:00", to: "07:00" }), "disabled window applied");
  assert(!Pulse.inQuiet(at(23, 0), { enabled: true, from: "22:00", to: "22:00" }), "zero-width window applied");
});

check("quiet lifts at the next occurrence of the end time", () => {
  assert(Pulse.quietEnds(at(23, 0), overnight) === at(7, 0, 11).getTime(), "23:00 should lift at 07:00 tomorrow");
  assert(Pulse.quietEnds(at(3, 0), overnight) === at(7, 0).getTime(), "03:00 should lift at 07:00 today");
});

check("a pulse landing in the quiet window is held until it lifts", () => {
  const now = at(21, 30).getTime();
  const next = Pulse.nextAfter(now, { intervalMs: 60 * 60 * 1000, quiet: overnight });
  assert(next === at(7, 0, 11).getTime(), "a 22:30 pulse should be held to 07:00, got " + new Date(next));
});

check("a pulse clear of the window lands exactly one interval out", () => {
  const now = at(9, 0).getTime();
  const next = Pulse.nextAfter(now, { intervalMs: 30 * 60 * 1000, quiet: overnight });
  assert(next === at(9, 30).getTime(), "expected 09:30, got " + new Date(next));
});

check("with no quiet window the interval is the whole rule", () => {
  const now = at(23, 0).getTime();
  const next = Pulse.nextAfter(now, { intervalMs: 60 * 60 * 1000, quiet: { enabled: false } });
  assert(next === at(0, 0, 11).getTime(), "expected midnight, got " + new Date(next));
});

check("the phrase always goes in the body, never the title", () => {
  const short = "Start badly. Fix it later.";
  const out = Pulse.splitForNotification({ text: short, note: "" });
  assert(out.body === short, "the body must carry the phrase");
  assert(out.title === "MindPulse", "the title stays a short fixed label");
});

check("a long phrase reaches the body complete and unclipped", () => {
  const long = "The mood follows the action rather than the other way round, so the "
    + "way out is to start moving before you feel like starting at all.";
  const out = Pulse.splitForNotification({ text: long, note: "" });
  assert(out.body === long, "the body must carry the complete phrase");
  assert(!out.body.includes("\u2026"), "the app must not pre-truncate the phrase itself");
});

check("nothing is ever put in the narrow title field", () => {
  // Measured on macOS: the title is clipped near 29 characters. Anything
  // longer than the label would risk exactly the bug this replaced.
  const cases = ["short", "x".repeat(240), "Если будешь дохуя думать, можно и передумать"];
  cases.forEach((text) => {
    const out = Pulse.splitForNotification({ text, note: "" });
    assert(out.title.length <= 29, "title must stay inside the clip point: " + out.title);
    assert(out.body === text, "body must be the untouched phrase");
  });
});

check("the longest phrase the app accepts still arrives whole", () => {
  const max = "x".repeat(120);   // the composer's cap
  assert(Pulse.splitForNotification({ text: max, note: "" }).body === max,
    "a 120-character phrase must survive intact in the body");
});

check("phrases written before the cap was lowered are left alone", () => {
  // Existing phrases can be longer than today's limit; the app must never
  // silently shorten something already written.
  const legacy = "y".repeat(240);
  assert(Pulse.splitForNotification({ text: legacy, note: "" }).body === legacy,
    "an over-length phrase must still be delivered in full");
});

// --- time windows (Advanced Mode) ---------------------------------------

check("the clock helper refuses a call that would build an invalid date", () => {
  let threw = false;
  try { at(9); } catch (e) { threw = true; }
  assert(threw, "at(9) must throw — it would otherwise yield NaN hours and quietly pass");
  assert(at(9, 30).getHours() === 9 && at(9, 30).getMinutes() === 30, "at() lost the time it was given");
});

const plain = { advanced: false };
const advanced = { advanced: true };

check("each window claims its own hours, and the boundaries do not overlap", () => {
  const expected = [
    [6, 0, "morning"], [11, 59, "morning"],
    [12, 0, "afternoon"], [17, 59, "afternoon"],
    [18, 0, "evening"], [23, 59, "evening"],
  ];
  expected.forEach(([h, m, want]) => {
    const got = Pulse.windowAt(at(h, m));
    assert(got === want, `${h}:${m} landed in ${got}, expected ${want}`);
  });
});

check("the small hours belong to no window at all", () => {
  [[0, 0], [3, 30], [5, 59]].forEach(([h, m]) => {
    assert(Pulse.windowAt(at(h, m)) === null, `${h}:${m} should be outside every window`);
  });
});

check("a phrase with no category set counts as anytime", () => {
  assert(Pulse.phraseWindow({ text: "old" }) === "anytime", "a legacy phrase must default to anytime");
  assert(Pulse.phraseWindow({ text: "x", window: "" }) === "anytime", "an empty category must fall back");
  assert(Pulse.phraseWindow({ text: "x", window: "teatime" }) === "anytime", "an unknown category must fall back");
  assert(Pulse.phraseWindow({ text: "x", window: "morning" }) === "morning", "a real category must be kept");
});

const mixed = [
  { id: "m", text: "m", window: "morning" },
  { id: "a", text: "a", window: "afternoon" },
  { id: "e", text: "e", window: "evening" },
  { id: "any", text: "any", window: "anytime" },
  { id: "legacy", text: "legacy" },
];
const idsOf = (list) => list.map((p) => p.id).join(",");

check("with Advanced Mode off every active phrase stays eligible, whatever the hour", () => {
  [0, 7, 13, 20].forEach((h) => {
    assert(idsOf(Pulse.eligible(mixed, at(h, 0), plain)) === "m,a,e,any,legacy",
      `advanced-off filtered the pool at ${h}:00`);
  });
});

check("with Advanced Mode on only this window's phrases are eligible", () => {
  assert(idsOf(Pulse.eligible(mixed, at(8, 0), advanced)) === "m,any,legacy", "morning pool wrong");
  assert(idsOf(Pulse.eligible(mixed, at(14, 0), advanced)) === "a,any,legacy", "afternoon pool wrong");
  assert(idsOf(Pulse.eligible(mixed, at(21, 0), advanced)) === "e,any,legacy", "evening pool wrong");
});

check("outside every window only anytime phrases can be sent", () => {
  assert(idsOf(Pulse.eligible(mixed, at(3, 0), advanced)) === "any,legacy",
    "the small hours should leave only anytime phrases");
});

check("existing phrases keep working when Advanced Mode is switched on", () => {
  // Nobody who turns this on has categorised anything yet. If that silenced
  // the app it would look broken, so an uncategorised library stays whole.
  const legacyOnly = [{ id: "1", text: "a" }, { id: "2", text: "b" }];
  [3, 8, 14, 21].forEach((h) => {
    assert(Pulse.eligible(legacyOnly, at(h, 0), advanced).length === 2,
      `an uncategorised library went quiet at ${h}:00`);
  });
});

check("muting takes a phrase out of the pool in both modes", () => {
  const withMuted = mixed.concat([{ id: "mute", text: "m", window: "morning", muted: true }]);
  assert(!idsOf(Pulse.eligible(withMuted, at(8, 0), advanced)).includes("mute"), "muted phrase eligible in advanced mode");
  assert(!idsOf(Pulse.eligible(withMuted, at(8, 0), plain)).includes("mute"), "muted phrase eligible in plain mode");
});

check("a window with nothing in it yields an empty pool rather than falling back", () => {
  const morningOnly = [{ id: "m", text: "m", window: "morning" }];
  assert(Pulse.eligible(morningOnly, at(20, 0), advanced).length === 0,
    "evening must not borrow a morning phrase");
  assert(Pulse.eligible(morningOnly, at(8, 0), advanced).length === 1,
    "morning should still deal its own phrase");
});

check("every window offers tone guidance for the composer", () => {
  Pulse.WINDOWS.forEach((w) => {
    assert(w.label && w.tone && w.placeholder, `${w.id} is missing its guidance`);
  });
  const ids = Pulse.WINDOWS.map((w) => w.id).join(",");
  assert(ids === "anytime,morning,afternoon,evening", `unexpected window order: ${ids}`);
});

console.log(failures ? `\n${failures} failing` : "\nall passing");
process.exit(failures ? 1 : 0);
