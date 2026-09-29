# 第 2～5 阶段验证记录

日期：2026-09-29。各阶段均完成运行验证后再进入下一阶段。

| 阶段 | 完成内容 | 当阶段累计自动测试 |
| --- | --- | --- |
| 2 | 配置加载/校验、解析分帧、动态参数；JSON 新增 temperature 自动显示 | 12 通过 |
| 3 | QTableWidget 添加、删除、修改、保存及即时刷新；原子保存失败保留原配置 | 16 通过 |
| 4 | PyQtGraph 按配置建曲线、每条 500 点、清空及配置重建 | 19 通过 |
| 5 | CSV 表头顺序、缺失值、时间戳、防覆盖、异常停止及退出关闭 | 25 通过 |
| 综合回归 | 修复分段 CRLF 多余空行、溢出时不连续数字拼接 | 27 通过 |

## 原生窗口与回环验证

运行 `python tests/native_smoke.py`，使用真实 PySerial `loop://` 传输 41 帧，由实际 QThread 接收并驱动主窗口。

- angle 显示 `2.15 °`，speed 显示 `120 rpm`，voltage 显示 `7.42 V`。
- 临时配置新增 temperature 后显示 `36.5 ℃`，曲线自动包含 temperature。
- 曲线只包含 angle、speed、temperature，不包含 voltage。
- CSV 为 1 行表头 + 41 行数据，末行数值正确，列顺序与配置一致。
- 打开并截图检查原生主窗口和配置窗口，内容无裁切，控件可见。
- 窗口关闭后串口和 CSV 均关闭，进程以 0 退出。
- 实际 COM 扫描仍为 COM7、COM8。未对目标 MCU 真实蓝牙链路进行验收。

脚本使用临时目录，不将模拟温度配置写进默认配置，也不在正常 data/ 中创建模拟记录。

## 复现命令

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests/native_smoke.py
```
