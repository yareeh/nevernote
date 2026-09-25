"""Real-browser tests for the list pane: infinite scroll and in-place note loading.

Run against a live server in a thread with Playwright driving the installed
Google Chrome; skipped when Chrome isn't available.
"""

import socket
import threading
from collections.abc import Iterator

import pytest
import uvicorn
from playwright.sync_api import Browser, Error, Page, sync_playwright

from enex_viewer.app import create_app
from enex_viewer.index import build_index
from enexgen import note, write

N_NOTES = 70
PAGE_SIZE = 20


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    tmp = tmp_path_factory.mktemp("browser")
    write(
        tmp / "enex" / "Inbox.enex",
        *(
            note(
                f"Note {i:03d}",
                f"<div>body of note {i:03d}</div>",
                created=f"2024{1 + i // 28:02d}{1 + i % 28:02d}T100000Z",
            )
            for i in range(N_NOTES)
        ),
    )
    build_index(tmp / "enex", tmp / "data")
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(tmp / "data", page_size=PAGE_SIZE),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        threading.Event().wait(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Error:
            pytest.skip("Google Chrome is not installed")
        yield b
        b.close()


@pytest.fixture
def desktop(browser: Browser) -> Iterator[Page]:
    ctx = browser.new_context(viewport={"width": 1400, "height": 800})
    yield ctx.new_page()
    ctx.close()


@pytest.fixture
def phone(browser: Browser) -> Iterator[Page]:
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    yield ctx.new_page()
    ctx.close()


def item_count(page: Page) -> int:
    return page.locator(".notes .note-link").count()


def scroll_list_to_end(page: Page) -> None:
    page.eval_on_selector(".list", "el => { el.scrollTop = el.scrollHeight; }")


def test_list_loads_more_on_scroll_instead_of_paging(
    desktop: Page, base_url: str
) -> None:
    desktop.goto(base_url + "/")
    assert item_count(desktop) == PAGE_SIZE
    assert desktop.locator(".pager").count() == 0
    for _ in range(10):
        if item_count(desktop) == N_NOTES:
            break
        scroll_list_to_end(desktop)
        desktop.wait_for_timeout(150)
    assert item_count(desktop) == N_NOTES
    assert desktop.locator(".load-more").count() == 0
    titles = desktop.locator(".notes .note-title").all_inner_texts()
    assert len(set(titles)) == N_NOTES


def test_selecting_a_note_keeps_the_list_where_it_is(
    desktop: Page, base_url: str
) -> None:
    desktop.goto(base_url + "/")
    scroll_list_to_end(desktop)
    desktop.wait_for_function(
        f"document.querySelectorAll('.note-link').length > {PAGE_SIZE}"
    )
    desktop.eval_on_selector(".list", "el => { el.scrollTop = 900; }")
    link = desktop.locator(".notes .note-link").nth(25)
    link.scroll_into_view_if_needed()  # what click() would do; measure after it
    before = desktop.eval_on_selector(".list", "el => el.scrollTop")
    assert before > 0
    title = link.locator(".note-title").inner_text()
    link.click()
    desktop.wait_for_function(
        "t => document.querySelector('.note-heading')?.textContent === t", arg=title
    )
    assert desktop.eval_on_selector(".list", "el => el.scrollTop") == before
    assert "/notes/" in desktop.url
    assert desktop.title().startswith(title)
    assert desktop.locator("li.current .note-title").inner_text() == title
    assert item_count(desktop) > PAGE_SIZE  # list was not re-rendered


def test_back_and_forward_switch_notes(desktop: Page, base_url: str) -> None:
    desktop.goto(base_url + "/")
    links = desktop.locator(".notes .note-link")
    first = links.nth(0).locator(".note-title").inner_text()
    second = links.nth(1).locator(".note-title").inner_text()
    links.nth(0).click()
    desktop.wait_for_function(
        "t => document.querySelector('.note-heading')?.textContent === t", arg=first
    )
    links.nth(1).click()
    desktop.wait_for_function(
        "t => document.querySelector('.note-heading')?.textContent === t", arg=second
    )
    desktop.go_back()
    desktop.wait_for_function(
        "t => document.querySelector('.note-heading')?.textContent === t", arg=first
    )
    desktop.go_back()
    desktop.wait_for_selector(".placeholder")
    assert desktop.url == base_url + "/"
    desktop.go_forward()
    desktop.wait_for_function(
        "t => document.querySelector('.note-heading')?.textContent === t", arg=first
    )


def test_phone_returns_to_the_same_list_position(phone: Page, base_url: str) -> None:
    phone.goto(base_url + "/")
    phone.evaluate("window.scrollTo(0, 800)")
    y = phone.evaluate("window.scrollY")
    assert y > 0
    link = phone.locator(".notes .note-link").nth(12)
    title = link.locator(".note-title").inner_text()
    link.click()
    phone.wait_for_function(
        "t => document.querySelector('.note-heading')?.textContent === t", arg=title
    )
    assert not phone.locator(".list").is_visible()
    phone.locator("a.back").click()
    phone.wait_for_function(
        "() => getComputedStyle(document.querySelector('.list')).display !== 'none'"
    )
    assert phone.evaluate("window.scrollY") == y
