# WeChat 消息提取器（wechatmsgg）

一个自动化从微信窗口截屏、OCR识别并解析为结构化消息的工具集，包含：
- 自动滚动控制（AutoScrollController / AdvancedScrollController）
- OCR识别与区域优化（OCRProcessor）
- 文本区域解析为消息（MessageParser）
- 结果保存到 JSON/CSV/TXT/Markdown（StorageManager）
- 两套 CLI（基础提取与高级扫描）与进度/指标输出（ProgressReporter）

## 快速开始

1) 安装依赖并确保本机能运行 PaddleOCR（可选 GPU）。

2) 运行测试确保环境就绪：

```
pytest -q
```

3) 命令行启动一次提取并保存：

```
python -m cli.run_extraction --retry --attempts 3 --delay 0.5 --prefix chat_dump
```

选项说明（基础提取 CLI：cli/run_extraction.py）：
- `--retry` 是否启用重试机制。
- `--attempts` 最大重试次数（默认 3）。
- `--delay` 尝试间的等待秒数（默认 0.5s）。
- `--prefix` 输出文件名前缀（默认 extraction）。
- `--no-progress` 关闭命令行进度显示。
 - `--scan` 启用自适应多批次扫描（按方向滚动捕获多屏）。
 - `--batches` 扫描的最大批次数（默认 5）。
 - `--direction` 扫描滚动方向（up/down，默认 up）。
- 覆盖项（窗口/区域/OCR）：
  - `--window-title` 自定义窗口标题子串，用于在 macOS 受限环境下辅助定位微信窗口。
  - `--chat-area` 聊天区域覆盖坐标（格式 `x,y,w,h`），受限环境下建议直接提供以跳过窗口定位流程。
  - `--ocr-lang` 覆盖 OCR 语言（如 `ch/en/japan/korean`）。
- `--clear-dedup-index` 在运行前清空持久化去重索引。
 - 过滤选项：
   - `--sender` 按发送者过滤（不区分大小写的子串匹配）。
   - `--start` 起始时间（ISO 格式，例如 `2024-10-01` 或 `2024-10-01T10:00:00`）。
   - `--end` 结束时间（ISO 格式，例如 `2024-10-31` 或 `2024-10-31T18:00:00`）。
   - `--types` 包含的消息类型（逗号分隔，如 `TEXT,IMAGE`）。
   - `--contains` 按消息内容子串过滤（不区分大小写）。
   - `--min-confidence` 最低置信度阈值（0.0-1.0），仅保留分数不低于该值的消息。
 - 输出与存储控制：
   - `--format` 覆盖单一输出格式（`json/csv/txt/md`）。
   - `--formats` 同时导出多种格式（逗号分隔），如 `json,csv,md`。
   - `--outdir` 覆盖输出目录。
   - `--dry-run` 干跑模式，仅显示解析数量，不写入任何文件。
   - `--exclude-fields` 在 JSON/CSV 导出中移除字段（逗号分隔），如 `confidence_score,raw_ocr_text`。
   - `--exclude-time-only` 过滤仅包含日期/时间/星期等的系统分隔消息。
   - `--aggressive-dedup` 启用更激进的内容级去重（基于 `sender+content`，减少同轮重复）。
 - 去重与空结果：
  - `--no-dedup` 本次运行禁用去重（批内与跨批次索引过滤均不执行）。
  - `--skip-empty` 当消息数量为 0 时不写入文件。

输出文件将根据配置写入到 `AppConfig.output.directory` 指定的目录，格式由 `AppConfig.output.format` 或 CLI 的 `--formats` 控制（支持 json/csv/txt/md）。

示例：一次性输出 JSON 与 CSV，并过滤系统时间分隔消息、移除无分析价值字段：

```
python3 cli/run_extraction.py \
  --formats json,csv \
  --exclude-time-only \
  --exclude-fields confidence_score,raw_ocr_text \
  --prefix chat_dump \
  --retry --attempts 2 --delay 0.4
```

## 系统环境要求

- 操作系统：macOS（建议 13+），图形界面可用；
- Python：3.12（请使用本机可用的解释器路径，例如 `python3.12` 或 `python3`）；
- 微信客户端：已安装且可前置显示；
- 权限设置：
  - 系统设置 → 隐私与安全 → 屏幕录制：为终端或 Python 应用授权；
  - 系统设置 → 隐私与安全 → 辅助功能：为终端或 Python 应用授权；
- OCR 模型：首次运行 PaddleOCR 将下载模型，需保证网络可用；可选开启 GPU（取决于本机环境）。

