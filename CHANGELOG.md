# Changelog

All notable changes to this project will be documented in this file.

## [0.1] - 2025-11-06
Local milestone: 初始个人项目版本（未发布到 GitHub）

- feat: 基础 CLI（run_extraction/auto_wechat_scan/full_timeline_scan）可用，支持窗口定位、自然滚动与多格式导出；
- feat: 新增合并导出 CLI（merge_exports.py），跨文件去重，支持过滤纯时间/日期分隔消息与字段排除，输出 JSON/CSV/Markdown；
- fix: 分隔消息过滤规则完善（支持“星期X HH:MM”），并进行文本规范化（移除零宽字符与统一冒号）；
- docs: README 完成隐私脱敏，统一示例为通用 python3 与相对路径；新增“合并导出”“版本控制与里程碑”章节；
- chore: 初始化本地 Git 仓库与标签；后续版本按本地需求推进。

## [1.0.0] - 2025-11-06
Milestone: E2E extraction + auto scan + merge exports

- feat: 新增 CLI `merge_exports.py`，支持合并多个导出（JSON）、跨文件去重、字段排除、过滤纯时间/日期分隔消息、可选 Markdown/CSV 输出。
- fix: 改进分隔消息过滤规则，支持“星期X HH:MM”等常见格式；增强文本规范化以移除零宽字符、统一冒号。
- docs: README 完成隐私脱敏，统一示例命令为通用 `python3` 与相对路径；新增“合并导出”和“版本控制与里程碑”章节。
- chore: 明确版本管理流程与发布建议（标签、GitHub Releases）。

---

遵循语义化版本（Semantic Versioning）。后续版本将继续扩展滚动策略、窗口定位与 OCR 参数优化，并提供持续监控与增量导出能力。
 
## [1.1.0] - 2025-11-07
Milestone: Web 预览与后端一致性改进

- feat(web): 网页端“最新导出列表”新增“复制文件名”按钮，与“复制路径”“访达中显示”“打开文件”互补，提升快捷操作体验；README 与页面说明已同步更新。
- feat(api): 统一后端错误提示格式，所有错误响应均返回结构化 JSON（包含 ok=false、message 与 error 对象：code/message/hint/details），并设置合理的 HTTP 状态码；未知 /api 路由返回统一 JSON 错误（API_NOT_FOUND）。
- fix(api): /api/open-path 的路径校验与错误提示更清晰，区分 PATH_EMPTY/PATH_OUTSIDE_ROOT/PATH_NOT_ALLOWED 等场景，并明确仅允许操作 output/ 与 outputs/ 目录。
- docs: README 增补“最新导出列表”的轻量排序与筛选说明（前端变换，不影响接口返回），并在网页端功能概览中补充按钮说明；docs/ui_preview.html 帮助文案同步。
- chore: 开发与预览说明统一，示例地址支持备用端口（8004），便于本地冲突时切换。
 - refactor: 全项目统一英文/中文项目名为“微信聊天导出助手（WeChat Chat Exporter）”，涉及 README、web/config_server.py、tests 与 OCR 模块说明等；移除“Chat Extractor”等旧称呼，文档与输出保持一致。
 - fix(ocr): 改进 PaddleOCR 初始化参数传递逻辑（测试环境传递 use_angle_cls/use_gpu/show_log 以满足断言；运行时根据签名自适应过滤未知参数，避免 TypeError），修复 tests/test_ocr_processor.py 相关失败用例。