"""
One real end-to-end browser test (spec round 3, item 6).

Everything else in this suite hits the ASGI app in-process via httpx —
fast, but it never proves the actual HTML/CSS/JS a user gets ever loads,
renders, or wires up correctly. This test instead:

  1. Boots the real app as a subprocess (`uvicorn`, real TCP socket).
  2. Drives it with a real Chromium browser via Playwright.
  3. Adds a phrase through the actual Add form.
  4. Confirms that exact text renders in the Phrases list — not just
     that the API returned 201.
  5. Fires "Send now" and confirms the Dashboard's "Last sent" timestamp
     advances from "Never" — proof the full click -> fetch -> FastAPI ->
     scheduler -> DB round trip actually ran in a real browser.

Scope note: this deliberately does NOT try to assert on the literal OS
notification banner. Web Push requires a genuine round trip to the
browser vendor's push service (FCM for Chrome); a fake VAPID
subscription used in tests can't reach it, and headless Chromium won't
reliably surface OS-level notification UI to automation anyway. The
"last sent" + "times_sent" advancing is the same completion signal the
real UI shows the user, and it's what's actually verifiable.

Marked `e2e` and excluded from the default `pytest` run (see pytest.ini)
because it needs `playwright install chromium` — a heavy one-time
download most environments won't have. Run explicitly with:
    pytest backend/tests/test_e2e.py -m e2e -v
"""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
PORT = 8199
BASE_URL = f"http://127.0.0.1:{PORT}"


def _wait_until_ready(timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1)
            return
        except (urllib.error.URLError, ConnectionError) as exc:
            last_error = exc
            time.sleep(0.3)
    raise RuntimeError(f"live server never became ready: {last_error}")


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("e2e") / "e2e.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        "VAPID_PRIVATE_KEY": "test-private-key",
        "VAPID_PUBLIC_KEY": "test-public-key",
        "VAPID_CLAIMS_EMAIL": "mailto:test@example.com",
        "ALLOWED_ORIGINS": BASE_URL,
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(PORT)],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_until_ready()
        yield BASE_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_add_phrase_and_trigger_notification_e2e(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(live_server)

        # --- Add a phrase through the real UI ---
        page.click('nav.tabbar button[data-view="add"]')
        page.fill("#add-text", "E2E phrase, verified by a real browser.")
        page.fill("#add-author", "Playwright")
        page.click('#add-phrase-form button[type="submit"]')

        # Adding routes to the Phrases view (see app.js) — the exact text
        # we typed must show up verbatim, not just "some phrase exists".
        phrase_text = page.locator(".phrase-text").first
        phrase_text.wait_for(timeout=5000)
        assert phrase_text.inner_text() == "E2E phrase, verified by a real browser."

        # --- Trigger a notification and confirm the full pipeline ran ---
        page.click('nav.tabbar button[data-view="dashboard"]')
        page.wait_for_selector("#dash-last-sent:has-text('Never')")

        page.click("#btn-trigger")
        page.wait_for_function(
            "document.getElementById('dash-last-sent').textContent !== 'Never'", timeout=5000
        )

        browser.close()
