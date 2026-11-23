"""R5: every raw data file is the file that was downloaded, byte for byte."""

import shutil

from nni_model.fingerprints import DATA, changed_files, read_fingerprints, raw_files


def test_every_raw_file_has_its_stored_fingerprint():
    assert sorted(read_fingerprints()) == raw_files()
    assert len(raw_files()) == 6
    assert changed_files() == []


def test_one_changed_byte_is_caught(tmp_path):
    folder = tmp_path / "data"
    shutil.copytree(DATA, folder)
    hours = folder / "pwt" / "pwt110_hours.csv"
    text = hours.read_bytes()
    hours.write_bytes(text.replace(b"1", b"2", 1))       # same size, one digit changed
    assert changed_files(folder) == [("pwt/pwt110_hours.csv", "bytes differ from the stored fingerprint")]


def test_a_new_or_missing_file_is_caught(tmp_path):
    folder = tmp_path / "data"
    shutil.copytree(DATA, folder)
    (folder / "wdi" / "extra.csv").write_text("economy,series,year,value\n")
    (folder / "eurostat" / "nama_10_a10_e_emp_total.csv").unlink()
    assert changed_files(folder) == [("wdi/extra.csv", "no stored fingerprint"),
                                     ("eurostat/nama_10_a10_e_emp_total.csv", "file missing")]