## 依赖库清单及安装方法

项目依赖（摘自 `requirements.txt`）：

- paddlepaddle>=2.4.0
- paddleocr>=2.6.0
- opencv-python>=4.5.0
- Pillow>=8.0.0
- pyautogui>=0.9.53
- pygetwindow>=0.0.9
- pandas>=1.3.0
- PyYAML>=6.0

测试相关：
- pytest>=7.0.0
- pytest-cov>=4.0.0

安装方法：
```
python3 -m pip install -r requirements.txt
```

示例：在 macOS 受限环境下（窗口 API 不可用）使用窗口标题与聊天区域覆盖进行基础提取：

```
python3 cli/run_extraction.py \
  --window-title WeChat \
  --chat-area 10,10,100,100 \
  --ocr-lang ch \
  --format json \
  --prefix chat_dump_basic
```

## 一键自动化脚本：auto_wechat_scan.py（终端直接运行）

该脚本专为“直接在终端运行”的场景设计，提供自动窗口定位、自然滚动、OCR 识别与多格式结构化输出。一条命令完成从采集到导出。

系统环境要求：
- macOS（建议 13+），带可见图形界面；
- 终端或 Python 解释器需授予以下权限：
  - 系统设置 → 隐私与安全 → 屏幕录制（允许终端或 Python 应用录屏）；
  - 系统设置 → 隐私与安全 → 辅助功能（允许终端或 Python 应用控制鼠标/键盘、激活窗口）；
- 微信客户端处于前台或可被激活；
- Python 3.12（请使用本机可用的解释器，例如 `python3` 或 `python3.12`；公开文档不展示个人绝对路径）。

依赖库安装：
- 推荐使用本项目的 `requirements.txt` 安装：
```
python3 -m pip install -r requirements.txt
```
- 首次运行 PaddleOCR 会下载/加载模型，耗时较长属正常现象。

使用说明：
```
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

可选覆盖参数：
- `--window-title` 指定窗口标题子串（例如 `微信` 或 `WeChat`），用于辅助定位窗口；
- `--chat-area` 指定聊天区域坐标（格式：`x,y,width,height`），在窗口定位困难时直接覆盖区域；
- `--ocr-lang` 指定 OCR 语言（默认取配置 `ocr.language`，如 `ch`）；
- `--scroll-delay` 固定滚动停顿时间（若不指定则根据窗口高度自动估算间隔范围）；
- `--dry-run` 仅打印统计与预览，不保存文件；
- `--skip-empty` 当结果为空时不保存文件。
- `--full-fetch` 尝试一次性抓取全部聊天内容（大幅提高滚动上限并在到达边缘时停止，允许一次轻量重试）。
- `--go-top-first` 扫描前先滚动到聊天记录顶部（建议与 `--direction down` 联用，自顶向下一次性覆盖）。

自然滚动与智能停顿：
- 脚本会尝试获取微信窗口高度，并根据高度自动估算“滚动距离范围”和“时间间隔范围”，使滚动更贴近真实用户操作；
- 也可通过 `--scroll-delay` 人为设定固定停顿，间隔范围会以该值为下限进行调整；
- `--max-scrolls-per-minute` 提供速率限制，避免滚动过快被判定为机器行为。

示例（在受限环境中使用覆盖参数）：
```
python3 cli/auto_wechat_scan.py \
  --direction up --max-scrolls 30 \
  --window-title 微信 \
  --chat-area 120,80,920,900 \
  --formats json,csv \
  --output ./output \
  --filename-prefix auto_wechat_scan \
  --verbose
```

示例输出（JSON 部分片段）：
```
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

说明：
- 输出包含时间戳与发送者信息；表情符号（emoji）如 👍📅 将作为文本字符保留；
- 对于贴纸/表情包等图片类消息，当前版本不会将其识别为 emoji 字符，可能以 `IMAGE` 类型或被忽略；
- 多格式导出（JSON/CSV/TXT/Markdown）可通过 `--formats` 指定；CSV/TXT/MD 会按结构化字段生成便于阅读的文本；
- 存储层包含去重索引（`.dedup_index.json`），避免重复消息多次写入，详见下文“去重索引详解”。

常见问题与解决方案：
- 提示“未定位到微信窗口”：
  - 请确认微信已打开且能够被系统识别；
  - 尝试添加 `--window-title 微信` 或 `--window-title WeChat`；
  - 在受限环境中使用 `--chat-area x,y,width,height` 直接覆盖区域。
