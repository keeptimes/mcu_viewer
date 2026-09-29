"""串口扫描和后台接收；所有串口 I/O 均在工作线程执行。"""

import codecs
from queue import Empty, Full, Queue

import serial
from serial.tools import list_ports
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot


class SerialWorker(QThread):
    opened = Signal()
    error = Signal(str)

    def __init__(self, port, baudrate, parent=None):
        super().__init__(parent)
        self.port = port
        self.baudrate = baudrate
        self.received = Queue(maxsize=128)
        self._gap_pending = False

    def _enqueue(self, text):
        if not text:
            return
        try:
            self.received.put_nowait((text, self._gap_pending))
            self._gap_pending = False
        except Full:
            if not self._gap_pending:
                self.error.emit("接收速度超过显示处理速度，部分原始数据已丢弃")
            self._gap_pending = True

    def run(self):
        connection = None
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            connection = serial.Serial(
                port=self.port, baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE, timeout=0.1,
                xonxoff=False, rtscts=False, dsrdtr=False,
            )
            if not self.isInterruptionRequested():
                self.opened.emit()
            while not self.isInterruptionRequested():
                chunk = connection.read(max(1, min(connection.in_waiting, 4096)))
                if chunk:
                    self._enqueue(decoder.decode(chunk))
        except Exception as exc:
            if not self.isInterruptionRequested():
                action = "打开失败（请检查端口是否存在、被占用或蓝牙是否连接）" if connection is None else "接收失败，连接已断开"
                self.error.emit(f"串口 {self.port} {action}：{exc}")
        finally:
            self._enqueue(decoder.decode(b"", final=True))
            if connection is not None:
                try:
                    connection.close()
                except Exception as exc:
                    self.error.emit(f"关闭串口失败：{exc}")


class SerialManager(QObject):
    raw_data = Signal(str)
    data_gap = Signal()
    error = Signal(str)
    state_changed = Signal(str)
    stopped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._connected = False
        self._stopping = False
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._drain)

    @property
    def is_busy(self):
        return self._worker is not None

    @property
    def is_connected(self):
        return self._connected

    def scan_ports(self):
        try:
            return sorted(list_ports.comports(), key=lambda port: port.device)
        except Exception as exc:
            self.error.emit(f"扫描串口失败：{exc}")
            return []

    def connect_port(self, port, baudrate):
        """启动连接；禁止重复连接，打开串口也不阻塞主线程。"""
        if self.is_busy:
            return
        if not port or not isinstance(baudrate, int) or baudrate <= 0:
            self.error.emit("请选择有效串口和波特率")
            return
        self._stopping = False
        self._worker = SerialWorker(port, baudrate, self)
        self._worker.opened.connect(self._on_opened)
        self._worker.error.connect(self.error)
        self._worker.finished.connect(self._on_finished)
        self.state_changed.emit("正在连接")
        self._timer.start()
        self._worker.start()

    @Slot()
    def disconnect_port(self):
        """请求中断，GUI 不调用 wait()，等 finished 信号完成清理。"""
        if self._worker is not None:
            self._stopping = True
            self.state_changed.emit("正在断开")
            self._worker.requestInterruption()

    @Slot()
    def _on_opened(self):
        if not self._stopping:
            self._connected = True
            self.state_changed.emit("已连接")

    @Slot()
    def _drain(self):
        if self._worker is None:
            return
        chunks = []
        for _ in range(128):
            try:
                text, gap_before = self._worker.received.get_nowait()
            except Empty:
                break
            if gap_before:
                if chunks:
                    self.raw_data.emit("".join(chunks))
                    chunks.clear()
                self.data_gap.emit()
            chunks.append(text)
        if chunks:
            self.raw_data.emit("".join(chunks))

    @Slot()
    def _on_finished(self):
        self._timer.stop()
        self._drain()
        worker = self._worker
        self._worker = None
        self._connected = False
        self._stopping = False
        worker.deleteLater()
        self.state_changed.emit("已断开")
        self.stopped.emit()
