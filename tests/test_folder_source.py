"""
Tests for the folder reader, run against real files on a real disk.

This is the part a user touches directly, so it is the part that has to be right
before anything is wired to WhatsApp. Two days were lost upstream to code that
looked correct and was not; the answer to that is tests that actually run.
"""

import sys
import tempfile
import unittest
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qasid import folder_source as fs          # noqa: E402

DAY = date(2026, 9, 4)


class FolderCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.day = self.root / DAY.isoformat()
        self.day.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, text: str = "") -> Path:
        p = self.day / name
        p.write_bytes(text.encode("utf-8")) if text else p.write_bytes(b"\x00")
        return p

    # --- the shapes the README promises -------------------------------------

    def test_picture_and_text_of_the_same_name_are_one_post(self):
        self.write("1.jpg")
        self.write("1.txt", "Hello world")
        posts = fs.read_day(self.root, DAY)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].caption, "Hello world")
        self.assertEqual(posts[0].image.name, "1.jpg")
        self.assertEqual(posts[0].kind, "picture with caption")

    def test_picture_alone_posts_without_a_caption(self):
        self.write("1.jpg")
        posts = fs.read_day(self.root, DAY)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].caption, "")
        self.assertEqual(posts[0].kind, "picture")

    def test_text_alone_posts_as_a_message(self):
        self.write("note.txt", "Just words")
        posts = fs.read_day(self.root, DAY)
        self.assertEqual(len(posts), 1)
        self.assertIsNone(posts[0].image)
        self.assertEqual(posts[0].kind, "text")

    def test_order_is_by_filename(self):
        for n in ("3", "1", "2"):
            self.write(f"{n}.jpg")
        self.assertEqual([p.key for p in fs.read_day(self.root, DAY)], ["1", "2", "3"])

    # --- the things users will actually do ----------------------------------

    def test_other_files_and_folders_are_ignored_not_errors(self):
        self.write("1.jpg")
        self.write("notes.docx")
        self.write("thumbs.db")
        (self.day / "spare").mkdir()
        posts = fs.read_day(self.root, DAY)
        self.assertEqual(len(posts), 1)

    def test_a_different_day_is_left_alone(self):
        other = self.root / "2026-09-05"
        other.mkdir()
        (other / "1.jpg").write_bytes(b"\x00")
        self.assertEqual(fs.read_day(self.root, DAY), [])

    def test_missing_folder_is_an_empty_day_not_a_crash(self):
        self.assertEqual(fs.read_day(self.root, date(2030, 1, 1)), [])

    def test_empty_text_file_does_not_create_a_post(self):
        self.write("1.txt", "   \n  ")
        self.assertEqual(fs.read_day(self.root, DAY), [])

    def test_uppercase_extensions_work(self):
        self.write("1.JPG")
        self.write("1.TXT", "shouting")
        posts = fs.read_day(self.root, DAY)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].caption, "shouting")

    def test_urdu_text_survives_intact(self):
        self.write("1.jpg")
        self.write("1.txt", "آج کا حال — حمل")
        self.assertEqual(fs.read_day(self.root, DAY)[0].caption, "آج کا حال — حمل")

    # --- times ---------------------------------------------------------------

    def test_filename_time_prefix_is_read(self):
        self.write("07-15 hamal.jpg")
        self.write("07-15 hamal.txt", "Aries")
        posts = fs.read_day(self.root, DAY)
        self.assertEqual(len(posts), 1, "the prefix must not split the pair")
        self.assertEqual(posts[0].at, time(7, 15))
        self.assertEqual(posts[0].caption, "Aries")

    def test_posts_without_a_time_are_spread_by_the_gap(self):
        for n in ("1", "2", "3"):
            self.write(f"{n}.jpg")
        plan = fs.schedule(fs.read_day(self.root, DAY), time(7, 15), 3, DAY)
        self.assertEqual([w.strftime("%H:%M") for w, _ in plan],
                         ["07:15", "07:18", "07:21"])

    def test_a_pinned_time_wins_and_does_not_shift_the_others(self):
        self.write("1.jpg")
        self.write("2.jpg")
        self.write("20-00 evening.jpg")
        plan = fs.schedule(fs.read_day(self.root, DAY), time(7, 15), 3, DAY)
        got = {p.key: w.strftime("%H:%M") for w, p in plan}
        self.assertEqual(got["evening"], "20:00")
        self.assertEqual(got["1"], "07:15")
        self.assertEqual(got["2"], "07:18")

    def test_available_days_lists_only_real_dates(self):
        (self.root / "2026-09-05").mkdir()
        (self.root / "old pictures").mkdir()
        self.assertEqual(fs.available_days(self.root),
                         [date(2026, 9, 4), date(2026, 9, 5)])

    def test_keys_are_unique_within_a_day(self):
        for n in ("1", "2", "3"):
            self.write(f"{n}.jpg")
        keys = [p.key for p in fs.read_day(self.root, DAY)]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
