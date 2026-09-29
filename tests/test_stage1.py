import os
import time
import unittest
from collections import deque
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QThread, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import serial

from serial_manager import SerialManager
from main_window import MainWindow


class FakePort:
    def __init__(self, chunks=(), failure=False):
        self.chunks = deque(chunks)
        self.failure = failure
        self.closed = False
        self.read_thread = None

    @property
    def in_waiting(self):
        return 64

    def read(self, size):
        self.read_thread = QThread.currentThread()
        if self.chunks:
            return self.chunks.popleft()
        if self.failure:
            raise serial.SerialException("device disconnected")
        time.sleep(0.01)
        return b""

    def close(self):
        self.closed = True


class StageOneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def wait_until(self, predicate, timeout=2500):
        end = time.monotonic() + timeout / 1000
        while not predicate() and time.monotonic() < end:
            QTest.qWait(10)
        self.assertTrue(predicate(), "异步操作未在规定时间内完成")

    def setUp(self):
        self.manager = SerialManager()

    def tearDown(self):
        self.manager.disconnect_port()
        self.wait_until(lambda: not self.manager.is_busy)

    def test_fragmented_utf8_raw_data_and_reconnect(self):
        port = FakePort([b"angle=2.", b"15\r\n", b"\xe6", b"\xb8\xa9\n", b"\xff\n"])
        received = []
        self.manager.raw_data.connect(received.append)
        with patch("serial_manager.serial.Serial", return_value=port):
            self.manager.connect_port("COM9", 115200)
            self.wait_until(lambda: "".join(received).endswith("\ufffd\n"))
            self.assertEqual("".join(received), "angle=2.15\r\n温\n\ufffd\n")
            self.assertNotEqual(port.read_thread, self.app.thread())
            self.manager.disconnect_port()
            self.wait_until(lambda: not self.manager.is_busy)
            self.assertTrue(port.closed)
            self.manager.connect_port("COM9", 9600)
            self.wait_until(lambda: self.manager.is_connected)

    def test_open_failure_is_reported(self):
        errors = []
        self.manager.error.connect(errors.append)
        with patch("serial_manager.serial.Serial", side_effect=serial.SerialException("access denied")):
            self.manager.connect_port("COM9", 115200)
            self.wait_until(lambda: not self.manager.is_busy)
        self.assertIn("access denied", errors[0])
        self.assertFalse(self.manager.is_connected)

    def test_device_disconnect_closes_port(self):
        port = FakePort(failure=True)
        errors = []
        self.manager.error.connect(errors.append)
        with patch("serial_manager.serial.Serial", return_value=port):
            self.manager.connect_port("COM9", 115200)
            self.wait_until(lambda: not self.manager.is_busy)
        self.assertTrue(port.closed)
        self.assertIn("device disconnected", errors[0])

    def test_slow_open_does_not_block_gui_and_can_be_cancelled(self):
        port = FakePort()
        ticks = []
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(True))
        def slow_open(**kwargs):
            time.sleep(0.2)
            return port
        timer.start()
        try:
            with patch("serial_manager.serial.Serial", side_effect=slow_open):
                self.manager.connect_port("COM9", 115200)
                self.manager.disconnect_port()
                self.wait_until(lambda: not self.manager.is_busy)
            self.assertGreaterEqual(len(ticks), 3)
            self.assertTrue(port.closed)
            self.assertFalse(self.manager.is_connected)
        finally:
            timer.stop()

    def test_scan_failure_reports_error_without_crashing(self):
        errors = []
        self.manager.error.connect(errors.append)
        with patch("serial_manager.list_ports.comports", side_effect=OSError("scan failed")):
            self.assertEqual(self.manager.scan_ports(), [])
        self.assertIn("scan failed", errors[0])

    def test_window_receives_clears_and_closes_while_connected(self):
        port = FakePort([b"angle=2.15,speed=120,voltage=7.42\r\n"])
        with patch("serial_manager.list_ports.comports", return_value=[]):
            window = MainWindow(self.manager)
        window.show()
        with patch("serial_manager.serial.Serial", return_value=port):
            self.manager.connect_port("COM9", 115200)
            self.wait_until(lambda: "voltage=7.42" in window.raw_display.toPlainText())
            window.clear_button.click()
            self.assertEqual(window.raw_display.toPlainText(), "")
            window.close()
            self.wait_until(lambda: not window.isVisible())
        self.assertFalse(self.manager.is_busy)
        self.assertTrue(port.closed)

    def test_raw_display_is_bounded_without_newlines(self):
        with patch("serial_manager.list_ports.comports", return_value=[]):
            window = MainWindow(self.manager)
        window.append_raw_data("x" * 250000)
        self.assertLessEqual(len(window.raw_display.toPlainText()), 200000)
        window.close()


if __name__ == "__main__":
    unittest.main()
