解决本地破解微信消息导致的合规问题，采用更笨的方法：模拟滑动聊天窗口查看消息，进行OCR识别，解析为结构化的消息。 

v2.02版本更新
- 日志中，增加任务总结（开始和结束时间/耗时；累计滚动次数/每分钟滚动次数；消息时长/最长连续/最长间隔；累计消息/我的消息/对方消息）
- 其他细节优化
注：AI建议每分钟40-60次，实际可以调得更高（个人测试120）；滑动次数上限，也可以调得更高（个人测试6万次），数字太小会限制识别的内容
其他已知问题：图片识别暂无更好方案，可能会采用识别并截图保存的方案（未尝试）

v2.0版本主要优化
- 提高稳定性，经测试，连续10小时滑动和识别，稳定无异常；
- 优化对分享内容的识别，如：消息卡片、小程序等；
- 优化了消息去重逻辑，避免重复导出相同的消息；
- 优化桌面应用UI和交互，增加暂停/继续扫描功能；
- 等。
其他已知问题：仍有部分消息无法识别，如：图片中的文字等。  

结构化的消息生成后，请自行借助第三方AI（如 ChatGPT、Claude 等）进行分析。
（原本计划发布的消息分析工具，开发出了demo，但觉得满足不了需求，又因为要开发其他项目，遂弃）

说明：
- 该程序完全借助AI开发，没有一行代码是我写的
- 本人代码水平仅限于 print hello world
- 等有时间再继续更新
- 在此及之前描述由我本人所写

# 微信聊天记录获取助手（WeChatMsgGrabber）
文档结构概览：
1. 最近更新（重点）
2. 项目介绍
3. 使用指南（桌面应用为主）

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
- 接入大语言模型，通过文字分析情绪变化趋势、情感分析、性格分析、人格类型，等；
- 智能生成回复提示词（分析女友当前情绪，提供回复建议，等）；
- 等。

工具解决不了全部问题，真诚有效沟通还有可能。

另外，**该程序完全由AI生成**（耗时5天，其中有1天半花费在如何使用GitHub，以及处理报错），没有一行代码是我写的（仍处于 print hello world 的水平），只有前面这部分描述是我本人写的。

# 微信聊天记录获取助手（WeChatMsgGrabber）
文档结构概览：
1. 项目介绍
2. 系统要求与依赖
3. 使用指南
   3.1 桌面应用
4. 其他补充说明

下文命令以 python3 为示例；请根据本地环境（如 Windows 使用 py 或 python）适当调整。

---

## 1. 项目介绍

核心功能：
- 从微信聊天窗口自动截屏，进行 OCR 识别并解析为结构化消息对象（Message）
- 支持自动滚动、渐进式滑动与智能终止检测，覆盖基础与高级两类扫描方式
- 提供简易桌面 UI（Tkinter），满足直观操作需求
- 多格式导出（JSON/CSV/TXT/Markdown）与持久化去重索引，便于批量处理与复用

主要技术栈与架构概述：
- 语言与运行时：Python 3.12
- 核心库：PaddleOCR、OpenCV、Pillow、pyautogui、pygetwindow、pandas、PyYAML
- 前端/界面：Tkinter 简易桌面 UI

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

依赖安装：
```bash
# 安装核心依赖（建议）
python3 -m pip install -r requirements.txt
```

---

## 3. 使用指南

### 3.1 桌面应用（推荐）

- 安装依赖：`python3 -m pip install -r requirements.txt`；如缺 Pillow：`python3 -m pip install Pillow`
- 启动：`python3 ui/simple_gui.py`
- **界面特性**：
  - **响应式布局**：窗口默认采用 500x1000 的手机端比例，适合单列阅读。
  - **自由调整**：支持拖拽边缘自由调整窗口大小，且自动记忆上次关闭时的尺寸与位置。
  - **交互优化**：按钮间距适中，操作更误触。
- 核心流程：设置 `窗口标题` 或 `聊天区域 x,y,w,h` → 选择 `OCR 语言` 与 `输出目录` → 点击 `开始扫描`
- 日志管理：每次开始自动生成 `scan_YYYYMMDD_HHMMSS.log`，顶部显示当前日志路径
- 暂停/继续：扫描中可随时暂停（终止子进程但保留日志）；继续后在原日志追加；暂停超过 30 分钟自动停止
- 速率控制：填写 `每分钟滚动 (spm)`；可选 `spm范围(min,max)`（如 `30,60`）以动态化速率；默认滚动间隔随机化并偶发微暂停
- 预览：填写 `x,y,w,h` 后，开始前自动截取一次聊天区域预览图用于校准；也可点击“预览聊天区域”；框选操作后会自动刷新预览图。
- 权限：确保“屏幕录制/辅助功能”已授权当前终端或 Python 解释器

发布到 GitHub 的隐私提示：
- 本地 `config.json` 与 `ui_config.json` 含个人路径，已通过 `.gitignore` 排除；如需示例，请参考 `config.example.json` 与 `ui_config.example.json`
- 发布前可运行 `python3 scripts/privacy_scan.py --fail-on-warning` 或使用自动准备脚本 `python3 scripts/prepare_release.py`，在 `dist/github-release` 生成已脱敏的副本供提交

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
 - 引擎初始化优化：默认采用识别分支（rec=True, det=False）以降低模型加载与内存占用；默认关闭 PaddleX 离线/缓存猴子补丁以减少额外预加载。

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
