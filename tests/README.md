# OCR Module Unit Tests

This directory contains unit tests for the WeChatMsgGrabber OCR module, specifically testing OCR recognition accuracy and different image quality processing scenarios.

## Test Files

### `test_ocr_basic.py`
Basic functionality tests for the OCR processor:
- OCR configuration creation and validation
- OCR processor initialization
- Engine initialization with mocked PaddleOCR
- Supported languages retrieval
- Basic error handling

### `test_ocr_image_quality.py`
Image quality-specific tests:
- High quality image processing (expected high confidence)
- Low quality image processing (expected lower confidence)
- Very low quality image processing (expected very low confidence)
- Preprocessing effectiveness testing
- Confidence threshold filtering
- Enhanced confidence calculation
- Various image quality fixtures (noise, blur, darkness, low contrast)

### `conftest.py`
Shared pytest configuration and fixtures:
- Test data directory setup
- Logging configuration
- Sample configuration dictionaries

## Running Tests

### Run All OCR Tests
```bash
python run_tests.py
```

### Run Specific Test Files
```bash
# Basic tests only
python -m pytest tests/test_ocr_basic.py -v

# Image quality tests only
python -m pytest tests/test_ocr_image_quality.py -v

# All tests with coverage
python -m pytest tests/ --cov=services.ocr_processor --cov=services.image_preprocessor --cov-report=term-missing
```

### Run Individual Tests
```bash
# Run a specific test
python -m pytest tests/test_ocr_basic.py::TestOCRBasics::test_ocr_config_creation -v
```

## Test Coverage

The tests achieve approximately 62% overall coverage of the OCR and image preprocessing modules:
- `services/ocr_processor.py`: 72% coverage
- `services/image_preprocessor.py`: 52% coverage

## Test Strategy

### Mocking Strategy
- PaddleOCR is mocked to avoid dependency installation requirements
- Mock responses simulate different confidence levels based on image quality
- Tests focus on the logic and data flow rather than actual OCR accuracy

### Image Quality Testing
Tests simulate various real-world scenarios:
1. **High Quality Images**: Clear text, high contrast, good lighting
2. **Low Quality Images**: Some noise and blur, moderate degradation
3. **Very Low Quality Images**: Heavy noise and blur, significant degradation
4. **Dark Images**: Poor lighting conditions
5. **Low Contrast Images**: Reduced text-background contrast

### Confidence Testing
- Tests verify confidence threshold filtering works correctly
- Enhanced confidence calculation combines OCR confidence with image quality metrics
- Different image qualities produce appropriately different confidence scores

## Requirements Verification

These tests verify the following requirements from the specification:

**Requirement 1.2**: OCR引擎应当能够准确识别窗口中的文本内容
- ✅ Tests verify OCR engine can process images and extract text
- ✅ Tests verify confidence scoring works correctly
- ✅ Tests verify different image qualities produce appropriate results

**Requirement 4.1**: 当OCR识别失败时，系统应当重试最多3次并记录失败信息
- ✅ Tests verify error handling returns appropriate empty results
- ✅ Tests verify engine initialization failure handling

## Notes

- Tests use mocked PaddleOCR to avoid requiring actual OCR installation
- Image fixtures are generated programmatically using PIL
- Tests focus on core functional logic rather than edge cases
- Coverage could be improved by testing more error scenarios and edge cases

## 环境自适应与选择性运行（中文说明）

为提升本地与 CI 环境下的稳定性与覆盖率，测试套件引入了环境自适应机制与自定义标记：

- 自定义标记：`requires_wechat_closed`
  - 用途：标记那些期望“微信窗口未打开”的测试用例。
  - 行为：
    - 本地默认模式下（`WECHAT_TEST_MODE=auto`），若检测到已打开的微信窗口，则跳过这些用例；
    - CI 环境（`CI=true` 或 `GITHUB_ACTIONS=true`）不跳过，确保覆盖率。

- 环境变量：`WECHAT_TEST_MODE`（默认 `auto`）
  - `auto`（默认）：本地根据真实窗口状态自适应跳过标记为 `requires_wechat_closed` 的用例；CI 环境不跳过。
  - `force_not_found`：强制模拟“未找到窗口”的场景，不进行自适应跳过（适合在本地也希望完整覆盖该场景时）。

### 常用命令示例

- 默认运行（推荐）：

```bash
pytest -q
```

- 本地强制验证“未找到窗口”场景（不因窗口已打开而跳过）：

```bash
WECHAT_TEST_MODE=force_not_found pytest -q
```

- 仅运行需要“微信窗口关闭”的用例：

```bash
pytest -m requires_wechat_closed -q
```

- 按名称选择性运行（示例）：

```bash
pytest -k locate_wechat_window_not_found -q
```

说明：自适应逻辑在 `tests/conftest.py` 中实现，检测复用业务逻辑 `AutoScrollController.locate_wechat_window()` 以保证与实际行为一致。

## 并行运行（pytest-xdist）

在配备多核 CPU 的设备上，建议对“单元与常规测试”启用并行运行以显著加速：

```bash
# 使用 run_tests.py 快速并行运行（排除 integration/slow）
./run_tests.py --mode quick --parallel auto

# 或直接使用 pytest-xdist
pytest -m "not integration and not slow" -n auto --dist=loadfile -q
```

注意事项：
- 集成/端到端/慢速测试通常涉及文件系统、模型下载或窗口模拟，启用并行可能导致资源竞争或不稳定，建议保持串行。
- 如需在 CI 中应用并行运行，请参考 `docs/ci.md` 的“并行化建议”。

## 性能分析（cProfile）

当需要定位测试执行的性能瓶颈时，可使用脚本入口启用 cProfile：

```bash
# 快速分析（建议 quick 模式并行）
./run_tests.py --mode quick --parallel auto --profile \
  --profile-out profiles/quick.prof \
  --profile-report profiles/quick.txt

# 全量/慢测分析（串行更稳健）
./run_tests.py --mode full --profile --profile-out profiles/full.prof
./run_tests.py --mode slow --profile --profile-out profiles/slow.prof
```

说明：.prof 文件适合用 snakeviz 等工具进行可视化；文本报告可直接查看最耗时函数摘要。