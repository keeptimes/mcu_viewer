"""JSON 配置加载、校验和变更通知。"""

import copy
import json
import math
import os
from pathlib import Path
import re
import tempfile

from PySide6.QtCore import QObject, Signal


class ConfigManager(QObject):
    error = Signal(str)
    config_changed = Signal(dict)

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.path = Path(path) if path is not None else Path(__file__).resolve().parent / "config" / "config.json"
        self._config = {"serial": {"baudrate": 115200}, "parameters": []}

    @property
    def config(self):
        return copy.deepcopy(self._config)

    @staticmethod
    def validate(config):
        """整体校验，拒绝重复 key 和含糊的类型，避免部分配置生效。"""
        if not isinstance(config, dict) or not isinstance(config.get("serial"), dict):
            raise ValueError("配置必须包含 serial 对象")
        baudrate = config["serial"].get("baudrate")
        if type(baudrate) is not int or not 0 < baudrate <= 4000000:
            raise ValueError("serial.baudrate 必须为 1～4000000 的整数")
        parameters = config.get("parameters")
        if not isinstance(parameters, list):
            raise ValueError("parameters 必须为数组")
        keys = set()
        for index, parameter in enumerate(parameters, 1):
            prefix = f"第 {index} 个参数"
            if not isinstance(parameter, dict):
                raise ValueError(f"{prefix}必须为对象")
            key = parameter.get("key")
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ValueError(f"{prefix} Key 必须为字母或下划线开头的英文标识符")
            if key in keys or key == "timestamp":
                raise ValueError(f"{prefix} Key 重复或使用保留名 timestamp：{key}")
            keys.add(key)
            if not isinstance(parameter.get("name"), str) or not parameter["name"].strip():
                raise ValueError(f"{prefix}名称不能为空")
            if not isinstance(parameter.get("unit"), str):
                raise ValueError(f"{prefix}单位必须为字符串")
            if parameter.get("type") not in ("float", "int", "string"):
                raise ValueError(f"{prefix}类型只能为 float、int、string")
            for flag in ("show", "curve"):
                if type(parameter.get(flag)) is not bool:
                    raise ValueError(f"{prefix} {flag} 必须为 true 或 false")
            if parameter["type"] == "string" and parameter["curve"]:
                raise ValueError(f"{prefix}为 string 类型，不能绘制数值曲线")
            for bound in ("min", "max"):
                value = parameter.get(bound)
                if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                    raise ValueError(f"{prefix} {bound} 必须为有限数字或 null")
            low, high = parameter.get("min"), parameter.get("max")
            if low is not None and high is not None and low > high:
                raise ValueError(f"{prefix}最小值不能大于最大值")
        return copy.deepcopy(config)

    def load(self):
        """失败时保留上一次有效配置，也不覆盖损坏的磁盘文件。"""
        try:
            config = json.loads(self.path.read_text(encoding="utf-8-sig"))
            validated = self.validate(config)
        except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
            self.error.emit(f"读取配置失败（{self.path.name}）：{exc}")
            return False
        self._config = validated
        self.config_changed.emit(self.config)
        return True

    def save(self, config):
        """在同目录写临时文件并原子替换，成功后才发布新配置。"""
        temporary = None
        try:
            validated = self.validate(config)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix="config-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(validated, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
            self.error.emit(f"保存配置失败：{exc}")
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        self._config = validated
        self.config_changed.emit(self.config)
        return True
