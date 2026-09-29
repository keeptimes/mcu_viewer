"""有界文本分帧和配置驱动的字段转换。"""

import math
import re
from PySide6.QtCore import QObject, Signal


class DataParser(QObject):
    data_received = Signal(dict)
    error = Signal(str)
    MAX_LINE_LENGTH = 8192

    def __init__(self, parameters=(), parent=None):
        super().__init__(parent)
        self.set_parameters(parameters)

    def set_parameters(self, parameters):
        self._types = {parameter["key"]: parameter["type"] for parameter in parameters}
        self.reset()

    def reset(self):
        self._buffer = ""
        self._discarding = False

    def discard_partial(self):
        """数据丢失后丢弃至下个换行，避免把不连续的数据拼成有效值。"""
        self._buffer = ""
        self._discarding = True

    def parse_line(self, line):
        result = {}
        invalid = []
        for field in line.strip().split(","):
            if not field.strip():
                continue
            if "=" not in field:
                invalid.append(field[:40])
                continue
            key, value = (part.strip() for part in field.split("=", 1))
            if not key:
                invalid.append("空 Key")
                continue
            value_type = self._types.get(key)
            if value_type is None:
                continue
            try:
                if value_type == "int":
                    if not re.fullmatch(r"[+-]?[0-9]+", value):
                        raise ValueError
                    converted = int(value)
                elif value_type == "float":
                    converted = float(value)
                    if not math.isfinite(converted):
                        raise ValueError
                else:
                    converted = value
                result[key] = converted
            except (ValueError, OverflowError):
                invalid.append(key)
        if invalid:
            self.error.emit("忽略非法数据字段：" + "、".join(invalid[:5]))
        return result

    def feed(self, text):
        """只在完整换行后发布样本；超长行丢弃到下一行恢复。"""
        pieces = text.split("\n")
        for index, piece in enumerate(pieces):
            complete = index < len(pieces) - 1
            if not self._discarding:
                if len(self._buffer) + len(piece) > self.MAX_LINE_LENGTH:
                    self._buffer = ""
                    self._discarding = True
                    self.error.emit("串口单行超过 8192 字符，已丢弃该行")
                else:
                    self._buffer += piece
            if complete:
                if not self._discarding:
                    values = self.parse_line(self._buffer.rstrip("\r"))
                    if values:
                        self.data_received.emit(values)
                self._buffer = ""
                self._discarding = False
