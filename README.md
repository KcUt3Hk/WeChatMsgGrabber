因为最近一段的经历，想导出微信聊天记录分析下内容，但是发现多个工具都因合规问题被迫删库了。
在揣着小鱼干去喂小猫的路上，突然想到可以用最笨的方式去处理，定位聊天窗口 - 滑动窗口 - 截图 - ORC识别文字 - 导出文字。
相比破解本地的微信备份记录，这种方案更安全，没有合规问题；缺点是处理速度慢，不能100%精准识别。

已知的未处理问题：缺少大量测试；分享内容的识别，没有整合；引用消息回复，会识别出备注名（正常是sender），等。
## 关于后续优化：提升性能和稳定性
- 分享内容的识别优化；
- 大量消息处理优化，提高稳定性；
- 优化消息去重逻辑，避免重复导出；
- 等。
## 关于后续版本：增加信息处理能力
- 接入大语言模型，通过文字分析情绪变化趋势、情感分析、性格分析（预置性格分析模型，MBTI等）；
- 智能生成回复提示词（分析女友当前情绪，提供回复建议，等）；
- 等。

工具解决不了全部问题，真诚有效沟通还有可能。

另外，**该程序完全由AI生成**（耗时5天，其中有1天半花费在如何使用GitHub，以及处理报错），没有一行代码是我写的（仍处于 print hello world 的水平），只有前面这部分描述是我本人写的。

# 微信聊天记录获取助手（WeChatMsgGrabber）
文档结构概览：
1. 项目介绍
2. 系统要求与依赖
3. 使用指南
   3.1 一键自动化脚本
   3.2 桌面应用
   3.3 网页预览
4. 其他补充说明

下文命令以 python3 为示例；请根据本地环境（如 Windows 使用 py 或 python）适当调整。

---

## 1. 项目介绍

核心功能：
- 从微信聊天窗口自动截屏，进行 OCR 识别并解析为结构化消息对象（Message）
- 支持自动滚动、渐进式滑动与智能终止检测，覆盖基础与高级两类扫描方式
- 提供 CLI、简易桌面 UI（Tkinter）与网页预览/配置服务，满足不同使用场景
- 多格式导出（JSON/CSV/TXT/Markdown）与持久化去重索引，便于批量处理与复用

目标用户与应用场景：
- 测试工程师：快速采集聊天记录用于测试数据或回归分析
- 数据分析/研究人员：将聊天内容结构化导出，便于进一步统计或建模
- 合规与存档：按需批量导出特定群/会话，作为归档或留痕材料

主要技术栈与架构概述：
- 语言与运行时：Python 3.12
- 核心库：PaddleOCR、OpenCV、Pillow、pyautogui、pygetwindow、pandas、PyYAML
- 前端/界面：Tkinter 简易桌面 UI；网页预览基于内置 http.server 提供静态页面与 API
- 代码结构（模块职责）：
  - controllers/main_controller.py：总控流程（滚动→截图→预处理→OCR→解析→去重→保存）
  - services/auto_scroll_controller.py：基础滚动与窗口控制
  - services/advanced_scroll_controller.py：渐进式滚动、速率控制、边缘检测
  - services/image_preprocessor.py：图像增强/去噪，提升 OCR 识别质量
  - services/ocr_processor.py：区域检测与文本识别、指标采集
  - services/message_parser.py：将识别到的文本区域解析为 Message 列表
  - services/storage_manager.py：按配置保存为多种格式，并维护去重索引
  - services/config_manager.py / models/config.py：加载/管理应用与输出配置
  - ui/simple_gui.py：桌面应用（Tkinter）
  - web/config_server.py：本地配置服务与网页预览（docs/ui_preview.html）

数据流概览：
- 自动滚动或定位聊天区域 → 截图 → 图像预处理 → OCR 区域识别与文本提取 → 文本解析为消息 → 批内与跨批次去重 → 多格式导出与索引维护。

示例：以 MainController 为入口的代码演示（带函数级注释）

