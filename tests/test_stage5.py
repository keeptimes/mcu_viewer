import csv
from datetime import datetime
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from config_manager import ConfigManager
from csv_logger import CSVLogger
from main_window import MainWindow
from test_stage2 import sample_config


class StageFiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.config = sample_config()
        self.logger = CSVLogger(self.directory / "data")
        self.addCleanup(self.logger.stop)

    def read_rows(self, path):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.reader(stream))

    def test_csv_order_timestamp_missing_fields_and_string_quoting(self):
        self.assertTrue(self.logger.start(self.config["parameters"]))
        self.logger.write_sample({"angle": 2.15, "state": "正常,运行"}, datetime(2026, 9, 29, 10, 15, 21, 123000))
        self.logger.stop()
        rows = self.read_rows(self.logger.path)
        self.assertEqual(rows, [["timestamp", "angle", "speed", "state"], ["10:15:21.123", "2.15", "", "正常,运行"]])
        self.assertFalse(self.logger.is_recording)
        self.logger.path.rename(self.directory / "closed.csv")

    def test_same_second_recordings_do_not_overwrite(self):
        with patch("csv_logger.datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 29, 10, 15, 21)
            self.logger.start(self.config["parameters"])
            first = self.logger.path
            self.logger.stop()
            self.logger.start(self.config["parameters"])
            second = self.logger.path
            self.logger.stop()
        self.assertNotEqual(first, second)
        self.assertEqual(first.name, "data_20260929_101521.csv")
        self.assertTrue(second.exists())
        self.assertTrue(first.exists())

    def test_file_creation_failure_is_reported(self):
        blocked = self.directory / "not_a_directory"
        blocked.write_text("file", encoding="utf-8")
        logger = CSVLogger(blocked)
        errors = []
        logger.error.connect(errors.append)
        self.assertFalse(logger.start(self.config["parameters"]))
        self.assertFalse(logger.is_recording)
        self.assertTrue(errors)

    def test_write_failure_stops_recording_and_releases_file(self):
        errors = []
        self.logger.error.connect(errors.append)
        self.logger.start(self.config["parameters"])
        with patch.object(self.logger._writer, "writerow", side_effect=OSError("disk full")):
            self.logger.write_sample({"angle": 1})
        self.assertFalse(self.logger.is_recording)
        self.assertIn("disk full", errors[0])
        self.logger.path.rename(self.directory / "released.csv")

    def make_window(self):
        path = self.directory / "config.json"
        path.write_text(json.dumps(self.config), encoding="utf-8")
        with patch("serial_manager.list_ports.comports", return_value=[]):
            window = MainWindow(config_manager=ConfigManager(path), csv_logger=self.logger)
        self.addCleanup(window.close)
        return window

    def test_main_window_logging_and_configuration_change(self):
        window = self.make_window()
        window.start_record_button.click()
        self.assertTrue(self.logger.is_recording)
        window.receive_raw_data("angle=2.15,speed=120\n")
        self.assertEqual(window.parameter_widgets["speed"].text(), "120 rpm")
        self.assertEqual(len(window.chart.history["angle"]), 1)
        changed = window.config_manager.config
        changed["parameters"].pop()
        window.config_manager.save(changed)
        self.assertFalse(self.logger.is_recording)
        rows = self.read_rows(self.logger.path)
        self.assertEqual(rows[0], ["timestamp", "angle", "speed", "state"])
        self.assertEqual(rows[1][1:], ["2.15", "120", ""])

    def test_window_exit_closes_recording(self):
        window = self.make_window()
        window.start_record_button.click()
        window.receive_raw_data("speed=120\n")
        window.close()
        self.assertFalse(self.logger.is_recording)
        self.assertEqual(self.read_rows(self.logger.path)[1][2], "120")


if __name__ == "__main__":
    unittest.main()
