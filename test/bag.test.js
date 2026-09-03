/**
 * Checks the guarantees the shuffle bag is supposed to make.
 * Run with: node test/bag.test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ctx = { console };
ctx.self = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, "../lib/bag.js"), "utf8"), ctx);
const Bag = ctx.RFBag;

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

/** Deterministic pseudo-random so a failure is reproducible. */
function seeded(seed) {
  let s = seed >>> 0;
  return function () {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function deal(ids, count, rnd) {
  let bag = Bag.emptyBag();
  const out = [];
  for (let i = 0; i < count; i++) {
    const r = Bag.draw(bag, ids, rnd);
    bag = r.bag;
    out.push(r.id);
  }
  return out;
}

const ids = ["0", "1", "2", "3", "4", "5"];

check("deals every phrase exactly once per cycle", () => {
  for (let seed = 1; seed <= 200; seed++) {
    const cycle = deal(ids, ids.length, seeded(seed));
    assert(new Set(cycle).size === ids.length, `seed ${seed} repeated inside a cycle: ${cycle}`);
  }
});

check("never repeats back to back, including across cycle boundaries", () => {
  for (let seed = 1; seed <= 200; seed++) {
    const run = deal(ids, 600, seeded(seed));
    for (let i = 1; i < run.length; i++) {
      assert(run[i] !== run[i - 1], `seed ${seed} repeated ${run[i]} at index ${i}`);
    }
  }
});

check("shuffles: a cycle is not always the insertion order", () => {
  const seen = new Set();
  for (let seed = 1; seed <= 60; seed++) seen.add(deal(ids, ids.length, seeded(seed)).join(","));
  assert(seen.size > 20, `only ${seen.size} distinct orders across 60 seeds`);
});

check("stays uniform over many cycles", () => {
  const run = deal(ids, 6000, seeded(7));
  const counts = {};
  run.forEach((id) => (counts[id] = (counts[id] || 0) + 1));
  // Exactly 1000 each: every cycle deals the full set, and 6000 is a whole
  // number of cycles. The bag is fairer than uniform random sampling.
  ids.forEach((id) => assert(counts[id] === 1000, `${id} drawn ${counts[id]} times, expected 1000`));
});

check("reports a new cycle only when one actually opens", () => {
  let bag = Bag.emptyBag();
  const rnd = seeded(3);
  const flags = [];
  for (let i = 0; i < 13; i++) {
    const r = Bag.draw(bag, ids, rnd);
    bag = r.bag;
    flags.push(r.cycled);
  }
  assert(flags.filter(Boolean).length === 3, `expected 3 cycle starts in 13 draws, got ${flags.filter(Boolean).length}`);
  assert(flags[0] && flags[6] && flags[12], `cycle starts landed at the wrong draws: ${flags}`);
});

check("a single phrase just repeats", () => {
  assert(deal(["solo"], 5, seeded(1)).every((id) => id === "solo"), "single phrase not dealt");
});

check("an empty list draws nothing", () => {
  const r = Bag.draw(Bag.emptyBag(), [], seeded(1));
  assert(r.id === null, "expected null from an empty list");
  assert(r.cycled === false, "an empty list should not report a cycle");
});

check("a deleted phrase stops being dealt", () => {
  const rnd = seeded(11);
  let bag = Bag.draw(Bag.emptyBag(), ids, rnd).bag;
  const kept = ids.filter((id) => id !== "3");
  for (let i = 0; i < 200; i++) {
    const r = Bag.draw(bag, kept, rnd);
    bag = r.bag;
    assert(r.id !== "3", "dealt a phrase that was deleted");
  }
});

check("a new phrase can be dealt in the cycle already running", () => {
  const rnd = seeded(5);
  let bag = Bag.draw(Bag.emptyBag(), ids, rnd).bag; // 1 of 6 dealt
  const grown = ids.concat(["new"]);
  const rest = [];
  for (let i = 0; i < 6; i++) {
    const r = Bag.draw(bag, grown, rnd);
    bag = r.bag;
    rest.push(r.id);
  }
  assert(rest.includes("new"), `new phrase waited for the next cycle: ${rest}`);
});

check("counts what is left in the cycle", () => {
  let bag = Bag.emptyBag();
  const rnd = seeded(9);
  assert(Bag.remaining(bag, ids) === 6, "a fresh bag should have all 6 left");
  for (let i = 1; i <= 5; i++) {
    bag = Bag.draw(bag, ids, rnd).bag;
    assert(Bag.remaining(bag, ids) === 6 - i, `after ${i} draws expected ${6 - i} left`);
  }
  bag = Bag.draw(bag, ids, rnd).bag; // drains the cycle
  assert(Bag.remaining(bag, ids) === 6, "a drained cycle should read as a full one again");
});

console.log(failures ? `\n${failures} failing` : "\nall passing");
process.exit(failures ? 1 : 0);