```python
from controllers.main_controller import MainController
from ui.progress import ProgressReporter
from models.data_models import Message


def demo_run_once() -> list[Message]:
    """
    单次提取当前聊天视图并解析为消息列表。

    流程：
    - 若提供了聊天区域覆盖坐标，则跳过窗口定位与激活；
    - 捕获截图、进行预处理与 OCR；
    - 将文本区域解析为 Message 对象列表并返回。
    """
    ctrl = MainController()
    return ctrl.run_once()


def demo_run_with_retry() -> list[Message]:
    """
    带重试机制的提取：在空结果或异常时按指定次数重试。

    参数要点：
    - max_attempts: 最大尝试次数（默认 3）
    - delay_seconds: 每次尝试之间的等待时间（默认 0.5 秒）
    """
    ctrl = MainController()
    return ctrl.run_with_retry(max_attempts=3, delay_seconds=0.5)


def demo_run_with_progress() -> list[Message]:
    """
    带进度上报的提取：在 CLI 或日志中显示尝试次数、解析条数与状态。
    """
    ctrl = MainController()
    reporter = ProgressReporter()
    return ctrl.run_with_progress(reporter, max_attempts=3, delay_seconds=0.5)


def demo_scan_chat_history() -> list[Message]:
    """
    基础扫描聊天历史：按方向滚动，批次捕获与解析，支持批内去重与智能边缘检测。

    关键参数：
    - max_messages: 目标最大消息数量（默认 1000）
    - direction: 滚动方向（"up"/"down"）
    - reporter: 可选的进度上报器
    """
    ctrl = MainController()
    return ctrl.scan_chat_history(max_messages=300, direction="up", reporter=ProgressReporter())


def demo_advanced_scan_chat_history() -> list[Message]:
    """
    高级扫描：使用 AdvancedScrollController 渐进式滚动与速率控制，支持目标内容命中提前停止。

    关键参数：
    - max_scrolls: 最大滚动次数（默认 100）
    - direction: 滚动方向（"up"/"down"）
    - target_content: 命中该文本内容时提前终止（可选）
    - stop_at_edges: 到达边缘时停止（默认 True）
    - scroll_speed/scroll_delay/scroll_distance_range/scroll_interval_range/max_scrolls_per_minute: 可选滚动参数覆盖
    """
    ctrl = MainController()
    return ctrl.advanced_scan_chat_history(
        max_scrolls=60,
        direction="up",
        target_content=None,
        stop_at_edges=True,
        reporter=ProgressReporter(),
        scroll_speed=2,
        scroll_delay=0.8,
        scroll_distance_range=(150, 280),
        scroll_interval_range=(0.2, 0.5),
        max_scrolls_per_minute=40,
    )


def demo_scan_multiple_chats() -> list[Message]:
    """
    批量扫描多个会话标题：侧边栏 OCR 模糊匹配点击会话，聚合并去重，支持多格式保存。

    关键参数：
    - chat_titles: 需要扫描的会话列表（支持模糊匹配）
    - per_chat_max_messages: 每个会话最多提取条数
    - direction: 每个会话内的滚动方向（"up"/"down"）
    - formats/filename_prefix/output_dir: 覆盖导出控制
    """
    ctrl = MainController()
    return ctrl.scan_multiple_chats(
        chat_titles=["产品群", "项目讨论", "同事小王"],
        per_chat_max_messages=200,
        direction="up",
        formats=["json", "csv", "md"],
        filename_prefix="batch_demo",
        output_dir="./output",
        reporter=ProgressReporter(),
    )


def demo_run_and_save() -> list[Message]:
    """
    组合流程：先执行一次提取（可选重试与进度上报），再按 OutputConfig 保存到指定格式与目录。

    关键参数：
    - filename_prefix: 导出文件名前缀（默认 extraction）
    - use_retry/max_attempts/delay_seconds: 重试控制
    - reporter: 进度上报器（可选）
    - output_override: 覆盖默认输出配置（可选）
    """
    ctrl = MainController()
    return ctrl.run_and_save(
        filename_prefix="extraction_demo",
        use_retry=True,
        max_attempts=3,
        delay_seconds=0.5,
        reporter=ProgressReporter(),
    )


if __name__ == "__main__":
    # 按需调用上述函数进行演示
    msgs = demo_run_with_progress()
    print(f"解析到消息条数: {len(msgs)}")
```

