"""Leftovers of interrupted transfers in the library check."""
import os
import time

from shelfsort.audit import STILL_COPYING, leftover_items
from shelfsort.executor import Reporter, execute
from test_core import touch


def _old(p):
    t = time.time() - STILL_COPYING - 60
    os.utime(p, (t, t))
    return p


def test_leftovers_are_found(tmp_path):
    d = tmp_path / "Arrival (2016) {tmdb-329865}"
    partial = _old(touch(d / "Arrival (2016).mkv.partial", 3 * 1024 * 1024))
    parked = touch(d / "Arrival (2016) - pt2.mkv.shelfsort-tmp")
    running = touch(d / "Other (2020).mkv.partial")  # just written: a transfer may still be running
    touch(d / "Arrival (2016).mkv")
    items = {it.source: it for it in leftover_items(d)}
    assert set(items) == {partial, parked}
    assert items[partial].ops[0].kind == "delete_file" and "3 MB" in items[partial].note
    assert items[parked].target == d / "Arrival (2016) - pt2.mkv" and items[parked].status == "review"
    assert running.exists()
    assert not any(it.selected for it in items.values())  # never preselected


def test_parked_name_taken_is_a_conflict(tmp_path):
    touch(tmp_path / "S01E02.mkv")
    touch(tmp_path / "S01E02.mkv.shelfsort-tmp")
    [item] = leftover_items(tmp_path)
    assert item.status == "conflict"


def test_leftovers_are_cleaned_up(tmp_path):
    d = tmp_path / "lib" / "Show"
    partial = _old(touch(d / "x.mkv.partial"))
    parked = touch(d / "Season 01" / "Show - S01E02.mkv.shelfsort-tmp", 7)
    items = leftover_items(d)
    for it in items:
        it.selected = True
    execute(items, Reporter(), [tmp_path / "lib"])
    assert not partial.exists() and not parked.exists()
    assert (d / "Season 01" / "Show - S01E02.mkv").stat().st_size == 7
    assert all(it.status == "done" for it in items)