- 提取到 0 条消息：
  - 检查聊天区域坐标是否覆盖到实际消息区域；
  - 调整滚动次数与方向，或将微信窗口最大化；
  - 提高 OCR 语言准确性（`--ocr-lang ch`）。
- 权限相关报错（屏幕录制/辅助功能）：
  - 在“系统设置 → 隐私与安全”中为终端或 Python 应用授予相应权限，然后重试运行。
- 指标心跳与内存阈值：
  - 为避免误告警，自动化脚本未开启内存阈值检测；如需监控，请改用高级扫描 CLI（`cli/run_advanced_scan.py`）。

### 全量时间线扫描：full_timeline_scan.py（自顶向下，支持尾部实时监控）

如需严格按时间顺序从“最早消息”到“最新消息”一次性抓取，推荐使用 `cli/full_timeline_scan.py`。
该脚本会先自动滚动到顶部，再向下渐进式扫描，默认支持尾部实时监控（可关闭）。

一次性全量抓取（禁用尾部监控）：
```
python3 cli/full_timeline_scan.py \
  --output ./output \
  --no-tail \
  --max-scrolls 1200 \
  --delay 0.25 \
  --verbose
```

说明与建议：
- 若聊天记录极长，可适当增大 `--max-scrolls`（例如 `2000+`）；
- 输出文件默认命名为 `initial_full_timeline_*.json/csv`，并按时间顺序与稳定键去重；
- 运行过程中请确保微信处于前台或可被激活，系统的“屏幕录制/辅助功能”权限已授予终端或 Python。

与 auto_wechat_scan 的搭配建议：
- 若希望使用 `auto_wechat_scan.py` 完成一次性覆盖，可加上 `--go-top-first --direction down --full-fetch`，并根据实际长度增加 `--max-scrolls`；
- 在定位困难时，可以先用 `auto_wechat_scan.py --window-title/--chat-area` 成功识别并保存，再运行 `full_timeline_scan.py` 进行自顶向下的完整覆盖。


### 时间分隔识别与自定义规则

当启用 `--exclude-time-only` 或在配置中设置 `output.exclude_time_only: true` 时，存储过程会过滤掉仅用于界面分隔的“纯时间/日期”消息。内置识别规则包括：

- 日期（可选年份，可选时间）：例如 `2024年10月21日`、`10月21日 23:47`、`2024年10月21日23:47`
- 纯时间（24小时制）：例如 `18:15`、`08:05:12`
- 星期（中文全称）：例如 `星期四`、`星期天`
- 星期（中文简写）：例如 `周一`、`周日`
- 相对日期 + 时间：例如 `昨天 23:47`、`今天 08:30`、`前天 12:00`
- 仅相对日期（部分客户端可能出现）：例如 `昨天`、`今天`、`前天`
- 上下文时间（中文）：例如 `下午 3:05`、`上午9:15`、`中午 12:00`、`凌晨 1:20`、`傍晚 6:45`、`晚间 7:30`
- AM/PM 英文格式：例如 `AM 10:05`、`PM 3:25`

此外，还包含一个宽松的兜底规则：当文本仅由数字、空格、冒号和日期单位（年/月/日/.-）构成，且包含至少一个日期单位或时间冒号时，也会被视为分隔消息。

如需进一步扩展识别范围，可通过 `config.yaml` 的 `output.time_only_patterns` 追加自定义正则（在内置规则之后匹配）：

```yaml
output:
  exclude_time_only: true
  time_only_patterns:
    - "^周[一二三四五六日天]\s*\d{1,2}:\d{2}$"     # 例如：周三 20:15
    - "^昨天\s*\d{1,2}:\d{2}$"                   # 例如：昨天 18:30
    - "^(?:AM|PM)\s*\d{1,2}:\d{2}$"              # AM/PM 无秒
```

提示：自定义正则仅在整段文本完整匹配时生效，避免误过滤包含真实内容的消息。

### 去重索引（.dedup_index.json）详解

为避免重复保存相同消息，存储管理器会在输出目录维护一个持久化索引文件 `.dedup_index.json`：

- 位置：位于输出目录（`AppConfig.output.directory`）根下。
- 内容：一个字符串数组，保存已写入消息的“去重键”。
- 键规则：优先使用 `message.id`；若没有，则使用 `"sender|timestamp|content"` 的组合键（时间为 ISO 字符串）。
  - 实现细节：该逻辑已封装为 `Message.stable_key()` 方法，存储（StorageManager）与扫描（MainController.scan_chat_history）均使用同一策略。
