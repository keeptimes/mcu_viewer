"""按配置列顺序记录 CSV，处理文件冲突和写入异常。"""

import csv
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal


class CSVLogger(QObject):
    error = Signal(str)
    state_changed = Signal(bool)

    def __init__(self, data_dir=None, parent=None):
        super().__init__(parent)
        self.data_dir = Path(data_dir) if data_dir is not None else Path(__file__).resolve().parent / "data"
        self.path = None
        self._file = None
        self._writer = None
        self._keys = []
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(1000)
        self._flush_timer.timeout.connect(self.flush)

    @property
    def is_recording(self):
        return self._file is not None

    def start(self, parameters):
        if self.is_recording:
            return False
        keys = [parameter["key"] for parameter in parameters]
        if not keys or len(keys) != len(set(keys)) or "timestamp" in keys:
            self.error.emit("无法开始记录：参数为空、Key 重复或使用保留名 timestamp")
            return False
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            stem = datetime.now().strftime("data_%Y%m%d_%H%M%S")
            suffix = 0
            while True:
                path = self.data_dir / f"{stem}{'_' + str(suffix).zfill(3) if suffix else ''}.csv"
                try:
                    # x 模式绝不覆盖同秒创建或已有的数据文件。
                    self._file = path.open("x", encoding="utf-8-sig", newline="")
                    self.path = path
                    break
                except FileExistsError:
                    suffix += 1
            self._keys = keys
            self._writer = csv.DictWriter(self._file, fieldnames=["timestamp", *keys], extrasaction="ignore")
            self._writer.writeheader()
            self._file.flush()
        except (OSError, ValueError, csv.Error) as exc:
            self.error.emit(f"创建 CSV 失败：{exc}")
            self.stop()
            return False
        self._flush_timer.start()
        self.state_changed.emit(True)
        return True

    def write_sample(self, values, timestamp=None):
        """每个有效协议包一行，缺失值留空，不沿用上次采样值。"""
        if not self.is_recording:
            return
        stamp = (timestamp or datetime.now()).strftime("%H:%M:%S.%f")[:-3]
        row = {key: values.get(key, "") for key in self._keys}
        row["timestamp"] = stamp
        try:
            self._writer.writerow(row)
        except (OSError, ValueError, csv.Error) as exc:
            self.error.emit(f"写入 CSV 失败，已停止记录：{exc}")
            self.stop()

    def flush(self):
        if self._file is not None:
            try:
                self._file.flush()
            except (OSError, ValueError) as exc:
                self.error.emit(f"刷新 CSV 失败，已停止记录：{exc}")
                self.stop()

    def stop(self):
        """close 会刷新缓冲；即使关闭失败，也恢复 UI 的非记录状态。"""
        self._flush_timer.stop()
        stream = self._file
        self._file = None
        self._writer = None
        if stream is not None:
            try:
                stream.close()
            except (OSError, ValueError) as exc:
                self.error.emit(f"关闭 CSV 失败，末尾数据可能未保存：{exc}")
            finally:
                self.state_changed.emit(False)
