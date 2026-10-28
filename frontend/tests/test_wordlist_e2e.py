"""Browser proof for the adaptive word list: a pile-on teaches a new slang word, the dashboard shows it for review,
approving it makes obfuscated spellings match at once (no retraining).

Run from the repo root:  backend/.venv/Scripts/python -m pytest -q frontend/tests/test_wordlist_e2e.py
"""
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "tests")]
from test_rooms import to_notifications  # noqa: E402  (the extension's mapping, mirrored in Python)

PORT = 8766
BASE = f"http://localhost:{PORT}"


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r).read() or b"null")


@pytest.fixture(scope="module")
def backend():
    with socket.socket() as s:
        assert s.connect_ex(("127.0.0.1", PORT)) != 0, f"port {PORT} busy"
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
                            cwd=ROOT / "backend", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/health", timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    yield
    proc.terminate()
    proc.wait(10)


def test_pile_on_teaches_word_list_and_approval_applies(backend):
    r = _req("POST", "/ingest/notification", to_notifications(_req("GET", "/demo/rooms/pile_on")))
    assert [x["term"] for x in r["new_slang"]] == ["behenji"], r["new_slang"]

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(BASE + "/")
        page.wait_for_selector("text=Live model", timeout=15000)
        page.get_by_role("button", name="Word list").first.click()

        item = page.locator("div", has=page.locator("span.mono", has_text="behenji")).filter(has_text="Approve").last
        item.wait_for(timeout=10000)
        assert "0 safe chats" in item.inner_text() and "Auto" in item.inner_text()
        item.get_by_role("button", name="Approve").click()

        page.wait_for_selector("td.mono:text-is('behenji')", timeout=10000)
        page.fill("#tst", "tu full b3h3nji hai")
        page.wait_for_function("document.body.innerText.includes('Message read as: insult')", timeout=10000)
        body = page.inner_text("body")
        assert "behenji (Bullying" in body
        page.screenshot(path=str(ROOT / "docs" / "results" / "wordlist_learned.png"), full_page=False)
        browser.close()

    lex = _req("GET", "/lexicon")
    assert not lex["pending"] and any(t["term"] == "behenji" and t["src"] == "Auto" for t in lex["terms"])
