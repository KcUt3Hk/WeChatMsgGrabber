# CI 优化建议（缓存与工件策略）

本文件补充了在 GitHub Actions 中降低执行时间与带宽占用的实践，配合 `docs/ci.md` 使用。

## Playwright 浏览器缓存（如项目使用 UI 自动化）

使用 actions/cache 缓存 `~/.cache/ms-playwright` 与 `~/.playwright`：

```yaml
- name: Cache Playwright browsers
  uses: actions/cache@v4
  with:
    path: |
      ~/.cache/ms-playwright
      ~/.playwright
    key: ${{ runner.os }}-playwright-${{ hashFiles('**/package-lock.json', '**/requirements*.txt') }}
    restore-keys: |
      ${{ runner.os }}-playwright-
```

如通过 `npx playwright install --with-deps` 或 `pip install playwright && playwright install` 安装，缓存可显著缩短首次下载时间。

## Python 依赖缓存

`actions/setup-python@v5` 支持 pip 缓存：

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: '3.12'
    cache: 'pip'
```

如需额外缓存 PaddleOCR 模型，可缓存 `~/.paddleocr`，并在首次运行前将模型下载/解压至该目录。

## 工件与日志保留策略

将失败日志（如 `pytest-logs`, `screenshots`, `profiling-reports`）打包为工件，并设置合理的保留时间：

```yaml
- name: Upload test logs
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: test-logs
    path: |
      .pytest_cache
      logs/**
      outputs/**
    retention-days: 7
```

建议对连续工作流使用 `concurrency` 取消过时的运行：

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

## 任务矩阵与慢测隔离

使用 `strategy.matrix` 将单元测试、集成测试与慢测试分离到不同作业，便于并行与复用缓存：

```yaml
strategy:
  matrix:
    mode: [unit, integration, slow]

- name: Run tests
  run: |
    python -m pip install -r requirements.txt
    python run_tests.py --mode ${{ matrix.mode }} --mark ${{ matrix.mode == 'unit' && 'unit' || matrix.mode == 'slow' && 'slow' || '' }}
```

## 带宽与时间的进一步优化

- 尽量复用模型与浏览器缓存，避免在每次运行中重复下载大型依赖；
- 对截图与生成数据进行体积压缩（如 PNG 采用 `zlib` 高压缩）；
- 在 `pytest.ini` 中设置合理的标记与跳过策略，避免在无真实窗口的运行器上执行 UI 相关测试。