import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from config_manager import ConfigManager
from config_window import ConfigWindow
from main_window import MainWindow
from test_stage2 import sample_config


class StageThreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.json"
        self.config = sample_config()
        self.path.write_text(json.dumps(self.config), encoding="utf-8")
        self.manager = ConfigManager(self.path)
        self.manager.load()

    def test_table_add_edit_save_updates_live_window(self):
        with patch("serial_manager.list_ports.comports", return_value=[]):
            window = MainWindow(config_manager=self.manager)
        self.addCleanup(window.close)
        editor = ConfigWindow(self.manager)
        self.addCleanup(editor.close)
        editor.add_button.click()
        row = editor.table.rowCount() - 1
        for column, value in [(0, "温度"), (1, "temperature"), (2, "℃"), (6, "0"), (7, "100")]:
            editor.table.item(row, column).setText(value)
        editor.table.cellWidget(row, 3).setCurrentText("float")
        editor.table.item(row, 4).setCheckState(Qt.CheckState.Checked)
        editor.table.item(row, 5).setCheckState(Qt.CheckState.Checked)
        editor.save_button.click()
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["parameters"][-1]["key"], "temperature")
        window.receive_raw_data("temperature=36.5\n")
        self.assertEqual(window.parameter_widgets["temperature"].text(), "36.5 ℃")

    def test_delete_and_invalid_save_preserve_disk(self):
        editor = ConfigWindow(self.manager)
        self.addCleanup(editor.close)
        editor.table.selectRow(1)
        editor.delete_button.click()
        self.assertEqual(editor.table.rowCount(), 2)
        editor.table.item(1, 1).setText("angle")
        editor.save_button.click()
        self.assertIn("重复", editor.message_label.text())
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), self.config)
        editor.table.item(1, 1).setText("state")
        editor.save_button.click()
        self.assertEqual([p["key"] for p in self.manager.config["parameters"]], ["angle", "state"])

    def test_failed_atomic_save_preserves_previous_file_and_config(self):
        changed = sample_config()
        changed["parameters"][0]["name"] = "新名称"
        errors = []
        self.manager.error.connect(errors.append)
        with patch("config_manager.os.replace", side_effect=PermissionError("locked")):
            self.assertFalse(self.manager.save(changed))
        self.assertEqual(self.manager.config, self.config)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), self.config)
        self.assertIn("locked", errors[0])
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_missing_file_can_be_created_by_saving(self):
        self.path.unlink()
        self.assertTrue(self.manager.save(self.config))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), self.config)


if __name__ == "__main__":
    unittest.main()
