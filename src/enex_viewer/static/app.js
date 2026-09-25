// Progressive enhancement for the browse page. Without it every link is a
// plain page load; with it:
//  - the note list loads more items as it scrolls (no paging), and
//  - opening a note swaps only the note pane, so the list keeps its items and
//    scroll position. The URL still changes and Back/Forward work.
(() => {
  "use strict";

  const list = document.querySelector("ol.notes");
  const pane = document.querySelector("main.note");
  if (!pane) return; // error pages

  // ---- Infinite scroll -----------------------------------------------------

  let loading = false;
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) loadMore(entry.target);
      }
    },
    { rootMargin: "0px 0px 800px 0px" } // start before the end is visible
  );

  function watchSentinel() {
    const sentinel = list && list.querySelector("li.load-more");
    if (sentinel) observer.observe(sentinel);
  }

  async function loadMore(sentinel) {
    if (loading) return;
    loading = true;
    observer.unobserve(sentinel);
    const link = sentinel.querySelector("a");
    const label = link ? link.textContent : "";
    if (link) link.textContent = "Loading…";
    try {
      const response = await fetch(sentinel.dataset.next);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      sentinel.insertAdjacentHTML("afterend", await response.text());
      sentinel.remove();
      markCurrent(currentNoteId());
      watchSentinel(); // the new batch ends with the next sentinel, if any
    } catch (err) {
      // Don't retry in a loop; the sentinel's link still opens the next page.
      if (link) link.textContent = label;
      console.error("loading more notes failed", err);
    } finally {
      loading = false;
    }
  }

  // ---- In-place note loading ------------------------------------------------

  const listUrl = location.pathname.startsWith("/notes/") ? null : location.href;
  const placeholder = pane.innerHTML;
  const listTitle = document.title;
  let listScrollY = 0; // phones: the list scrolls the window

  function noteIdFrom(url) {
    const m = new URL(url, location.href).pathname.match(/^\/notes\/([^/]+)$/);
    return m ? decodeURIComponent(m[1]) : null;
  }

  function currentNoteId() {
    return noteIdFrom(location.href);
  }

  function markCurrent(id) {
    if (!list) return;
    for (const li of list.querySelectorAll("li.current")) {
      li.classList.remove("current");
      li.querySelector("a")?.removeAttribute("aria-current");
    }
    if (!id) return;
    for (const a of list.querySelectorAll("a.note-link")) {
      if (a.dataset.id === id) {
        a.parentElement.classList.add("current");
        a.setAttribute("aria-current", "page");
      }
    }
  }

  function showList() {
    document.body.classList.replace("has-note", "no-note");
  }

  function showNote() {
    document.body.classList.replace("no-note", "has-note");
  }

  // Same breakpoint as style.css: one pane at a time, the window scrolls.
  const phone = window.matchMedia("(max-width: 860px)");
  function isPhoneLayout() {
    return phone.matches;
  }

  async function openNote(url, push) {
    const id = noteIdFrom(url);
    const target = new URL(url, location.href);
    let html;
    try {
      const response = await fetch(`/ui/note/${encodeURIComponent(id)}${target.search}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      html = await response.text();
    } catch (err) {
      location.href = url; // fall back to a normal page load
      return;
    }
    if (push && isPhoneLayout()) listScrollY = window.scrollY;
    pane.innerHTML = html;
    pane.scrollTop = 0;
    document.title = pane.querySelector("[data-title]")?.dataset.title || listTitle;
    markCurrent(id);
    showNote();
    if (push) {
      history.pushState({ note: id }, "", target.pathname + target.search);
      if (isPhoneLayout()) window.scrollTo(0, 0);
    }
  }

  function closeNote() {
    pane.innerHTML = placeholder;
    document.title = listTitle;
    markCurrent(null);
    showList();
    if (isPhoneLayout()) window.scrollTo(0, listScrollY);
  }

  function plainClick(event) {
    return (
      event.button === 0 &&
      !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
    );
  }

  if (list) {
    list.addEventListener("click", (event) => {
      const a = event.target.closest("a.note-link");
      if (!a || !plainClick(event)) return;
      event.preventDefault();
      if (noteIdFrom(a.href) === currentNoteId()) {
        showNote();
        return;
      }
      openNote(a.href, true);
    });
  }

  // "← back to list" in the note pane (visible on phones).
  pane.addEventListener("click", (event) => {
    const a = event.target.closest("a.back");
    if (!a || !plainClick(event) || !history.state?.note) return;
    event.preventDefault();
    history.back();
  });

  window.addEventListener("popstate", () => {
    const id = currentNoteId();
    if (id) openNote(location.href, false);
    else if (listUrl) closeNote();
    else location.reload(); // came in on a note URL; the list page isn't loaded
  });

  // A note opened directly by URL: make sure it's visible in the list.
  list?.querySelector("li.current")?.scrollIntoView({ block: "nearest" });
  watchSentinel();
})();
