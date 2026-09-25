import threading
from pathlib import Path

from enex_viewer.index import INDEX_NAME
from enex_viewer.store import Store


def test_store_can_be_used_from_another_thread(data_dir: Path) -> None:
    # FastAPI may open the store (dependency) and use it (endpoint) in
    # different worker threads.
    store = Store(data_dir / INDEX_NAME)
    result: list[int] = []
    errors: list[BaseException] = []

    def use() -> None:
        try:
            result.append(store.note_count())
        except BaseException as e:
            errors.append(e)

    t = threading.Thread(target=use)
    t.start()
    t.join()
    store.close()
    assert errors == []
    assert result == [3]


def test_store_works_on_a_read_only_data_dir(data_dir: Path) -> None:
    # The container mounts data/viewer read-only; nothing may try to write.
    paths = [data_dir, *data_dir.rglob("*")]
    for p in paths:
        p.chmod(p.stat().st_mode & ~0o222)
    try:
        store = Store(data_dir / INDEX_NAME)
        assert store.note_count() == 3
        page = store.notes(q="potatoes")
        assert page.total == 1
        store.close()
    finally:
        for p in paths:
            p.chmod(p.stat().st_mode | 0o200)