运行示例：

```bash
python3 -c "from controllers.main_controller import MainController; from ui.progress import ProgressReporter; print(len(MainController().run_with_progress(ProgressReporter())))"
```

---

### 快速导航与本地预览（UI 页面）

若需快速预览样式与说明，可直接启动静态页面服务；如需保存/加载配置与指标接口，请使用开发者服务器。

1) 静态预览（仅 UI 样式与说明，不调用 API）

```bash
# 通用（推荐）：
python3 -m http.server 8002 --directory docs
open http://localhost:8002/ui_preview.html

# 或使用绝对路径示例：
$HOME/Projects/Setting/python_envs/bin/python3.12 -m http.server 8002 --directory docs
open http://localhost:8002/ui_preview.html
```

2) 开发者服务器联动（带配置保存与指标接口）

```bash
# 推荐默认端口
python3 web/config_server.py --port 8003
open http://localhost:8003/ui_preview.html

# 或使用绝对路径示例：
$HOME/Projects/Setting/python_envs/bin/python3.12 web/config_server.py --port 8003
open http://localhost:8003/ui_preview.html

# 如端口被占用，可改用 8010：
python3 web/config_server.py --port 8010
open http://localhost:8010/ui_preview.html
```

与页面一致的模块索引（静态预览端口示例 8002）：
- 1. 使用指南：一键自动化脚本 → http://localhost:8002/ui_preview.html#module-guide-cli
- 2. 使用指南：桌面应用 → http://localhost:8002/ui_preview.html#module-guide-desktop
- 3. 使用指南：网页预览 → http://localhost:8002/ui_preview.html#module-guide-web

提示：静态预览请访问根路径下的 ui_preview.html（不要带 /docs/ 前缀），否则可能出现 404。

---

## 2. 系统要求与依赖

运行环境要求：
- 操作系统：macOS 13 及以上（建议），需图形界面与必要权限可用。
- 硬件建议：内存建议≥8GB；磁盘剩余空间≥2GB（用于 OCR 模型与导出）。
- 权限：
  - 系统设置 → 隐私与安全 → 屏幕录制：允许终端或 Python 解释器进行录屏；
  - 系统设置 → 隐私与安全 → 辅助功能：允许终端或 Python 解释器控制鼠标/键盘与窗口；
  - 建议将正在使用的终端或 Python 解释器加入上述权限白名单。

核心依赖（requirements.txt）：
- paddlepaddle>=2.4.0
- paddleocr>=2.6.0
- opencv-python>=4.5.0
- Pillow>=8.0.0
- pyautogui>=0.9.53
- pygetwindow>=0.0.9
- pandas>=1.3.0
- PyYAML>=6.0

测试相关（可选，用于本仓库测试与网页预览的验证）：
- pytest>=7.0.0, pytest-cov>=4.0.0, pytest-xdist, pytest-html>=4.0.0
- playwright>=1.45.0（若运行 UI 自动化测试）

依赖安装与基础配置：
```bash
# 安装核心依赖（建议）
python3 -m pip install -r requirements.txt

#（可选）安装与初始化 Playwright 以运行网页/UI 自动化测试
python3 -m pip install playwright
python3 -m playwright install
```

GPU 加速（可选）：
- PaddleOCR 在部分设备上支持 GPU；若启用需正确安装对应 GPU 版本的 paddlepaddle 并配置驱动。
- 本项目默认 CPU 运行即可，M2 Max 等设备的 CPU 性能通常足够完成常规聊天记录识别。

---

