# MindPulse

Write down the phrases you want to hear again. MindPulse deals one back to you
as a notification on a rhythm you set — and never repeats a phrase until it has
worked through every other one.

![MindPulse](docs/screenshot.jpg)

It is a single static page. No server, no account, no build step, no
dependencies. Your phrases are stored in IndexedDB on your own device and are
never sent anywhere.

## Run it

```sh
python3 -m http.server 8123
```

Then open <http://127.0.0.1:8123>. Any static host works just as well — GitHub
Pages, Netlify, Vercel — with no configuration; every path in the app is
relative, so serving it from a subdirectory is fine too.

Notifications need a secure context, which means `localhost` or HTTPS.
Opening `index.html` as a `file://` URL shows the app but cannot register the
service worker.

## How the phrase is chosen

Drawing uniformly at random each time is the obvious approach and it is the
wrong one. With six phrases you would see the same line twice in a row about
one pulse in six, and any given phrase could go unseen for days.

So MindPulse uses a shuffle bag. Every phrase is dealt exactly once per cycle,
in a shuffled order; only when the bag is empty is it refilled and reshuffled.
Refilling also avoids opening a cycle with the phrase the previous one just
closed on, which is the single place a plain reshuffle can still repeat.

```
phrases   0 1 2 3 4 5
cycle 1   2 5 0 3 1 4     each phrase once
cycle 2   1 0 4 2 5 3     reshuffled, and never 4 first
```

Editing the list folds into the cycle already running: a deleted phrase drops
out immediately, and a phrase you add now is slotted somewhere in the part of
the cycle that has not been dealt yet, so it can turn up on the very next
pulse instead of waiting.

The **This cycle** row on screen is that bag, drawn — one tile per phrase, lit
while it is still to come, dark once it has been dealt. The tiles all relight
together when the cycle turns over.

## When pulses arrive

Delivery is done by your device, not by a server.

- Pulses arrive whenever MindPulse is open, including in a background tab.
- If one came due while the app was closed, it is delivered when you come
  back — once, not once for every hour you were away.
- Installed to your home screen, Chrome may also deliver while the app is
  closed, through Periodic Background Sync. Browsers grant this sparingly, so
  treat it as a bonus rather than a guarantee.

**Hold pulses overnight** pauses delivery between the two times you choose, and
picks up again when the window lifts.

## Around the app

- **Pulse now** deals one immediately, without touching the schedule.
- **Pause** stops delivery entirely until you resume.
- Muting a phrase keeps it in your list but takes it out of the rotation.
- **Export** writes your phrases to a JSON file; **Import** adds back anything
  from such a file that you do not already have, and leaves the rest alone.

## Tests

```sh
npm test          # or: node test/bag.test.js && node test/pulse.test.js
```

`test/bag.test.js` checks the guarantees the shuffle bag makes — full coverage
per cycle, no back-to-back repeats across cycle boundaries, uniform delivery
over many cycles, and correct behaviour when the phrase list is edited
mid-cycle. `test/pulse.test.js` covers the scheduling arithmetic, mostly the
overnight window, which wraps past midnight.

## Layout

```
index.html              the whole interface
styles.css
app.js                  reads state, paints it, writes back changes
lib/bag.js              the shuffle bag
lib/pulse.js            deciding when to send, and sending
lib/idb.js              key/value storage on IndexedDB
sw.js                   offline shell, background delivery, notification taps
```

`lib/` is shared: the page loads those three files with `<script>`, and the
service worker pulls in the same files with `importScripts`. A pulse delivered
while the app is closed is therefore drawn by exactly the same code as one
delivered while you are looking at it.

## Licence

MIT — see [LICENSE](LICENSE).
