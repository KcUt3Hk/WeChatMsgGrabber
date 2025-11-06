#!/Users/pankkkk/Projects/Setting/python_envs/bin/python3.12
"""
合并导出工具（merge_exports.py）

用途：
- 将多个导出的 JSON 文件（来自 auto_wechat_scan / full_timeline_scan / run_extraction 等）进行合并、去重，并输出为 JSON/CSV（可选 Markdown）。
- 支持排除无分析价值字段（如 raw_ocr_text）、过滤纯时间/日期分隔消息、可选激进内容级去重（sender+content）。

使用示例：
  python3 cli/merge_exports.py \
    --inputs ./outputs/full_timeline/initial_full_timeline_20251106_193223.json \
            ./outputs/auto_full/auto_wechat_scan_20251106_193600.json \
    --outdir ./outputs/merged_full \
    --formats json,csv \
    --exclude-fields raw_ocr_text \
    --exclude-time-only

注意：
- 代码包含函数级注释，便于后续维护与扩展。
- 该脚本不依赖项目的内部模型与服务模块，直接处理导出的 JSON 列表结构。
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
from typing import Dict, List, Tuple, Iterable


def _ensure_dir(path: str) -> None:
    """确保输出目录存在。

    参数:
        path: 目录路径。
    """
    os.makedirs(path, exist_ok=True)


def _normalize_text(text: str) -> str:
    """规范化文本以用于稳定键与去重。

    处理内容:
    - 去除前后空白。
    - 将连续空白（空格、制表符、换行）折叠为单个空格。
    - 保留基本标点与 emoji 字符。

    参数:
        text: 原始文本。

    返回:
        规范化后的文本字符串。
    """
    if text is None:
        return ""
    s = str(text)
    # 移除常见的零宽与方向控制字符，统一全角冒号为半角
    s = s.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    s = s.replace("\u200e", "").replace("\u200f", "")
    s = s.replace("：", ":")
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _normalize_timestamp(ts: str) -> str:
    """规范化时间戳到秒级 ISO 格式（YYYY-MM-DDTHH:MM:SS）。

    支持输入包含毫秒/微秒的 ISO 字符串，或无 'T' 的日期时间字符串。

    参数:
        ts: 原始时间戳字符串。

    返回:
        规范化后的秒级 ISO 时间戳。如果解析失败，返回原始字符串去除小数部分。
    """
    if not ts:
        return ""
    s = str(ts).strip()
    # 尝试简单截断小数部分
    if "." in s:
        s = s.split(".")[0]
    # 若缺少 'T'，尝试替换空格为 'T'
    if "T" not in s and " " in s:
        s = s.replace(" ", "T")
    # 尝试用 datetime 解析
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt_obj = dt.datetime.strptime(s, fmt)
            return dt_obj.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
    # 兜底返回
    return s


def _stable_key(msg: Dict) -> str:
    """计算消息的稳定去重键。

    规则:
    - 优先使用 id（非空）: "id:<id>"。
    - 否则使用 "sender|timestamp|content" 组合（均为规范化值，时间戳到秒级）。

    参数:
        msg: 消息字典，期望包含 sender/content/timestamp 等键。

    返回:
        用于去重的稳定键字符串。
    """
    if msg is None:
        return ""
    mid = str(msg.get("id", "")).strip()
    if mid:
        return f"id:{mid}"
    sender = _normalize_text(msg.get("sender", "")).lower()
    ts = _normalize_timestamp(msg.get("timestamp", ""))
    content = _normalize_text(msg.get("content", ""))
    return f"{sender}|{ts}|{content}"


def _aggressive_key(msg: Dict) -> str:
    """激进内容级去重键：仅使用 sender+content，用于减少同轮重复。

    参数:
        msg: 消息字典。

    返回:
        基于发送者与内容的键。
    """
    sender = _normalize_text(msg.get("sender", "")).lower()
    content = _normalize_text(msg.get("content", ""))
    return f"{sender}|{content}"


def _is_time_only_separator(text: str) -> bool:
    """判断文本是否为“纯时间/日期/星期”等分隔消息。

    该函数实现与 README 中的描述一致，覆盖常见中文日期、时间与星期格式，并包含宽松兜底规则。

    参数:
        text: 文本内容。

    返回:
        True 表示应视作分隔消息并在过滤时移除；False 表示保留。
    """
    s = _normalize_text(text)
    if not s:
        return False

    patterns = [
        r"^\d{4}年\d{1,2}月\d{1,2}日$",
        r"^\d{1,2}月\d{1,2}日(?:\s*\d{1,2}:\d{2}(?::\d{2})?)?$",
        r"^\d{1,2}:\d{2}(?::\d{2})?$",
        r"^星期[一二三四五六日天]$",
        r"^周[一二三四五六日天]$",
        r"^星期[一二三四五六日天]\s*\d{1,2}:\d{2}(?::\d{2})?$",
        r"^周[一二三四五六日天]\s*\d{1,2}:\d{2}(?::\d{2})?$",
        r"^(?:昨天|今天|前天)(?:\s*\d{1,2}:\d{2})?$",
        r"^(?:下午|上午|中午|凌晨|傍晚|晚间|早上|早晨)\s*\d{1,2}:\d{2}(?::\d{2})?$",
        r"^(?:AM|PM)\s*\d{1,2}:\d{2}(?::\d{2})?$",
    ]
    for p in patterns:
        if re.fullmatch(p, s):
            return True

    # 宽松兜底：仅数字/空格/冒号/日期/星期单位组成，且包含日期/星期单位或时间冒号
    if re.fullmatch(r"[0-9\s:\./\-年月日星期周]+", s):
        if any(ch in s for ch in ["年", "月", "日", "星期", "周", ":", "/", ".", "-"]):
            return True

    return False


def load_messages_from_file(path: str) -> List[Dict]:
    """从 JSON 文件加载消息列表。

    要求文件顶层为列表，每个元素为包含 sender/content/timestamp 等键的字典。

    参数:
        path: JSON 文件路径。

    返回:
        消息字典列表；解析失败时返回空列表。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        return []
    except Exception as e:
        print(f"[WARN] 加载失败: {path} -> {e}")
        return []