## 3. 使用指南

### 3.2 桌面应用

桌面 UI 提供参数设置、预览与一键扫描能力，适合非命令行用户或需要交互式调试的场景。

安装与配置：
1) 确认本机可用的 Python 解释器（例如命令 `python3`）
2) 安装 Pillow（若尚未安装）：
```bash
python3 -m pip install --upgrade pip Pillow
```

启动应用：
```bash
# 正常模式
python3 ui/simple_gui.py

# 安全模式（若遇到窗口控制/权限问题）
SAFE_MODE=1 python3 ui/simple_gui.py
```

基本操作指南：
- 在 UI 中设置窗口标题（如“微信/WeChat”）、聊天区域坐标（x,y,w,h）、OCR 语言（ch/en/japan/korean）与输出目录。
- 点击“开始扫描/开始采集”，观察进度条与日志提示，等待导出完成。
- 打开输出目录，检查生成的 JSON/CSV/TXT/Markdown 文件与截图。

常见功能说明：
- 聊天区域覆盖：在受限环境下可直接提供区域坐标，跳过窗口定位与激活流程。
- 进度显示：在界面或终端日志中显示解析条数与状态；异常时给出提示。
- 安全模式：降低对窗口 API 的依赖，增强在受限或权限不足环境中的稳定性。

截图参考：网页预览页面（docs/ui_preview.html）中提供 UI 布局示意与“复制启动命令”按钮，可用作视觉参考。

子节：安全模式与解释器选择（桌面 UI）

- 异常退出自动重试：当子进程出现异常（如退出码 -9/134/139 或输出包含 Killed/Abort trap/Segmentation fault），桌面 UI 将自动切换为“安全模式”并重试。
- 安全模式行为：在 Python 启动命令中追加参数 -S -E，并设置环境变量以提升稳健性（例如 PYTHONNOUSERSITE=1、PYTHONDONTWRITEBYTECODE=1、WX_SAFE_MODE=1）。
- 解释器选择优先级：WX_PYTHON_BIN > python3.12（若可用）> 当前进程解释器；如需固定使用本机虚拟环境解释器，可在终端导出 WX_PYTHON_BIN 后运行。
- 常规建议：仅在检测到异常退出时自动启用安全模式；常规环境下保持正常模式以获得完整功能与最佳性能。

### 3.1 一键自动化脚本

该脚本专为“直接在终端运行”的场景设计，提供自动窗口定位、自然滚动、OCR 识别与多格式结构化输出。

示例命令（auto_wechat_scan.py）：
```bash
python3 cli/auto_wechat_scan.py \
  --direction up \
  --max-scrolls 60 \
  --max-scrolls-per-minute 40 \
  --full-fetch \
  --formats json,csv,md \
  --output ./output \
  --filename-prefix auto_scan_$(date +%Y%m%d_%H%M%S) \
  --verbose
```

常用覆盖参数：
- --window-title 指定窗口标题子串（如 “微信” 或 “WeChat”），辅助定位窗口
- --chat-area 指定聊天区域坐标（x,y,width,height），在窗口定位困难时直接覆盖区域
- --ocr-lang OCR 语言覆盖（ch/en/japan/korean）

基础提取 CLI（run_extraction.py）示例：
```bash
python3 -m cli.run_extraction \
  --retry --attempts 3 --delay 0.5 \
  --prefix chat_dump \
  --scan --batches 5 --direction up \
  --window-title 微信 \
  --formats json,csv
```

高级扫描 CLI（run_advanced_scan.py）示例：
```bash
python3 cli/run_advanced_scan.py \
  --max-scrolls 60 --direction up \
  --scroll-delay 0.8 --scroll-distance-range 150,300 \
  --scroll-interval-range 0.2,0.6 --max-scrolls-per-minute 40 \
  --chat-area 120,90,900,920 \
  --formats json,csv,md \
  --metrics-file ./output/metrics.csv --metrics-format csv
```

