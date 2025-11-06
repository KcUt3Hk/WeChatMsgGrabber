# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2025-11-06
Milestone: E2E extraction + auto scan + merge exports

- feat: 新增 CLI `merge_exports.py`，支持合并多个导出（JSON）、跨文件去重、字段排除、过滤纯时间/日期分隔消息、可选 Markdown/CSV 输出。
- fix: 改进分隔消息过滤规则，支持“星期X HH:MM”等常见格式；增强文本规范化以移除零宽字符、统一冒号。
- docs: README 完成隐私脱敏，统一示例命令为通用 `python3` 与相对路径；新增“合并导出”和“版本控制与里程碑”章节。
- chore: 明确版本管理流程与发布建议（标签、GitHub Releases）。

---

遵循语义化版本（Semantic Versioning）。后续版本将继续扩展滚动策略、窗口定位与 OCR 参数优化，并提供持续监控与增量导出能力。