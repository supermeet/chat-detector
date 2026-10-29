"""End-to-end proof: real backend + real model + the unpacked extension in Chromium + the simulated chatroom.

Run from the repo root (needs `playwright install chromium` once):
    backend/.venv/Scripts/python -m pytest -q extension/tests/test_e2e.py
Screenshots land in docs/results/extension_<scenario>.png
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "extension"
SHOTS = ROOT / "docs" / "results"
PORT = 8765
BASE = f"http://localhost:{PORT}"


def _free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


@pytest.fixture(scope="module")
def backend():
    assert _free(PORT), f"port {PORT} busy"
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
                            cwd=ROOT / "backend", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/health", timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("backend did not start")
    yield BASE
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="module")
def browser(backend, tmp_path_factory):
    with playwright.sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(tmp_path_factory.mktemp("profile")), headless=True, channel="chromium",
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"], viewport={"width": 1280, "height": 860})
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
        sw.evaluate(f"chrome.storage.local.set({{api: '{backend}'}})")
        yield ctx
        ctx.close()


def _clear(backend):
    urllib.request.urlopen(urllib.request.Request(backend + "/data", method="DELETE"))


def _play(browser, backend, scenario, mode="scripted"):
    _clear(backend)
    page = browser.new_page()
    page.goto(f"{backend}/chatroom/?scenario={scenario}&speed=fast&mode={mode}&autostart=1")
    page.wait_for_selector("#safesphere-guard", state="attached", timeout=10000)
    return page


def _done(page):
    page.wait_for_selector('main#room[data-state="done"]', timeout=30000)
    page.wait_for_timeout(1500)   # last ingest round-trip


def _cards(page):
    return page.locator("#safesphere-guard .card")


def _shot(page, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"extension_{name}.png"))


def test_pile_on_alerts_and_blurs(browser, backend):
    page = _play(browser, backend, "pile_on")
    _done(page)
    titles = _cards(page).locator("h3").all_inner_texts()
    assert any("members of Class 12-B are targeting you" in t for t in titles), titles
    first = page.evaluate("""() => [...document.querySelector('#safesphere-guard').shadowRoot.querySelectorAll('.card')]
        .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0].querySelector('h3').textContent""")
    assert "members of Class 12-B" in first, f"room card must be shown first, got {first!r}"
    assert page.locator("#replying").is_hidden()
    assert page.locator("li.msg.ssg-blur").count() >= 1
    assert page.locator('li.msg[data-sender-id="kunal"].ssg-blur').count() == 0, "bystander chatter must not be blurred"
    _shot(page, "pile_on")
    page.close()


def test_banter_stays_quiet(browser, backend):
    page = _play(browser, backend, "banter")
    _done(page)
    assert _cards(page).count() == 0, _cards(page).all_inner_texts()
    assert page.locator("li.msg.ssg-blur").count() == 0
    status = page.locator("#safesphere-guard .status").inner_text()
    assert "messages aimed at you checked" in status, status
    _shot(page, "banter")
    page.close()


def test_singled_out_card(browser, backend):
    page = _play(browser, backend, "singled_out")
    _done(page)
    titles = _cards(page).locator("h3").all_inner_texts()
    assert any(t.startswith("Vikram ") for t in titles), titles
    _shot(page, "singled_out")
    page.close()


def test_sextortion_critical_card(browser, backend):
    page = _play(browser, backend, "sextortion")
    _done(page)
    crit = page.locator("#safesphere-guard .card.critical")
    assert crit.count() >= 1
    assert "Don't pay, don't delete, don't reply." in crit.first.inner_text()
    _shot(page, "sextortion")
    page.close()


def test_blurred_message_reveals_on_tap(browser, backend):
    page = _play(browser, backend, "pile_on")
    _done(page)
    node = page.locator("li.msg.ssg-blur").first
    mid = node.get_attribute("data-msg-id")
    node.click()
    assert "ssg-blur" not in (page.locator(f'li.msg[data-msg-id="{mid}"]').get_attribute("class") or "")
    page.close()


def test_not_harassment_resolves_card(browser, backend):
    page = _play(browser, backend, "singled_out")
    _done(page)
    card = _cards(page).first
    card.get_by_role("button", name="Not harassment").click()
    page.wait_for_selector("#safesphere-guard .card.resolved", timeout=5000)
    assert "Marked as not harassment" in card.inner_text()
    page.close()


def test_live_typing_pauses_and_uses_scenario_clock(browser, backend):
    page = _play(browser, backend, "singled_out", mode="live")
    page.wait_for_selector('main#room[data-state="waiting"]', timeout=15000)
    assert page.input_value("#input") == "hmm"
    page.fill("#input", "hmm")
    page.click("#send")
    page.wait_for_selector('main#room[data-state="playing"], main#room[data-state="waiting"]')
    mine = page.locator("li.msg[data-self]").first
    times = page.locator("li.msg time").evaluate_all("els => els.map(e => e.getAttribute('datetime'))")
    assert mine.locator("time").get_attribute("datetime") in times
    assert times == sorted(times), "typed reply must sit on the scenario clock"
    page.close()


def test_backend_down_is_reported(browser, backend):
    sw = browser.service_workers[0]
    sw.evaluate("chrome.storage.local.set({api: 'http://localhost:9'})")
    try:
        page = _play(browser, backend, "pile_on")
        page.wait_for_selector("#safesphere-guard .panel.error", timeout=15000)
        assert "not reachable" in page.locator("#safesphere-guard .status").inner_text()
        page.close()
    finally:
        sw.evaluate(f"chrome.storage.local.set({{api: '{backend}'}})")