def discover_input_files(inputs: Iterable[str]) -> List[str]:
    """发现输入文件列表。

    - 若为文件路径（.json），直接纳入。
    - 若为目录，扫描其中的 .json 文件（忽略 .dedup_index.json）。

    参数:
        inputs: 文件或目录路径迭代。

    返回:
        去重后的 JSON 文件路径列表（按路径排序）。
    """
    files: List[str] = []
    for p in inputs:
        if not p:
            continue
        p = os.path.abspath(p)
        if os.path.isfile(p) and p.lower().endswith(".json"):
            files.append(p)
        elif os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                fp = os.path.join(p, name)
                if os.path.isfile(fp) and fp.lower().endswith(".json"):
                    if os.path.basename(fp) == ".dedup_index.json":
                        continue
                    files.append(fp)
    # 去重
    uniq = sorted(set(files))
    return uniq


def merge_messages(
    input_files: List[str],
    exclude_time_only: bool = False,
    aggressive_dedup: bool = False,
) -> List[Dict]:
    """合并多个 JSON 文件中的消息并去重。

    去重策略：
    - 默认使用稳定键 `_stable_key(msg)` 跨文件去重；
    - 当 `aggressive_dedup=True` 时，额外使用 `_aggressive_key(msg)` 进行内容级去重，减少同轮重复；
    - 保留合并后顺序按时间戳排序（无法解析的时间戳按原始加载顺序）。

    参数:
        input_files: 需要合并的 JSON 文件路径列表。
        exclude_time_only: 是否过滤纯时间/日期/星期分隔消息。
        aggressive_dedup: 是否启用激进内容级去重。

    返回:
        合并后的消息列表（字典）。
    """
    seen_stable: set = set()
    seen_aggr: set = set()
    merged: List[Dict] = []

    total_loaded = 0
    for fp in input_files:
        msgs = load_messages_from_file(fp)
        total_loaded += len(msgs)
        for m in msgs:
            if exclude_time_only and _is_time_only_separator(m.get("content", "")):
                continue
            key = _stable_key(m)
            if key in seen_stable:
                continue
            if aggressive_dedup:
                akey = _aggressive_key(m)
                if akey in seen_aggr:
                    continue
                seen_aggr.add(akey)
            seen_stable.add(key)
            merged.append(m)

    # 尝试按时间戳排序（解析失败的保持相对顺序）
    def _ts_key(m: Dict) -> Tuple[int, str]:
        ts = _normalize_timestamp(m.get("timestamp", ""))
        try:
            dt_obj = dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
            return (0, dt_obj.isoformat())
        except Exception:
            return (1, ts)

    merged_sorted = sorted(merged, key=_ts_key)
    print(f"[INFO] 已加载 {total_loaded} 条，合并后 {len(merged_sorted)} 条（去重后）。")
    return merged_sorted


