#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
隐私扫描脚本
---------------------------------
用途：在提交到 GitHub 之前对仓库进行快速隐私审计，阻断可能包含的个人信息或敏感数据。

功能要点：
- 扫描指定目录（默认：项目根目录）中的文本文件；
- 检测个人路径、个人 ID、手机号、邮箱、以及其它可配置的敏感模式；
- 输出详细报告，并在发现高危项时以非零退出码结束进程；

使用方法：
    python scripts/privacy_scan.py --base-dir .
    python scripts/privacy_scan.py --fail-on-warning

参数说明：
- --base-dir：扫描的根目录，默认当前目录；
- --fail-on-warning：开启后，警告级别也将作为错误处理（默认只在 error 级别退出）。

注意：本脚本只扫描文本文件，二进制文件将被跳过。可根据项目需要调整扫描的文件扩展名和敏感模式。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Iterable, List, Tuple


@dataclass
class MatchItem:
    """匹配结果的数据结构。

    字段：
    - file_path：命中的文件路径；
    - line_no：命中的行号；
    - level：级别（"error" 或 "warning"）；
    - pattern：触发的敏感模式（字符串或正则表达式描述）。
    - line：命中的原始内容片段。
    """
    file_path: str
    line_no: int
    level: str
    pattern: str
    line: str


def should_skip_dir(dir_name: str) -> bool:
    """判断目录是否需要在扫描时跳过。

    设计原则：跳过常见的构建缓存、虚拟环境与版本控制目录，避免噪声与性能问题。
    """
    skip_dirs = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".venv",
        "venv",
        "node_modules",
        # 以下目录为运行产物或性能分析输出，可能包含本工具生成的报告或本机路径，不参与扫描
        "reports",   # 隐私扫描报告输出目录，避免自扫误报
        "profiles",  # 本地性能分析报告目录，已在 .gitignore 中忽略
    }
    return dir_name in skip_dirs


def text_file_extensions() -> Tuple[str, ...]:
    """返回需要扫描的文本文件扩展名集合。

    可根据项目需求进行扩展或收缩（例如加入 .rst/.ipynb 的纯文本单元等）。
    """
    return (
        ".py",
        ".md",
        ".txt",
        ".yml",
        ".yaml",
        ".ini",
        ".cfg",
        ".toml",
        ".json",
        ".html",
        ".css",
        ".js",
        ".sh",
    )


def list_files_to_scan(base_dir: str) -> List[str]:
    """枚举需要扫描的文本文件。

    实现细节：
    - 使用 os.walk 遍历；
    - 跳过 should_skip_dir 返回 True 的目录；
    - 只收集后缀在 text_file_extensions() 集合中的文件。
    """
    files: List[str] = []
    exclude_files = {os.path.normpath(os.path.join(base_dir, "scripts", "privacy_scan.py"))}
    for root, dirs, filenames in os.walk(base_dir):
        # 过滤目录
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]

        for name in filenames:
            if os.path.splitext(name)[1] in text_file_extensions():
                fp = os.path.join(root, name)
                if os.path.normpath(fp) in exclude_files:
                    # 跳过本工具脚本自身，避免因内置敏感模式字符串而误报
                    continue
                files.append(fp)
    return files


def build_sensitive_patterns() -> Tuple[List[str], List[Tuple[str, re.Pattern]], List[Tuple[str, re.Pattern]]]:
    """构建敏感模式集合。

    返回三类模式：
    - exact_errors：错误级别的精确字符串匹配（如个人路径、个人ID等）；
    - regex_errors：错误级别的正则匹配（如手机号、邮箱）；
    - regex_warnings：警告级别的正则匹配（较为宽松的可能项，如通用 /Users 路径）。
    """
    # 错误级别：精确字符串
    exact_errors: List[str] = [
        # 在此处添加特定的高危字符串（如硬编码的 API Key、特定路径等）
    ]

    # 错误级别：正则表达式
    regex_errors: List[Tuple[str, re.Pattern]] = [
        ("CN_mobile", re.compile(r"\b1[3-9]\d{9}\b")),  # 中国大陆手机号（11位）
        ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
        # 证件号：限定包含“号/号码/No/Number”等关键词与 5 位以上数字，避免普通说明文字误报
        ("id_number_like", re.compile(r"(身份证号|身份证号码|银行卡号|护照号|社保号|ID\s*(No|Number)?)\s*[:：]?\s*\d{5,}")),
    ]

    # 警告级别：正则表达式（宽松匹配）
    regex_warnings: List[Tuple[str, re.Pattern]] = [
        ("mac_users_path", re.compile(r"/Users/[^/]+/")),  # 通用 macOS 用户目录
    ]

    return exact_errors, regex_errors, regex_warnings