- 工作流程：
  1) 当前批次先进行“批内”去重（同一批只保留唯一消息）。
  2) 再从索引中过滤已保存过的消息，只写入新增消息。
  3) 将新增消息的键追加到索引并持久化回 `.dedup_index.json`。

常用操作：

- 清空索引：在命令行增加 `--clear-dedup-index`，或使用代码 `StorageManager(...).clear_dedup_index()`。
- 禁用去重：将配置 `output.enable_deduplication: false`，则不会进行批内去重和跨批次过滤。
- 最佳实践：
  - 若能为每条消息提供稳定的 `id`，可显著提升跨运行识别重复的准确性。
  - 若使用组合键，消息内容或时间发生微小变化会被视为“新消息”。
  - 当希望“重新保存”历史消息（不被过滤），请先清空索引再执行保存。


## 配置

项目通过 `ConfigManager` 读取应用配置（支持 YAML/JSON）。关键片段（示例）：

配置通过 `ConfigManager` 读取（YAML/JSON）。完整示例：

```yaml
output:
  directory: ./output
  format: json
  enable_deduplication: true
  # 同时导出多种格式（若非空则优先生效）
  formats: ["json", "csv"]
  # 移除字段（仅影响 JSON/CSV）
  exclude_fields: ["confidence_score", "raw_ocr_text"]
  # 过滤纯时间/日期分隔消息
  exclude_time_only: true
  # 激进内容级去重（sender+content）
  aggressive_dedup: false
  # 自定义“纯时间/日期分隔”识别规则（追加到内置规则之后）
  time_only_patterns:
    - "^周[一二三四五六日天]\s*\d{1,2}:\d{2}$"     # 例如：周三 20:15
    - "^昨天\s*\d{1,2}:\d{2}$"                   # 例如：昨天 18:30

ocr:
  language: ch
  use_gpu: false
  confidence_threshold: 0.7

logging:
  level: INFO
  file: ./logs/extractor.log
  max_size: 10MB
```

## 主要特性与优化

- 主控制器重试机制（`MainController.run_with_retry`）：空结果或异常时自动重试。
- OCR 区域 Top-N 优化（`OCRProcessor.detect_and_process_regions(max_regions)`）：按区域面积取前 N，提升性能。
- OCR 裁剪结果缓存（LRU）：避免对相同裁剪图重复识别，显著降低重复开销。
- 进度显示（`MainController.run_with_progress` + `ui/progress.py`）：在 CLI 输出尝试次数、解析条数与异常信息。
- 自动保存（`MainController.run_and_save`）：依据配置输出格式与目录保存结果，并支持基础去重。
 - 自适应滚动扫描（`MainController.scan_chat_history`）：根据 OCR 命中率与截图相似度动态调整滚动速度与等待时间。
 - 持久化跨批次去重（`StorageManager`）：在输出目录维护 `.dedup_index.json` 索引，避免不同运行间重复消息保存；可通过 `--clear-dedup-index` 清空索引。
 - CLI 输出覆盖与干跑：命令行支持 `--format`/`--outdir` 覆盖输出设置，以及 `--dry-run` 干跑以便快速核对提取效果。

### 高级扫描（渐进式滚动 + 速率控制 + 指标心跳 + 多格式导出）

在 `cli/run_advanced_scan.py` 中提供了针对微信聊天界面的高级扫描 CLI，支持：

- 渐进式滚动与惯性效果（AdvancedScrollController）
- 智能终止条件（到达边缘、命中目标内容）
- 速率控制与滚动参数覆盖
- 资源心跳与指标写入（CSV/JSON），支持 CPU/内存阈值告警

常用参数（cli/run_advanced_scan.py）：

- 基本控制：
  - `--max-scrolls` 最大滚动次数（默认 50）
  - `--direction` 滚动方向（`up`/`down`，默认 `up`）
  - `--target-content` 命中该内容时提前停止
  - `--no-stop-at-edges` 不在聊天记录边缘处停止
- 覆盖项（窗口/区域/OCR）：
  - `--window-title` 自定义窗口标题子串（非受限环境定位窗口）
  - `--chat-area` 聊天区域覆盖坐标（格式：`x,y,w,h`；受限环境建议必传）
  - `--ocr-lang` OCR 语言覆盖（如 `ch/en/japan/korean`）
