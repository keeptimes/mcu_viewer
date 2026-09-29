import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from chart_widget import ChartWidget
from test_stage2 import sample_config


class StageFourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.chart = ChartWidget()
        self.addCleanup(self.chart.close)
        self.parameters = sample_config()["parameters"]
        self.chart.configure(self.parameters)

    def test_only_curve_parameters_and_bounded_history(self):
        self.assertEqual(set(self.chart.curves), {"angle", "speed"})
        for index in range(601):
            self.chart.add_sample({"angle": index, "state": "ok"}, elapsed=index / 10)
        self.chart.refresh()
        x, y = self.chart.curves["angle"].getData()
        self.assertEqual(len(y), 500)
        self.assertEqual(y[0], 101)
        self.assertEqual(y[-1], 600)
        self.assertEqual(x[-1], 60)
        self.assertEqual(len(self.chart.history["speed"]), 0)

    def test_config_change_and_clear_remove_old_curves_and_history(self):
        self.chart.add_sample({"angle": 12}, elapsed=0)
        changed = [{"name": "温度", "key": "temperature", "unit": "℃", "type": "float", "show": False, "curve": True}]
        self.chart.configure(changed)
        self.assertEqual(set(self.chart.curves), {"temperature"})
        self.chart.add_sample({"temperature": 36.5, "angle": 42}, elapsed=1)
        self.chart.refresh()
        self.assertEqual(self.chart.curves["temperature"].getData()[1].tolist(), [36.5])
        self.chart.clear()
        self.assertEqual(len(self.chart.history["temperature"]), 0)
        x, y = self.chart.curves["temperature"].getData()
        self.assertTrue(y is None or len(y) == 0)

    def test_nonfinite_and_unplottable_values_do_not_break_chart(self):
        for value in (float("nan"), float("inf"), "bad", 10 ** 1000):
            self.chart.add_sample({"angle": value}, elapsed=0)
        self.assertEqual(len(self.chart.history["angle"]), 0)
        self.chart.add_sample({"angle": 2.15}, elapsed=1)
        self.chart.refresh()
        self.assertEqual(self.chart.curves["angle"].getData()[1].tolist(), [2.15])


if __name__ == "__main__":
    unittest.main()
