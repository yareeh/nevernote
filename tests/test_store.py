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
