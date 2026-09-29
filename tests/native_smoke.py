"""手动运行：真实 Windows 窗口 + PySerial loopback 的全流程验证。"""

import csv
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import serial
from config_manager import ConfigManager
from config_window import ConfigWindow
from csv_logger import CSVLogger
from main_window import MainWindow


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    failures = []
    def report_exception(kind, value, traceback):
        failures.append(str(value))
        sys.__excepthook__(kind, value, traceback)
        app.quit()
    sys.excepthook = report_exception
    with TemporaryDirectory() as temporary:
        config_path = Path(temporary) / "config.json"
        config = json.loads((ROOT / "config" / "config.json").read_text(encoding="utf-8"))
        config["parameters"].append({"name": "温度", "key": "temperature", "unit": "℃", "type": "float", "show": True, "curve": True, "min": 0, "max": 100})
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        logger = CSVLogger(Path(temporary) / "data")
        window = MainWindow(config_manager=ConfigManager(config_path), csv_logger=logger)
        window.show()
        print("实际 COM：", [p.device for p in window.manager.scan_ports()], flush=True)
        port = serial.serial_for_url("loop://", timeout=0.1)
        count = 0
        sender = QTimer()
        sender.setInterval(35)
        def send():
            nonlocal count
            if not window.manager.is_connected:
                return
            if count < 40:
                port.write(f"angle={count / 10:.2f},speed={100 + count},voltage=7.42,temperature={35 + count / 40:.2f}\r\n".encode())
                count += 1
            else:
                sender.stop()
                port.write(b"angle=2.15,speed=120,voltage=7.42,temperature=36.5\r\n")
                QTimer.singleShot(300, inspect_main)
        def inspect_main():
            assert window.parameter_widgets["temperature"].text() == "36.5 ℃"
            assert window.parameter_widgets["angle"].text() == "2.15 °"
            assert set(window.chart.curves) == {"angle", "speed", "temperature"}
            assert len(window.chart.history["temperature"]) == 41
            assert not window.error_label.isVisible(), window.error_label.text()
            window.chart.refresh()
            window.grab().save(str(ROOT / "docs" / "final-window.png"))
            window.stop_record_button.click()
            with logger.path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
            assert rows[0] == ["timestamp", "angle", "speed", "voltage", "temperature"]
            assert rows[-1][1:] == ["2.15", "120", "7.42", "36.5"]
            assert len(rows) == 42
            editor = ConfigWindow(window.config_manager, window)
            editor.show()
            def finish():
                editor.grab().save(str(ROOT / "docs" / "final-config-window.png"))
                editor.close()
                window.close()
            QTimer.singleShot(400, finish)
        sender.timeout.connect(send)
        finished = []
        def on_stopped():
            QTimer.singleShot(100, check_closed)
        def check_closed():
            assert not window.isVisible()
            assert not port.is_open
            assert not logger.is_recording
            finished.append(True)
            app.quit()
        window.manager.stopped.connect(on_stopped)
        with patch("serial_manager.serial.Serial", return_value=port):
            window.start_record_button.click()
            window.manager.connect_port("loop://", 115200)
            sender.start()
            watchdog = QTimer()
            watchdog.setSingleShot(True)
            watchdog.timeout.connect(lambda: (failures.append("native smoke timeout"), window.close()))
            watchdog.start(10000)
            app.exec()
            watchdog.stop()
        if failures or not finished:
            raise RuntimeError(f"Smoke failed: {failures}")
        print("PASS: 41 帧真实 PySerial loopback → 后台线程 → 参数显示/3 条曲线/CSV；窗口安全退出。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
