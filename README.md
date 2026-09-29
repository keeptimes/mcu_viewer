# MCU PC Monitor

Windows MCU 蓝牙串口监控工具。第 1～5 阶段已实现：串口扫描及连接、原始数据显示、JSON 参数配置、动态参数显示、参数编辑、实时曲线、CSV 记录。

## 运行

在项目目录打开 PowerShell，使用 Python 3.10 或更高版本：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

本次开发已在 `.venv` 安装 PySide6、PySerial 和 PyQtGraph，可直接执行最后一行。不需要激活虚拟环境。从其他目录用 main.py 的完整路径启动也可以，配置和数据目录始终位于本项目中。

## 使用流程

1. 在 Windows 中配对蓝牙 SPP 模块，确认设备管理器出现 COM 端口。BLE 设备需要提供虚拟串口才能使用本程序。
2. 选择端口和 MCU 波特率（默认 115200），点击“连接”。串口固定使用 8 数据位、无校验、1 停止位、无流控。
3. MCU 以 UTF-8 发送数据，每行用 `\r\n` 或 `\n` 结束，例如 `angle=2.15,speed=120,voltage=7.42`。
4. 主界面显示角度 `2.15 °`、速度 `120 rpm`、电压 `7.42 V`；默认绘制角度和速度曲线。
5. 点击“开始记录”创建 CSV，点击“停止记录”关闭文件。记录文件位于 `data/`，鼠标悬停在记录状态上可查看完整路径。
6. “清空”清除原始显示、参数当前值和曲线历史，不删除 CSV，也不停止接收或记录。

## 参数配置

默认读取 `config/config.json`。示例参数：

```json
{
  "name": "温度",
  "key": "temperature",
  "unit": "℃",
  "type": "float",
  "show": true,
  "curve": true,
  "min": 0,
  "max": 100
}
```

点击“参数配置”，添加上述参数并保存，主界面立即新增温度及曲线；MCU 发送 `temperature=36.5` 即显示 `36.5 ℃`，无需改代码或重启。

也可直接编辑 JSON 中的 `parameters`，然后点击“重载配置”。只有成功保存或重载后才刷新 UI；未保存的表格编辑不会生效。

| 字段 | 规则 |
| --- | --- |
| name | 非空显示名称 |
| key | 区分大小写；字母或下划线开头，只含英文字母、数字、下划线；不能重复；`timestamp` 保留给 CSV 时间列 |
| unit | 字符串，可为空 |
| type | `int`、`float`、`string` |
| show | 是否显示参数卡片 |
| curve | 是否绘图，与 show 独立；string 类型必须为 false |
| min / max | 参考范围，最小值不能大于最大值；可为 null；不裁剪数据、不触发报警 |

`serial.baudrate` 设置默认波特率。主界面临时选择波特率不自动写回配置。连接期间重载配置不会改变已打开串口的实际波特率。

配置损坏或不存在时显示错误，保留上一次有效配置；首次加载失败时使用空参数列表，仍可连接并查看原始数据。可以修复 JSON 后重载，或在参数配置窗口添加参数并保存。保存使用临时文件和原子替换，失败不覆盖原配置。

## 数据及曲线行为

- 每个字段独立转换，单个字段错误不影响同一行的其他有效字段。
- 未知 key 仍出现在原始数据区，但不更新参数、曲线或 CSV。
- int 接受整数文本，例如 `120`、`-2`；不把 `1.5` 或 `3e2` 截断成整数。
- float 支持小数和科学计数，拒绝 NaN、Infinity；string 保留文本值，英文逗号仍为字段分隔符。
- 空行或没有任何有效已配置字段的行不产生采样记录。重复 key 取本行最后一个成功转换的值。
- 未出现在本次数据包中的参数卡片保留最近值；对应 CSV 列留空，曲线不添加点。
- 每条曲线最多 500 点，显示刷新最多每秒 20 次，x 轴为 PC 接收经过时间。多参数共用 y 轴，各自单位见图例。
- 原始显示最多 2000 行、200000 个字符；接收队列最多 128 个数据块；协议单行最多 8192 字符。
- 数据丢失时会提示并丢弃不完整帧，避免把不连续的数字拼接成错误数据。非法 UTF-8 字节显示为替换字符。

## CSV

文件名：`data/data_YYYYMMDD_HHMMSS.csv`。同秒重复开始记录会附加 `_001` 等序号，不覆盖旧文件。

```csv
timestamp,angle,speed,voltage
10:15:21.123,2.15,120,7.42
10:15:21.163,,121,
```

首列为 PC 处理该完整数据包时的本地时间（毫秒精度），其余列按配置文件顺序，包括隐藏或未绘图的参数。文件使用带 BOM 的 UTF-8 编码，便于 Windows Excel 读取中文。

数据每秒刷新一次缓冲；停止记录、串口断开或程序正常退出时关闭文件。修改或重载配置时自动停止当前记录，以保持文件列定义一致；再次点击“开始记录”会按新配置创建文件。磁盘写入失败会提示并停止记录。

## 模块

```text
MCU_PC_Monitor/
├─ main.py               # 应用入口
├─ main_window.py        # 主界面和模块连接
├─ serial_manager.py     # 扫描、串口线程、信号及有界接收队列
├─ data_parser.py        # 按行分帧和类型转换
├─ config_manager.py     # JSON 校验、加载和原子保存
├─ config_window.py      # QTableWidget 参数编辑
├─ chart_widget.py       # PyQtGraph 曲线和固定长度历史
├─ csv_logger.py         # CSV 生命周期和写入
├─ config/config.json
├─ data/
├─ tests/
├─ docs/
├─ requirements.txt
└─ README.md
```

## 验证

```powershell
# 无硬件自动测试
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Windows 实际窗口及 PySerial 本地回环验证，自动关闭窗口
.\.venv\Scripts\python.exe tests/native_smoke.py
```

本次验证：27 项自动测试通过；本地回环完成 41 帧数据从串口线程到参数、曲线和 CSV 的完整流程。主窗口与配置窗口截图位于 `docs/final-window.png`、`docs/final-config-window.png`。本地回环使用临时配置和 CSV，不改变正常配置或记录目录。

本机已扫描到 COM7、COM8；尚未确认目标 MCU 使用哪个端口，也未进行真实蓝牙链路收数验证。蓝牙断开检测依赖 Windows 驱动报告，没有数据不自动判为断开。若驱动卡在打开操作，GUI 仍响应，退出需等待驱动返回。