def scan_file(file_path: str, exact_errors: Iterable[str], regex_errors: Iterable[Tuple[str, re.Pattern]], regex_warnings: Iterable[Tuple[str, re.Pattern]]) -> List[MatchItem]:
    """扫描单个文件并返回命中结果列表。

    实现说明：
    - 逐行读取文件内容；
    - 先进行精确字符串匹配，再进行正则匹配；
    - 分类记录命中项为 error 或 warning。
    """
    matches: List[MatchItem] = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, start=1):
                text = line.strip()
                if not text:
                    continue

                # 精确匹配（错误级别）
                for pat in exact_errors:
                    if pat in text:
                        matches.append(MatchItem(file_path=file_path, line_no=i, level="error", pattern=pat, line=text))

                # 正则匹配（错误级别）
                for name, rx in regex_errors:
                    if rx.search(text):
                        matches.append(MatchItem(file_path=file_path, line_no=i, level="error", pattern=name, line=text))

                # 正则匹配（警告级别）
                for name, rx in regex_warnings:
                    if rx.search(text):
                        matches.append(MatchItem(file_path=file_path, line_no=i, level="warning", pattern=name, line=text))
    except Exception as exc:
        # 读取失败不作为错误，但打印提示以便人工检查。
        sys.stderr.write(f"[privacy-scan] 跳过无法读取文件：{file_path}（{exc}）\n")
    return matches


def scan_repository(base_dir: str, fail_on_warning: bool = False) -> Tuple[List[MatchItem], List[MatchItem]]:
    """扫描仓库并返回 (errors, warnings)。

    参数：
    - base_dir：扫描起始目录；
    - fail_on_warning：为 True 时，警告也将计入错误退出条件。

    返回值：
    - errors：错误级别命中项列表；
    - warnings：警告级别命中项列表。
    """
    exact_errors, regex_errors, regex_warnings = build_sensitive_patterns()
    files = list_files_to_scan(base_dir)

    all_errors: List[MatchItem] = []
    all_warnings: List[MatchItem] = []

    for fp in files:
        hits = scan_file(fp, exact_errors, regex_errors, regex_warnings)
        for h in hits:
            if h.level == "error":
                all_errors.append(h)
            else:
                all_warnings.append(h)

    # 输出报告（终端 + 文件）
    if all_errors or all_warnings:
        report_lines: List[str] = []
        report_lines.append("=== 隐私扫描报告 ===")
        if all_errors:
            report_lines.append("\n[ERROR] 发现高危敏感信息：")
            for m in all_errors:
                report_lines.append(f" - {m.file_path}:{m.line_no} | pattern={m.pattern} | {m.line[:200]}")
        if all_warnings:
            report_lines.append("\n[WARNING] 发现可能的敏感信息：")
            for m in all_warnings:
                report_lines.append(f" - {m.file_path}:{m.line_no} | pattern={m.pattern} | {m.line[:200]}")
        report_lines.append("====================")

        # 控制台输出
        print("\n" + "\n".join(report_lines) + "\n")

        # 写入到 reports/privacy-scan.txt
        try:
            os.makedirs(os.path.join(base_dir, "reports"), exist_ok=True)
            out_path = os.path.join(base_dir, "reports", "privacy-scan.txt")
            with open(out_path, "w", encoding="utf-8") as wf:
                wf.write("\n".join(report_lines))
        except Exception as exc:
            sys.stderr.write(f"[privacy-scan] 写入报告文件失败：{exc}\n")

    # 退出码策略
    if all_errors:
        return all_errors, all_warnings
    if fail_on_warning and all_warnings:
        return all_warnings, []  # 语义上视作错误
    return [], all_warnings


def parse_args(argv: List[str]) -> argparse.Namespace:
    """解析命令行参数。

    说明：保持接口简洁，便于在 CI 中直接调用。
    """
    parser = argparse.ArgumentParser(description="仓库隐私扫描工具")
    parser.add_argument("--base-dir", default=".", help="扫描起始目录，默认当前目录")
    parser.add_argument("--fail-on-warning", action="store_true", help="将警告也视作错误")
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    """程序入口函数。

    执行流程：
    1. 解析参数；
    2. 扫描仓库；
    3. 打印报告并设置退出码（0=通过，1=含错误）。
    """
    args = parse_args(argv)
    errors, warnings = scan_repository(args.base_dir, fail_on_warning=args.fail_on_warning)
    if errors:
        print("隐私扫描失败：存在高危敏感信息。")
        return 1
    if args.fail_on_warning and warnings:
        print("隐私扫描失败：存在警告级别敏感信息且已设置为失败。")
        return 1
    print("隐私扫描通过：未发现高危敏感信息。")
    if warnings:
        print(f"注意：发现 {len(warnings)} 条可能的敏感项（未设为失败）。")
    return 0


if __name__ == "__main__":
    # 兼容 Mac 环境要求：用户指定的 Python 解释器路径可直接调用本脚本。
    # 若在 CI 中执行，使用系统的 python3 即可。
    sys.exit(main(sys.argv[1:]))