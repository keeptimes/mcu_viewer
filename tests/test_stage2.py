import copy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from config_manager import ConfigManager
from data_parser import DataParser
from main_window import MainWindow
from serial_manager import SerialManager, SerialWorker


def sample_config():
    return {"serial": {"baudrate": 115200}, "parameters": [
        {"name": "角度", "key": "angle", "unit": "°", "type": "float", "show": True, "curve": True, "min": -90, "max": 90},
        {"name": "速度", "key": "speed", "unit": "rpm", "type": "int", "show": True, "curve": True, "min": 0, "max": 500},
        {"name": "状态", "key": "state", "unit": "", "type": "string", "show": False, "curve": False, "min": None, "max": None},
    ]}


class StageTwoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.json"
        self.config = sample_config()

    def write_config(self, config):
        self.path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    def test_config_missing_invalid_and_last_good_retained(self):
        manager = ConfigManager(self.path)
        errors = []
        manager.error.connect(errors.append)
        self.assertFalse(manager.load())
        self.assertEqual(manager.config["parameters"], [])
        self.write_config(self.config)
        self.assertTrue(manager.load())
        self.path.write_text("{ broken", encoding="utf-8")
        self.assertFalse(manager.load())
        self.assertEqual(manager.config, self.config)
        self.assertEqual(len(errors), 2)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{ broken")

    def test_config_validation_rejects_bad_schema(self):
        cases = []
        bad = copy.deepcopy(self.config)
        bad["parameters"][1]["key"] = "angle"
        cases.append(bad)
        for field, value in [("type", "bool"), ("show", "false"), ("min", 1000), ("max", float("nan")), ("key", "a=b")]:
            bad = copy.deepcopy(self.config)
            bad["parameters"][0][field] = value
            cases.append(bad)
        for bad in cases:
            with self.subTest(config=bad), self.assertRaises(ValueError):
                ConfigManager.validate(bad)

    def test_parser_skips_unknown_and_only_bad_fields(self):
        parser = DataParser(self.config["parameters"])
        self.assertEqual(parser.parse_line(""), {})
        self.assertEqual(parser.parse_line("angle=2.15,speed=120,state=a=b,unknown=42"), {"angle": 2.15, "speed": 120, "state": "a=b"})
        self.assertEqual(parser.parse_line("angle=oops,speed=120,bad,=4"), {"speed": 120})
        self.assertEqual(parser.parse_line("angle=nan,speed=1.5"), {})
        self.assertEqual(parser.parse_line("angle=inf,speed=3e2"), {})

    def test_stream_framing_and_oversized_line_recovery(self):
        parser = DataParser(self.config["parameters"])
        samples = []
        parser.data_received.connect(samples.append)
        parser.feed("angle=2.")
        self.assertEqual(samples, [])
        parser.feed("15,speed=120\r")
        parser.feed("\nstate=正常\nspeed=42\n")
        self.assertEqual(samples, [{"angle": 2.15, "speed": 120}, {"state": "正常"}, {"speed": 42}])
        parser.feed("x" * 20000)
        parser.feed("speed=999\nspeed=7\n")
        self.assertEqual(samples[-1], {"speed": 7})
        self.assertNotIn({"speed": 999}, samples)
        parser.feed("speed=1")
        parser.reset()
        parser.feed("23\nspeed=9\n")
        self.assertEqual(samples[-1], {"speed": 9})

    def test_new_parameter_from_json_requires_no_code_change(self):
        self.write_config(self.config)
        with patch("serial_manager.list_ports.comports", return_value=[]):
            window = MainWindow(config_manager=ConfigManager(self.path))
        self.addCleanup(window.close)
        self.assertNotIn("state", window.parameter_widgets)
        self.config["parameters"].append({"name": "温度", "key": "temperature", "unit": "℃", "type": "float", "show": True, "curve": True, "min": 0, "max": 100})
        self.write_config(self.config)
        self.assertTrue(window.config_manager.load())
        window.manager.raw_data.emit("angle=2.15,speed=120,temperature=36.5\r\n")
        self.assertEqual(window.parameter_widgets["temperature"].text(), "36.5 ℃")
        self.assertEqual(window.parameter_widgets["angle"].text(), "2.15 °")
        self.assertEqual(window.parameter_widgets["speed"].text(), "120 rpm")

    def test_fragmented_crlf_does_not_add_blank_lines(self):
        self.write_config(self.config)
        with patch("serial_manager.list_ports.comports", return_value=[]):
            window = MainWindow(config_manager=ConfigManager(self.path))
        self.addCleanup(window.close)
        window.receive_raw_data("speed=1\r")
        window.receive_raw_data("\nspeed=2\r\n")
        self.assertEqual(window.raw_display.toPlainText(), "speed=1\nspeed=2\n")

    def test_queue_overflow_never_combines_text_across_gap(self):
        manager = SerialManager()
        worker = SerialWorker("COM_TEST", 115200)
        manager._worker = worker
        parser = DataParser(self.config["parameters"])
        samples = []
        parser.data_received.connect(samples.append)
        manager.raw_data.connect(parser.feed)
        manager.data_gap.connect(parser.discard_partial)
        # 填满队列，模拟丢失的包；随后 GUI 消费一个元素，后台又放入数据。
        for _ in range(127):
            worker._enqueue("\n")
        worker._enqueue("speed=1")
        worker._enqueue("lost\n")
        # 消费一个空行后腾出位置，剩余队列末尾为被截断的数值。
        first = worker.received.get_nowait()
        parser.feed(first[0])
        worker._enqueue("23\nspeed=7\n")
        manager._drain()
        self.assertEqual(samples, [{"speed": 7}])
        manager._worker = None


if __name__ == "__main__":
    unittest.main()