- 滚动与速率参数：
  - `--scroll-speed` 滚动速度（平台相关，默认内部值）
  - `--scroll-delay` 每次滚动后的延迟秒数（建议 `0.3-1.0`）
  - `--scroll-distance-range` 每次滚动距离范围（像素，格式 `min,max`，建议 `150,300`）
  - `--scroll-interval-range` 渐进式滚动的时间间隔范围（秒，格式 `min,max`，建议 `0.2,0.6`）
  - `--max-scrolls-per-minute` 每分钟滚动上限（建议 `30-60`）
- 指标采集输出：
  - `--metrics-file` 指标写入文件路径（CSV/JSON）
  - `--metrics-format` 指标写入格式（`csv`/`json`，默认 `csv`）
  - `--cpu-threshold` CPU 使用率阈值（超过则告警，单位：%）
  - `--mem-threshold` 内存占用阈值（超过则告警，单位：MB）
  - `--metrics-max-size-mb` 指标文件最大大小（MB），需与 `--metrics-rotate-count` 配合使用；当 `>0` 时达到后进行简单轮转（`file`→`file.1`→`file.2`...），当 `<=0` 时禁用轮转
  - `--metrics-rotate-count` 轮转保留的文件个数（例如 3 则保留 `.1/.2/.3`）；当 `<=0` 时不保留历史且禁用轮转，仅当 `--metrics-max-size-mb>0` 时轮转才会生效

- 输出与去重控制（与基础 CLI 对齐）：
  - `--format` 单一输出格式覆盖
  - `--formats` 多格式导出，逗号分隔
  - `--outdir` 输出目录覆盖
  - `--dry-run` 干跑模式
  - `--no-dedup` 禁用去重
  - `--skip-empty` 空结果不保存
  - `--exclude-time-only` 过滤系统分隔消息
  - `--exclude-fields` JSON/CSV 移除字段
  - `--aggressive-dedup` 激进内容级去重

示例命令（macOS 受限环境推荐）：

```
python3 cli/run_advanced_scan.py \
  --dry-run --skip-empty \
  --direction up --max-scrolls 20 \
  --chat-area 10,10,100,100 \
  --scroll-delay 0.5 \
  --scroll-distance-range 180,260 \
  --scroll-interval-range 0.25,0.45 \
  --max-scrolls-per-minute 40 \
  --metrics-file ./reports/cli_metrics.csv \
  --metrics-format csv \
  --cpu-threshold 80 --mem-threshold 1024 \
  --metrics-max-size-mb 0.5 --metrics-rotate-count 3
```

若希望观察指标写入（JSON）与阈值告警：

```
python3 cli/run_advanced_scan.py \
  --dry-run --skip-empty \
  --direction up --max-scrolls 10 \
  --chat-area 10,10,100,100 \
  --metrics-file ./reports/cli_metrics.json \
  --metrics-format json \
  --cpu-threshold 50 --mem-threshold 800
```

说明：

- 受限环境下（无法定位/激活窗口）建议始终使用 `--chat-area`，流程将跳过窗口定位并直接截屏。
- 指标写入采用“追加”模式，CSV 首次写入会生成表头；JSON 每行一个记录。
- 阈值告警不会中断流程，仅输出告警日志；请结合 `reports/cli_metrics.*` 分析长期运行状态。
 - 注：从 2025-11-06 起，项目默认在 `cli/run_advanced_scan.py` 中禁用了内存阈值的实际生效（即使传入 `--mem-threshold` 也不会触发告警），以提升使用体验；如需恢复，请在代码中将 `mem_threshold_mb=None` 改回传递 CLI 值。
 - 当配置了文件轮转（`--metrics-max-size-mb` 与 `--metrics-rotate-count`）后，达到大小阈值会将当前文件重命名为 `.1`，已有的历史文件序号整体后移，新的文件会重新写入表头（CSV）。

示例：高级扫描并一次性输出 JSON/Markdown 两种格式，过滤系统分隔消息：
 
```
python3 cli/run_advanced_scan.py \
  --direction up --max-scrolls 15 \
  --chat-area 10,10,100,100 \
  --formats json,md \
  --exclude-time-only \
  --prefix chat_scan
```

## 离线清洗脚本（sanitize_export.py）

当已完成一次导出后，可使用脚本对 JSON/CSV 文件进行“离线清洗”：去重、过滤纯时间、移除字段。

示例：

```
python3 scripts/sanitize_export.py \
  --input output/extraction_20251106_114448.json \
  --exclude-fields confidence_score,raw_ocr_text \
  --exclude-time-only \
  --aggressive-dedup
```

注意：该脚本不依赖再次截图/OCR，直接处理已有导出文件；其规则与存储层保持一致。

