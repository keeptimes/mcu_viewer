"""主窗口：串口控制、配置驱动的参数显示及原始文本。"""

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget, QGridLayout, QGroupBox, QScrollArea, QSplitter,
)

from serial_manager import SerialManager
from config_manager import ConfigManager
from data_parser import DataParser
from config_window import ConfigWindow
from chart_widget import ChartWidget
from csv_logger import CSVLogger


class MainWindow(QMainWindow):
    def __init__(self, serial_manager=None, config_manager=None, csv_logger=None):
        super().__init__()
        self.setWindowTitle("MCU 串口蓝牙数据监控")
        self.resize(1100, 720)
        self.manager = serial_manager or SerialManager(self)
        self.config_manager = config_manager or ConfigManager(parent=self)
        self.parser = DataParser(parent=self)
        self.logger = csv_logger or CSVLogger(parent=self)
        self.parameter_widgets = {}
        self._parameters = {}
        self._closing = False
        self._raw_ended_with_cr = False

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        controls = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(250)
        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        self.baud_combo.addItems(["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self.baud_combo.setCurrentText("115200")
        self.refresh_button = QPushButton("刷新")
        self.connect_button = QPushButton("连接")
        self.config_button = QPushButton("参数配置")
        self.reload_button = QPushButton("重载配置")
        for widget in (QLabel("串口"), self.port_combo, QLabel("波特率"), self.baud_combo, self.refresh_button, self.connect_button, self.config_button, self.reload_button):
            controls.addWidget(widget)
        controls.addStretch()
        layout.addLayout(controls)
        self.parameter_scroll = QScrollArea()
        self.parameter_scroll.setWidgetResizable(True)
        self.parameter_scroll.setMinimumHeight(110)
        self.parameter_scroll.setMaximumHeight(230)
        layout.addWidget(self.parameter_scroll)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.chart = ChartWidget()
        splitter.addWidget(self.chart)
        raw_panel = QWidget()
        raw_layout = QVBoxLayout(raw_panel)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.addWidget(QLabel("原始串口数据（UTF-8）"))
        self.raw_display = QPlainTextEdit()
        self.raw_display.setReadOnly(True)
        self.raw_display.setMaximumBlockCount(2000)
        raw_layout.addWidget(self.raw_display)
        splitter.addWidget(raw_panel)
        splitter.setSizes([340, 160])
        layout.addWidget(splitter, 1)
        self.error_label = QLabel()
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b42318;")
        self.error_label.hide()
        layout.addWidget(self.error_label)
        self.clear_button = QPushButton("清空")
        self.start_record_button = QPushButton("开始记录")
        self.stop_record_button = QPushButton("停止记录")
        self.stop_record_button.setEnabled(False)
        self.record_label = QLabel("未记录")
        self.record_label.setTextFormat(Qt.TextFormat.PlainText)
        self.record_label.setWordWrap(True)
        bottom = QHBoxLayout()
        bottom.addWidget(self.start_record_button)
        bottom.addWidget(self.stop_record_button)
        bottom.addWidget(self.clear_button)
        bottom.addWidget(self.record_label, 1)
        bottom.addStretch()
        layout.addLayout(bottom)

        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.toggle_connection)
        self.config_button.clicked.connect(self.open_config)
        self.reload_button.clicked.connect(self.config_manager.load)
        self.clear_button.clicked.connect(self.clear_display)
        self.start_record_button.clicked.connect(self.start_recording)
        self.stop_record_button.clicked.connect(self.logger.stop)
        self.logger.error.connect(self.show_error)
        self.logger.state_changed.connect(self.update_recording_state)
        self.manager.raw_data.connect(self.receive_raw_data)
        self.manager.data_gap.connect(self.parser.discard_partial)
        self.manager.error.connect(self.show_error)
        self.manager.state_changed.connect(self.update_state)
        self.manager.stopped.connect(self._on_stopped)
        self.config_manager.error.connect(self.show_error)
        self.config_manager.config_changed.connect(self.apply_config)
        self.parser.error.connect(self.show_error)
        self.parser.data_received.connect(self.update_parameters)
        self.parser.data_received.connect(self.chart.add_sample)
        self.parser.data_received.connect(self.logger.write_sample)
        self.refresh_ports()
        self.apply_config(self.config_manager.config)
        self.config_manager.load()

    @Slot()
    def open_config(self):
        editor = ConfigWindow(self.config_manager, self)
        editor.exec()
        editor.deleteLater()

    @Slot(dict)
    def apply_config(self, config):
        if self.logger.is_recording:
            self.logger.stop()
            self.record_label.setText("配置已变更，当前记录已停止；可开始新记录。")
        self.parser.set_parameters(config["parameters"])
        self.chart.configure(config["parameters"])
        self._parameters = {parameter["key"]: parameter for parameter in config["parameters"]}
        self.parameter_widgets = {}
        panel = QWidget()
        grid = QGridLayout(panel)
        for parameter in config["parameters"]:
            if not parameter["show"]:
                continue
            group = QGroupBox(parameter["name"])
            box = QVBoxLayout(group)
            label = QLabel("—")
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setStyleSheet("font-size: 22px;")
            box.addWidget(label)
            position = len(self.parameter_widgets)
            grid.addWidget(group, position // 4, position % 4)
            self.parameter_widgets[parameter["key"]] = label
        if not self.parameter_widgets:
            grid.addWidget(QLabel("尚无显示参数，请检查配置文件或添加参数。"), 0, 0)
        old = self.parameter_scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.parameter_scroll.setWidget(panel)
        if not self.manager.is_busy:
            self.baud_combo.setCurrentText(str(config["serial"]["baudrate"]))
        self.start_record_button.setEnabled(bool(config["parameters"]))

    @Slot()
    def start_recording(self):
        self.logger.start(self.config_manager.config["parameters"])

    @Slot(bool)
    def update_recording_state(self, recording):
        self.start_record_button.setEnabled(not recording and bool(self._parameters))
        self.stop_record_button.setEnabled(recording)
        path = self.logger.path
        self.record_label.setText(f"{'记录中' if recording else '已停止'}：{path.name}" if path else "未记录")
        self.record_label.setToolTip(str(path) if path else "")

    @Slot(str)
    def receive_raw_data(self, text):
        self.append_raw_data(text)
        self.parser.feed(text)

    @Slot()
    def clear_display(self):
        self.raw_display.clear()
        self._raw_ended_with_cr = False
        self.chart.clear()
        for label in self.parameter_widgets.values():
            label.setText("—")

    @Slot(dict)
    def update_parameters(self, values):
        for key, value in values.items():
            label = self.parameter_widgets.get(key)
            if label is not None:
                unit = self._parameters[key]["unit"]
                label.setText(f"{value} {unit}".rstrip())

    @Slot()
    def refresh_ports(self):
        selected = self.port_combo.currentData()
        self.port_combo.clear()
        for port in self.manager.scan_ports():
            self.port_combo.addItem(f"{port.device} — {port.description}", port.device)
        index = self.port_combo.findData(selected)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)
        self.connect_button.setEnabled(self.port_combo.count() > 0)
        self.statusBar().showMessage("未连接" if self.port_combo.count() else "未发现 COM 串口，请连接设备或完成蓝牙 SPP 配对后刷新")

    @Slot()
    def toggle_connection(self):
        if self.manager.is_busy:
            self.manager.disconnect_port()
            return
        try:
            baudrate = int(self.baud_combo.currentText())
            if not 0 < baudrate <= 4000000:
                raise ValueError
        except ValueError:
            self.show_error("波特率必须为 1～4000000 的整数")
            return
        self.error_label.hide()
        self.manager.connect_port(self.port_combo.currentData(), baudrate)

    @Slot(str)
    def append_raw_data(self, text):
        """保留原始换行，限制总字符数，避免无换行输入无限占用内存。"""
        if not text:
            return
        previous_cr = self._raw_ended_with_cr
        self._raw_ended_with_cr = text.endswith("\r")
        if previous_cr and text.startswith("\n"):
            text = text[1:]
        scrollbar = self.raw_display.verticalScrollBar()
        follow = scrollbar.value() >= scrollbar.maximum()
        cursor = QTextCursor(self.raw_display.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text.replace("\r\n", "\n").replace("\r", "\n"))
        excess = self.raw_display.document().characterCount() - 1 - 200000
        if excess > 0:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, excess)
            cursor.removeSelectedText()
        if follow:
            scrollbar.setValue(scrollbar.maximum())

    @Slot(str)
    def show_error(self, message):
        self.error_label.setText(message)
        self.error_label.show()

    @Slot(str)
    def update_state(self, state):
        if state in ("正在连接", "已断开"):
            self.parser.reset()
            self._raw_ended_with_cr = False
        if state == "已断开":
            self.logger.stop()
        busy = self.manager.is_busy
        self.port_combo.setEnabled(not busy)
        self.baud_combo.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
        self.connect_button.setText("断开" if busy else "连接")
        self.connect_button.setEnabled(state != "正在断开" and (busy or self.port_combo.count() > 0))
        self.statusBar().showMessage(state)

    @Slot()
    def _on_stopped(self):
        if self._closing:
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        if self.manager.is_busy:
            self._closing = True
            self.manager.disconnect_port()
            self.statusBar().showMessage("正在关闭串口，请稍候…")
            event.ignore()
        else:
            self.logger.stop()
            event.accept()
