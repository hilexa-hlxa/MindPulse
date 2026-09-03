/**
 * The shuffle bag — the rule that decides which phrase gets sent next.
 *
 * Drawing uniformly at random every time is the obvious approach and it is
 * the wrong one: with 6 phrases you would see the same line twice in a row
 * roughly one pulse in six, and a phrase could sit unseen for days. So
 * instead every phrase is dealt exactly once per cycle, in a shuffled order.
 * Only when the bag is empty is it refilled and reshuffled.
 *
 *   bag = { order: [id, ...], cursor: n, last: id | null }
 *
 * `order` is the shuffled deal order for the current cycle, `cursor` is how
 * many of them have been dealt, and `last` is the id dealt most recently —
 * kept so a refill can avoid opening with the phrase the previous cycle just
 * closed on, which is the one place a plain reshuffle can still repeat.
 *
 * Every function is pure: it takes state and returns new state. `rnd` is
 * injectable so the behaviour can be tested against a seeded sequence.
 */
(function (root) {
  "use strict";

  function emptyBag() {
    return { order: [], cursor: 0, last: null };
  }

  /** Fisher-Yates, on a copy. */
  function shuffle(items, rnd) {
    rnd = rnd || Math.random;
    var a = items.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(rnd() * (i + 1));
      var t = a[i];
      a[i] = a[j];
      a[j] = t;
    }
    return a;
  }

  /**
   * Start a fresh cycle over `ids`, avoiding an immediate repeat of `last`.
   * With a single phrase there is nothing to avoid, so it just repeats.
   */
  function refill(ids, last, rnd) {
    rnd = rnd || Math.random;
    var order = shuffle(ids, rnd);
    if (order.length > 1 && order[0] === last) {
      var j = 1 + Math.floor(rnd() * (order.length - 1));
      order[0] = order[j];
      order[j] = last;
    }
    return order;
  }

  /**
   * Fold edits to the phrase list into an in-flight cycle.
   *
   * Deleted phrases drop out. Newly written ones are slotted at a random
   * point in the part of the cycle that has not been dealt yet, so a phrase
   * you add now can turn up on the next pulse rather than waiting for the
   * current cycle to drain. Phrases already dealt this cycle stay dealt.
   */
  function reconcile(bag, ids, rnd) {
    rnd = rnd || Math.random;
    var live = new Set(ids);
    var dealt = bag.order.slice(0, bag.cursor).filter(function (id) { return live.has(id); });
    var pending = bag.order.slice(bag.cursor).filter(function (id) { return live.has(id); });

    var known = new Set(dealt.concat(pending));
    ids.forEach(function (id) {
      if (known.has(id)) return;
      pending.splice(Math.floor(rnd() * (pending.length + 1)), 0, id);
    });

    return {
      order: dealt.concat(pending),
      cursor: dealt.length,
      last: live.has(bag.last) ? bag.last : null,
    };
  }

  /**
   * Deal the next phrase. Returns the drawn id (null if there are no
   * phrases), the bag to persist, and whether this draw opened a new cycle.
   */
  function draw(bag, ids, rnd) {
    rnd = rnd || Math.random;
    var next = reconcile(bag || emptyBag(), ids, rnd);

    if (!ids.length) return { id: null, bag: next, cycled: false };

    if (next.cursor >= next.order.length) {
      next = { order: refill(ids, next.last, rnd), cursor: 0, last: next.last };
    }

    // Sitting at the head of the order means this draw opens a cycle —
    // whether the bag was just refilled or reconcile built the first one.
    var cycled = next.cursor === 0;
    var id = next.order[next.cursor];
    return {
      id: id,
      bag: { order: next.order, cursor: next.cursor + 1, last: id },
      cycled: cycled,
    };
  }

  /** How many phrases are still undealt in the current cycle. */
  function remaining(bag, ids) {
    var next = reconcile(bag || emptyBag(), ids);
    var left = next.order.length - next.cursor;
    return left > 0 ? left : next.order.length;
  }

  root.RFBag = {
    emptyBag: emptyBag,
    shuffle: shuffle,
    refill: refill,
    reconcile: reconcile,
    draw: draw,
    remaining: remaining,
  };
})(typeof self !== "undefined" ? self : globalThis);