## 运行要求与注意事项

- 需要操作系统层面的窗口管理与鼠标键盘模拟（pygetwindow / pyautogui）。
- 需要可见的微信窗口，且聊天区域能够被截屏。
- PaddleOCR 需要相应的模型与依赖，初次运行可能较慢。
- 如在无 GUI 环境（CI）运行，请针对相关模块进行模拟与跳过。

测试注意事项：
- 在本地机器实际运行微信时，某些窗口相关的测试（例如 `tests/test_auto_scroll_controller.py::test_locate_wechat_window_not_found`）可能受真实窗口影响而失败；这类测试在 CI/无窗口环境或禁用目标窗口时更为稳定。

## 测试

运行全部测试：

```
pytest -q
```

当前测试覆盖：
- 自动滚动控制器核心功能（窗口定位、截屏、质量优化、比较与缓存）
- OCR 基础识别与图像质量评分
- OCR 区域 Top-N 限制与缓存（新增）
- 主控制器重试与保存（`run_and_save`）
- 存储格式（JSON/CSV/TXT/Markdown）、多格式导出与去重索引

## 合并导出（merge_exports.py）

当你已通过多次运行 `auto_wechat_scan.py`、`full_timeline_scan.py` 或基础提取 CLI 生成了多个 JSON 导出文件，可使用合并脚本将它们统一合并、去重并导出为 JSON/CSV（可选 Markdown）。

使用示例：
```
python3 cli/merge_exports.py \
  --inputs ./outputs/full_timeline/initial_full_timeline_20251106_193223.json \
           ./outputs/auto_full/auto_wechat_scan_20251106_193600.json \
  --outdir ./outputs/merged_full \
  --formats json,csv \
  --exclude-fields raw_ocr_text \
  --exclude-time-only
```

主要选项：
- `--inputs` 指定多个输入路径（文件或目录）。为目录时将扫描其中的 `.json`（忽略 `.dedup_index.json`）。
- `--outdir` 输出目录（默认 `./outputs/merged_full`）。
- `--formats` 导出格式（逗号分隔）：`json,csv,md`。
- `--filename-prefix` 输出文件名前缀（默认带时间戳）。
- `--exclude-fields` 在导出中移除指定字段（如 `raw_ocr_text`）。
- `--exclude-time-only` 过滤纯时间/日期分隔消息。
- `--aggressive-dedup` 激进内容级去重（基于 `sender+content`），可减少同轮重复。

说明与建议：
- 默认稳定键去重规则与存储层一致：优先 `id`，否则 `sender|timestamp|content`（时间戳规范化到秒级）。
- 合并结果尝试按时间戳排序，无法解析的条目将保持相对顺序。
- 若需要更丰富的 Markdown 格式，可考虑通过 `StorageManager` 扩展或将输出导入分析工具处理。

## 版本控制与里程碑

本项目采用语义化版本（Semantic Versioning），推荐的版本管理流程如下：

里程碑定义建议：
- v1.0.0：完成基础提取与自动滚动扫描两条端到端流程，支持多格式导出与去重索引；新增合并导出脚本（merge_exports.py）。
- v1.1.0：扩展滚动策略与参数自适应；完善 Markdown 输出与示例。
- v1.2.0：加入更完善的窗口定位与受限环境适配；提供持续监控与增量导出。

版本管理与发布（示例命令）：
```
# 提交变更
git add .
git commit -m "feat: add merge_exports CLI; docs: sanitize README and add versioning guidance"

# 打标签（按里程碑版本）
git tag -a v1.0.0 -m "Milestone: E2E extraction + auto scan + merge exports"

# 推送到远程
git push origin main --tags

# 在 GitHub Releases 页面创建发行版，附上 CHANGELOG 说明
```

CHANGELOG 维护建议：
- 在仓库根目录维护 `CHANGELOG.md`，记录每个版本的新增、修复与优化条目。
- 与标签对应；发布时将 CHANGELOG 摘要附到 GitHub Release。

隐私与脱敏：
- 本 README 已去除任何本地用户名、路径等个人信息，请在公共仓库中保持该风格。
- 示例命令统一使用 `python3` 与相对路径，如需自定义解释器路径请在本地运行时自行替换。

## 路线图（下一步计划）

- 去重索引管理：提供更细粒度的索引导入/导出与统计。
- CLI 增强：更多自定义格式模板、并发批次控制、Web UI。
- UI 拓展：在 CLI 基础上进阶到 TUI 或轻量 Web UI。

欢迎反馈与贡献！