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

/** A local-time Date on an arbitrary fixed day. */
function at(hh, mm, day) {
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

console.log(failures ? `\n${failures} failing` : "\nall passing");
process.exit(failures ? 1 : 0);
