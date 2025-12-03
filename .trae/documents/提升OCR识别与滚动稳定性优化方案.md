## 目标
- 在不改变整体架构的前提下，提升 OCR 识别准确度与鲁棒性，降低误检/漏检。
- 提高窗口持续滑动的稳定性与边缘判定可靠性，减少误判导致的停止或重复扫描。

## 现状速览
- OCR：已包含预处理、语言回退、引擎多版本兼容、整图/裁剪/区域三级缓存与指标（services/ocr_processor.py:149–307, 814–845, 1348–1561, 1963–2135, 2182–2250）。
- 区域检测：形态学+自适应阈值，过滤面积/比例/长宽（services/image_preprocessor.py:172–289）。
- 媒体气泡：以面积、长宽比、边缘密度等启发式生成占位（services/ocr_processor.py:1840–1946）。
- 滚动：标题定位→枚举→活跃窗口→macOS 回退链；相似度采用均值差，多处 0.95/0.97/0.98 阈值（services/auto_scroll_controller.py:769–889, controllers/main_controller.py:304–319, 365–367）。

## 优化方向
### 1) OCR识别与鲁棒性
- 动态裁剪预处理：按裁剪区域最大边启用轻度去噪与灰度（services/ocr_processor.py:2033–2039）。
- 提高整图分辨率上限：`preprocess_max_side` 1280→1600 以适配高 DPI（models/config.py:31）。
- 归一化输出增强：兼容更多返回键（如 det_polys），避免多版本漏框（services/ocr_processor.py:1376–1383, 1409–1428）。
- 感知哈希缓存：将整图哈希改为 pHash/dHash 提升缓存命中容忍度（services/ocr_processor.py:133–148）。
- 区域检测自适应：形态学核与迭代次数随分辨率调整（services/image_preprocessor.py:236–239）。
- 媒体气泡边缘密度阈值动态化：常数 0.02 → 面积自适应函数（services/ocr_processor.py:1927–1943）。

### 2) 窗口滚动稳定性
- SSIM相似度：用结构相似度替代均值差，阈值 0.92–0.95（services/auto_scroll_controller.py:860–889；controllers/main_controller.py:304–319, 365–367）。
- 最小像素滚动与中心滚动：边缘确认阶段固定像素（如 60px）且强制在聊天区中心滚动，减少误判（services/auto_scroll_controller.py:769–811, 813–858）。
- 看门狗与重试链路：在长时扫描模式开放看门狗线程、心跳缩短，并在连续失败后触发 `ensure_window_ready(retries=3)`（services/auto_scroll_controller.py:1021–1054）。
- 侧边栏匹配增强：下限 0.8→0.85，先做全包含，再模糊匹配；加入中文数字规范化（services/auto_scroll_controller.py:529–568）。

## 分阶段实施
### 阶段A（快速收益，低风险）
1. 引入 SSIM 判定，统一阈值并在控制器同步使用。
2. 提高 `preprocess_max_side` 到 1600；为裁剪区域添加尺寸阈值触发的轻度去噪。
3. 区域检测形态学核自适应（大分辨率下用 5×5）。

### 阶段B（中期增强）
4. 感知哈希替换整图缓存键；补充命中/误命中对比指标。
5. 媒体气泡边缘密度阈值动态化，降低主题差异影响。
6. 归一化输出增强，覆盖多版本字段别名。

### 阶段C（稳定性与韧性）
7. 看门狗与自动重试策略在长时扫描场景开启；心跳采样间隔从 5s→3s（ui/progress.py:76–93）。
8. 侧边栏点击匹配策略优化，减少误点击与找不到会话的情况。

## 验证与指标
- 新增/扩展测试：
  - OCR性能与缓存命中：扩展 `tests/test_ocr_performance_optimization.py`，对 pHash 命中与时长下降做断言。
  - 滚动边缘判定：新增基于 SSIM 的模拟截图相似度测试，覆盖阈值与二次确认逻辑。
  - 媒体气泡：加入面积分层的边缘密度阈值单测，检验误判下降。
- 运行时指标：
  - `services/ocr_processor.py:get_metrics()` 扩展记录 pHash 命中率、SSIM 触发次数与平均值。
  - 进度心跳中打印滚动成功率、边缘确认触发次数。

## 影响与风险控制
- 依赖新增：SSIM 需 `scikit-image` 或自实现；pHash 可纯 NumPy/OpenCV 实现以避免外部依赖。
- 阈值调整需灰度回归：保留开关与配置项以便快速回滚。
- 在 CI/无桌面环境保持默认关闭系统级回退，避免不稳定行为。

## 交付物
- 逐模块差异补丁（按阶段分批提交）。
- 新增/扩展单元测试与指标采集。
- README 增补“优化开关与指标观察”章节。

请确认是否按上述阶段实施，我将按阶段A先行提交最小改动集与测试。