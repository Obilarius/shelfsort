from pathlib import Path

from shelfsort import executor
from shelfsort.executor import Reporter, execute
from shelfsort.plan import Op, PlanItem


def _item(src: Path, dst: Path) -> PlanItem:
    return PlanItem("movie", src, str(src), target=dst, ops=[Op("move", src, dst)], selected=True)


def test_progress_and_cancel(tmp_path, monkeypatch):
    # force the chunked copy path (normally only used across drives)
    monkeypatch.setattr(executor, "crosses_drive", lambda a, b: True)
    monkeypatch.setattr(executor, "CHUNK", 1000)
    src = tmp_path / "src"
    src.mkdir()
    a, b = src / "a.mkv", src / "b.mkv"
    a.write_bytes(b"x" * 5000)
    b.write_bytes(b"y" * 5000)
    items = [_item(a, tmp_path / "lib" / "A.mkv"), _item(b, tmp_path / "lib" / "B.mkv")]

    infos, states = [], []
    rep = Reporter(transfer=infos.append, item_state=lambda it, s: states.append((it.source.name, s)))

    def on_transfer(info):
        infos.append(info)
        if info.item_no == 2 and info.file_done == 2000:
            rep.cancel.set()  # user clicks "Abbrechen" mid-copy of the second file

    rep.transfer = on_transfer
    execute(items, rep, [tmp_path / "lib"])

    assert states == [("a.mkv", "running"), ("a.mkv", "done"), ("b.mkv", "running"), ("b.mkv", "cancelled")]
    assert (tmp_path / "lib" / "A.mkv").exists() and not a.exists()
    # cancelled: original untouched, no leftovers
    assert b.exists() and not (tmp_path / "lib" / "B.mkv").exists()
    assert not list((tmp_path / "lib").glob("*.partial"))
    assert items[1].status == "cancelled"
    # overall bytes cover both files, first file fully counted
    assert infos[0].all_total == 10000
    assert max(i.all_done for i in infos if i.item_no == 1) == 5000