预期输出（JSON 示例）：
```json
[
  {
    "id": "",
    "sender": "小王",
    "content": "好的，明天一起开会👍",
    "message_type": "TEXT",
    "timestamp": "2025-11-06T16:02:31",
    "confidence_score": 0.91
  },
  {
    "id": "",
    "sender": "我",
    "content": "收到～📅 会议日程我来拉",
    "message_type": "TEXT",
    "timestamp": "2025-11-06T16:02:45",
    "confidence_score": 0.88
  }
]
```

错误处理与常见排障：
- 未定位到微信窗口：确认微信已打开；尝试 --window-title；或在受限环境中使用 --chat-area 直接覆盖区域。
- 提取到 0 条消息：检查聊天区域坐标是否覆盖到消息区；适当增加滚动次数；合理设置 OCR 语言。
- 权限错误：检查“屏幕录制/辅助功能”权限是否对终端或解释器放行。

子节：扩展脚本与高级扫描

- 全量时间线扫描（自顶向下覆盖）：
  - 脚本：cli/full_timeline_scan.py
  - 作用：先滚动到聊天记录顶部，再向下渐进式扫描，默认按时间顺序导出并去重；支持关闭尾部实时监控。
  - 示例：
    ```bash
    python3 cli/full_timeline_scan.py \
      --output ./output \
      --no-tail \
      --max-scrolls 1200 \
      --delay 0.25 \
      --verbose
    ```
- 高级扫描补充（AdvancedScrollController）：
  - 渐进式滚动与惯性效果：可通过 scroll_distance_range、scroll_interval_range 与 inertial_effect 模拟自然滚动。
  - 资源心跳与指标：循环内输出滚动计数与可用的 CPU/MEM 统计，便于长时运行定位性能瓶颈。
  - 内存管理：历史截图按需裁剪与可选降采样（例如仅保留最近若干次截图、对大图进行比例缩放），适合千级滚动场景。
  - 终止条件：到达边缘、命中关键字、FAILSAFE（鼠标移至角落）等条件均可触发停止。

### 3.3 网页预览

网页预览用于说明/复制命令、保存/加载 UI 配置与查看导出/指标，不执行真实扫描流程。

启动方式：
```bash
python3 web/config_server.py --port 8003
# 打开浏览器访问
open http://localhost:8003/ui_preview.html
```

支持的浏览器：
- Chrome / Edge（建议使用最新版）
- Firefox（最新版）
- Safari（部分功能可能受限）

交互指南：
- 打开 ui_preview.html，填写 OCR 语言、滚动参数、输出目录等配置。
- 点击“保存配置”将 UI 配置写入项目根目录，并同步生成 CLI 可读取的 config.json。
- 点击“刷新最新导出”查看 output/ 与 outputs/ 目录中的最新导出文件；可在 macOS 上通过“在访达中显示”按钮快速定位文件。
- 点击“复制启动命令”获取推荐的 CLI 命令行，用于终端直接执行。
 - Python 解释器路径：在网页预览的“参数设置（交互）”卡片中填写的解释器路径会自动保存到浏览器（localStorage），刷新或重开页面将自动恢复；复制命令与按钮操作会优先使用该值。
 - 隐私说明：页面示例与路径展示默认做脱敏（使用 $HOME 或通用命令）；复制命令与“打开/访达显示”操作均使用真实路径。可在“最新导出”卡片中勾选“显示真实路径”，仅用于列表展示，不影响复制/打开行为。

可用 API（端口默认 8003）：
- POST /api/save-config：保存 UI 配置为 ui_config.json 并生成 CLI 的 config.json
- GET  /api/load-config：加载 ui_config.json 返回到页面
- GET  /api/latest-exports：查询 output/ 与 outputs/ 的最新导出文件（支持 limit 查询参数）
- GET  /api/metrics：返回性能指标快照或生成的零值指标
- POST /api/open-path（仅 macOS）：在 Finder 中显示或打开文件/目录（限 output/ 与 outputs/）
- POST /api/metrics/reset：重置性能指标快照
- POST /api/metrics/snapshot：保存当前指标为快照到 metrics.json