def exclude_fields(messages: List[Dict], fields: List[str]) -> List[Dict]:
    """从消息字典中移除指定字段。

    参数:
        messages: 消息列表。
        fields: 需要移除的字段名列表。

    返回:
        处理后的消息列表（新对象）。
    """
    if not fields:
        return messages
    out: List[Dict] = []
    for m in messages:
        nm = dict(m)
        for f in fields:
            nm.pop(f, None)
        out.append(nm)
    return out


def save_json(messages: List[Dict], out_path: str) -> None:
    """保存为 JSON 文件（UTF-8，缩进 2）。

    参数:
        messages: 消息列表。
        out_path: 输出文件路径。
    """
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 写入 JSON: {out_path}")


def save_csv(messages: List[Dict], out_path: str) -> None:
    """保存为 CSV 文件（UTF-8）。

    字段自动从首条消息推断；若没有消息则写入空文件并给出提示。

    参数:
        messages: 消息列表。
        out_path: 输出文件路径。
    """
    if not messages:
        # 写入空文件避免后续流程报错
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            pass
        print(f"[WARN] 无消息可写入 CSV: {out_path}")
        return

    # 常见字段顺序优先；其余字段按字母序补充
    common = ["id", "sender", "content", "message_type", "timestamp", "confidence_score"]
    keys = list(messages[0].keys())
    # 合并顺序：common（存在的） + 其余（字母序）
    ordered = [k for k in common if k in keys]
    extra = sorted([k for k in keys if k not in ordered])
    fieldnames = ordered + extra

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for m in messages:
            writer.writerow({k: m.get(k, "") for k in fieldnames})
    print(f"[INFO] 写入 CSV: {out_path}")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    返回:
        argparse.Namespace 对象，包含输入/输出/过滤/去重等设置。
    """
    p = argparse.ArgumentParser(description="Merge exported WeChat messages across JSON files")
    p.add_argument("--inputs", nargs="*", help="输入文件或目录（.json）；可重复传入多个路径")
    p.add_argument("--outdir", default=os.path.abspath("./outputs/merged_full"), help="输出目录（默认 ./outputs/merged_full）")
    p.add_argument("--formats", default="json,csv", help="导出格式列表（逗号分隔）：json,csv,md")
    p.add_argument("--filename-prefix", default=f"merged_wechat_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}", help="输出文件名前缀")
    p.add_argument("--exclude-fields", default="", help="在导出中移除的字段（逗号分隔），如 raw_ocr_text,confidence_score")
    p.add_argument("--exclude-time-only", action="store_true", help="过滤纯时间/日期分隔消息")
    p.add_argument("--aggressive-dedup", action="store_true", help="启用激进内容级去重（sender+content）")
    return p.parse_args()


def main() -> None:
    """脚本入口：执行合并、去重与保存。

    处理流程:
    1. 解析 CLI 参数；
    2. 发现输入文件并加载消息；
    3. 合并与去重（可选过滤分隔消息、激进去重）；
    4. 移除指定字段；
    5. 按需保存为 JSON/CSV/MD。
    """
    args = parse_args()
    inputs = args.inputs or []
    files = discover_input_files(inputs)
    if not files:
        print("[ERROR] 未发现可用的输入文件，请检查 --inputs 参数。")
        return
    print("[INFO] 待合并文件：")
    for fp in files:
        print(f"  - {fp}")

    msgs = merge_messages(files, exclude_time_only=args.exclude_time_only, aggressive_dedup=args.aggressive_dedup)
    # 字段排除
    exclude = [s.strip() for s in (args.exclude_fields or "").split(",") if s.strip()]
    msgs = exclude_fields(msgs, exclude)

    # 输出
    _ensure_dir(args.outdir)
    formats = set([s.strip().lower() for s in (args.formats or "json,csv").split(",") if s.strip()])
    base = os.path.join(args.outdir, args.filename_prefix)
    if "json" in formats:
        save_json(msgs, base + ".json")
    if "csv" in formats:
        save_csv(msgs, base + ".csv")
    if "md" in formats:
        # 简易 Markdown 导出（可后续替换为 StorageManager 的更丰富格式）
        md_path = base + ".md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# 合并导出（部分片段）\n\n")
            for m in msgs:
                ts = m.get("timestamp", "")
                sender = m.get("sender", "")
                content = m.get("content", "")
                f.write(f"- [{ts}] {sender}: {content}\n")
        print(f"[INFO] 写入 Markdown: {md_path}")

    print("[DONE] 合并导出完成。")


if __name__ == "__main__":
    main()