"""使用表格编辑参数，保存成功后由 ConfigManager 通知主窗口。"""

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)


class ConfigWindow(QDialog):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._config = config_manager.config
        self.setWindowTitle("参数配置")
        self.resize(940, 480)
        layout = QVBoxLayout(self)
        hint = QLabel("Key 与 MCU 字段一致且不能重复；string 不支持曲线。最小/最大值为参考范围，可留空。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["参数名称", "Key", "单位", "类型", "显示", "曲线", "最小值", "最大值"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.table)
        self.message_label = QLabel()
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("添加参数")
        self.delete_button = QPushButton("删除参数")
        self.save_button = QPushButton("保存配置")
        close_button = QPushButton("关闭")
        for button in (self.add_button, self.delete_button, self.save_button, close_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.add_button.clicked.connect(self.add_parameter)
        self.delete_button.clicked.connect(self.delete_parameters)
        self.save_button.clicked.connect(self.save_config)
        close_button.clicked.connect(self.reject)
        self.config_manager.error.connect(self.show_error)
        for parameter in self._config["parameters"]:
            self._insert_parameter(parameter)

    def _insert_parameter(self, parameter):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, field in ((0, "name"), (1, "key"), (2, "unit"), (6, "min"), (7, "max")):
            value = parameter.get(field)
            self.table.setItem(row, column, QTableWidgetItem("" if value is None else str(value)))
        combo = QComboBox()
        combo.addItems(["float", "int", "string"])
        combo.setCurrentText(parameter["type"])
        self.table.setCellWidget(row, 3, combo)
        for column, field in ((4, "show"), (5, "curve")):
            item = QTableWidgetItem()
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if parameter[field] else Qt.CheckState.Unchecked)
            self.table.setItem(row, column, item)

    @Slot()
    def add_parameter(self):
        self._insert_parameter({"name": "新参数", "key": "", "unit": "", "type": "float", "show": True, "curve": False})
        row = self.table.rowCount() - 1
        self.table.setCurrentCell(row, 1)
        self.table.scrollToItem(self.table.item(row, 1))

    @Slot()
    def delete_parameters(self):
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)

    @Slot(str)
    def show_error(self, message):
        self.message_label.setStyleSheet("color: #b42318;")
        self.message_label.setText(message)

    @Slot()
    def save_config(self):
        parameters = []
        try:
            for row in range(self.table.rowCount()):
                parameter = {field: self.table.item(row, column).text().strip()
                             for column, field in ((0, "name"), (1, "key"), (2, "unit"))}
                parameter["type"] = self.table.cellWidget(row, 3).currentText()
                for column, field in ((4, "show"), (5, "curve")):
                    parameter[field] = self.table.item(row, column).checkState() == Qt.CheckState.Checked
                for column, field in ((6, "min"), (7, "max")):
                    text = self.table.item(row, column).text().strip()
                    try:
                        parameter[field] = float(text) if text else None
                    except ValueError:
                        raise ValueError(f"第 {row + 1} 行{field}必须是数字或留空") from None
                parameters.append(parameter)
            config = self.config_manager.config
            config["parameters"] = parameters
            if self.config_manager.save(config):
                self._config = config
                self.message_label.setStyleSheet("color: #16753d;")
                self.message_label.setText("已保存，主界面已刷新。")
        except ValueError as exc:
            self.show_error(str(exc))