---

## 4. 其他补充说明

常见问题（FAQ）：
- 无法控制微信窗口：尝试以安全模式运行桌面应用；检查屏幕录制与辅助功能权限；在 CLI 提供 --chat-area 覆盖。
- OCR 识别不稳定：调整截图区域或增加预处理（放大/去噪）；切换 OCR 语言；提升截图质量（窗口最大化）。
- 退出码或脚本报错：多与权限/路径/依赖相关；优先确认解释器路径正确且已安装依赖。

去重索引与合并工具：
- 存储层在输出目录维护 .dedup_index.json，避免重复消息重复写入；支持 --clear-dedup-index 清空索引。
- 合并工具（merge 脚本/功能）可汇总多个 JSON 文件并去重、排序后再输出为多种格式，适合批量归档与分析。

附加说明：Desktop 应用退出码 -9 / PaddleX 预加载影响

- 现象：某些桌面环境会在 Python 启动阶段预加载重型库（如 PaddleX/PaddleOCR），导致轻量脚本也被系统以 SIGKILL(-9) 终止。
- 规避建议：
  - 在终端直接运行脚本，并为 Python 启动追加 -S -E（禁用 site 模块加载与环境变量影响）。
  - 使用调试脚本观察启动行为差异（解释器路径、sitecustomize/usercustomize 是否加载、是否触发重型库初始化）。
  - 如无需 PaddleX，可在当前虚拟环境卸载以避免干扰。
  - 如必须在桌面应用中运行，尽量添加 -S -E 或设置 PYTHONNOUSERSITE=1。

时间分隔识别与自定义规则

- 当启用 --exclude-time-only 或在配置中设置 output.exclude_time_only: true 时，存储层会过滤仅用于界面分隔的纯时间/日期消息。
- 内置规则涵盖中文日期/时间、星期、相对日期、AM/PM 等常见形式；允许通过 config.yaml 的 output.time_only_patterns 追加自定义正则：

```yaml
output:
  exclude_time_only: true
  time_only_patterns:
    - "^周[一二三四五六日天]\s*\d{1,2}:\d{2}$"     # 例如：周三 20:15
    - "^昨天\s*\d{1,2}:\d{2}$"                   # 例如：昨天 18:30
    - "^(?:AM|PM)\s*\d{1,2}:\d{2}$"              # AM/PM 无秒
```

离线清洗脚本（sanitize_export.py）

已完成一次导出后，可对 JSON/CSV 进行离线清洗：去重、过滤纯时间、移除字段。例如：

```bash
python3 scripts/sanitize_export.py \
  --input output/extraction_20251106_114448.json \
  --exclude-fields confidence_score,raw_ocr_text \
  --exclude-time-only \
  --aggressive-dedup
```

合并导出（merge_exports.py）

当多次运行生成了多个 JSON 导出文件，可用合并脚本统一合并、去重并导出为 JSON/CSV/Markdown：

```bash
python3 cli/merge_exports.py \
  --inputs ./outputs/full_timeline/initial_full_timeline_20251106_193223.json \
           ./outputs/auto_full/auto_wechat_scan_20251106_193600.json \
  --outdir ./outputs/merged_full \
  --formats json,csv \
  --exclude-fields raw_ocr_text \
  --exclude-time-only
```

说明：默认稳定键去重规则与存储层一致（优先 id，否则 sender|timestamp|content）；合并结果尝试按时间戳排序，无法解析的条目保持相对顺序。

已知限制与最佳实践：
- 贴纸/表情包等图片消息目前不会作为 emoji 文本识别；可能以 IMAGE 类型或被忽略。
- 稳定性依赖于窗口布局与系统权限；在受限环境建议直接使用聊天区域覆盖与较低滚动速度。
- 建议为每条消息提供稳定 id（若可获得），显著提升跨运行的重复识别准确性。
