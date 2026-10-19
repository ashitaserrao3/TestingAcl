import pytest

import drive_store
from fake_google import FakeGoogle


@pytest.fixture
def google(monkeypatch):
    g = FakeGoogle()
    monkeypatch.setattr(drive_store, "API", g.url)
    yield g
    g.close()


def test_placeholder_file_reads_as_empty_then_round_trips(google):
    store = drive_store.DriveStore(google.service_account(), "FILE1")
    assert store.download() == {}  # the file Ashita created hasn't been written by the app yet
    store.upload({"rates/Indigo Eff. 16th Oct 2026.xlsx": b"new", "rates/SG 29-Jul-26.xlsx": b"sg"})
    assert google.uploads == 1
    restarted = drive_store.DriveStore(google.service_account(), "FILE1")  # e.g. after an app restart
    assert restarted.download() == {"rates/Indigo Eff. 16th Oct 2026.xlsx": b"new", "rates/SG 29-Jul-26.xlsx": b"sg"}


def test_wrong_file_id_is_reported(google):
    with pytest.raises(RuntimeError, match="404"):
        drive_store.DriveStore(google.service_account(), "NOPE").download()
