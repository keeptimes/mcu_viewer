"""PyQtGraph 实时曲线：配置驱动、有界历史、批量刷新。"""

from collections import deque
from html import escape
import math
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QVBoxLayout, QWidget
import pyqtgraph as pg


class ChartWidget(QWidget):
    MAX_POINTS = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plot = pg.PlotWidget(background="w")
        self.plot.setLabel("bottom", "接收时间", units="s")
        self.plot.setLabel("left", "参数值（单位见图例）")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.legend = self.plot.addLegend()
        self.plot.setMinimumHeight(220)
        layout.addWidget(self.plot)
        self.history = {}
        self.curves = {}
        self._dirty = False
        self._origin = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def configure(self, parameters):
        """重建曲线，不保留旧配置的标签、图例或历史数据。"""
        self.plot.clear()
        self.legend.clear()
        self.history = {}
        self.curves = {}
        selected = [p for p in parameters if p["curve"] and p["type"] in ("int", "float")]
        for index, parameter in enumerate(selected):
            key = parameter["key"]
            label = escape(parameter["name"])
            if parameter["unit"]:
                label += f" ({escape(parameter['unit'])})"
            self.curves[key] = self.plot.plot(pen=pg.mkPen(pg.intColor(index, hues=max(len(selected), 1)), width=2), name=label)
            self.history[key] = deque(maxlen=self.MAX_POINTS)
        self.plot.setTitle("实时数据曲线" if selected else "实时数据曲线 — 请在参数配置中勾选曲线")
        self.plot.enableAutoRange()
        self._origin = time.monotonic()
        self._dirty = False

    def add_sample(self, values, elapsed=None):
        x = time.monotonic() - self._origin if elapsed is None else elapsed
        for key, value in values.items():
            history = self.history.get(key)
            if history is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(numeric):
                history.append((x, numeric))
                self._dirty = True

    def refresh(self):
        if not self._dirty:
            return
        for key, history in self.history.items():
            if history:
                x, y = zip(*history)
                self.curves[key].setData(list(x), list(y))
        self._dirty = False

    def clear(self):
        for key, history in self.history.items():
            history.clear()
            self.curves[key].setData([], [])
        self._origin = time.monotonic()
        self._dirty = False
