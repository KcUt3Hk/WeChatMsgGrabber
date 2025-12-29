"""
Message parsing and classification utilities.

This module converts OCR-detected text regions into structured Message
objects, applies simple heuristics to classify message types, and
groups lines that belong to the same chat bubble.
"""
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
import uuid
import logging

from models.data_models import Message, MessageType, TextRegion, ShareCard, QuoteMeta, Rectangle


@dataclass
class ParseOptions:
    """Options to guide parsing behavior."""
    # Maximum vertical gap (in pixels) between lines to consider them the same bubble
    line_grouping_vertical_gap: int = 12
    # Maximum horizontal offset to still consider lines in the same bubble
    line_grouping_horizontal_gap: int = 40
    # X threshold to differentiate left vs right alignment (heuristic)
    left_right_split_x: Optional[int] = None  # If None, inferred from regions
    # Extra sticker keywords provided by caller; merged到内置集合
    extra_sticker_keywords: Optional[List[str]] = None
    # 将“纯emoji或短句+emoji”视为贴图的最大长度阈值（字符数）
    emoji_sticker_max_length: int = 8
    # 紧凑卡片识别开关与阈值
    enable_compact_card: bool = True
    compact_card_min_lines: int = 3
    compact_card_max_lines: int = 12
    compact_card_max_gap_norm: float = 0.6
    compact_card_max_hstd_px: int = 15


class MessageParser:
    """Parses OCR text regions into structured messages."""

    def __init__(self, options: Optional[ParseOptions] = None):
        self.options = options or ParseOptions()

    @staticmethod
    def parse_wechat_time(text: str, reference_date: datetime) -> datetime:
        """Parse WeChat time string to datetime.
        
        Args:
            text: Time string (e.g. "10:00", "Yesterday 10:00", "Monday 10:00", "9月28日 晚上7:22")
            reference_date: Reference date (usually scan date)
            
        Returns:
            datetime: Parsed datetime
        """
        import re
        from datetime import timedelta
        
        text = text.strip()
        
        # Helper to adjust hour for 12-hour format with Chinese period indicators
        def adjust_hour(h: int, period: str) -> int:
            if not period:
                return h
            if period in ['下午', '晚上']:
                if h < 12:
                    return h + 12
            elif period == '凌晨':
                if h == 12:
                    return 0
            # 上午, 早上, 中午 usually don't need adjustment (except 12am/pm edge cases, 
            # but WeChat usually uses 0-24 or consistent 12h. Assuming 12h for periods)
            return h

        # Period regex pattern
        period_pattern = r'(?:(凌晨|早上|上午|中午|下午|晚上)\s*)?'

        # Full date: 2025年12月06日 10:00
        match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*' + period_pattern + r'(\d{1,2})[:：](\d{1,2})', text)
        if match:
            try:
                period = match.group(4)
                h = int(match.group(5))
                h = adjust_hour(h, period)
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), 
                               h, int(match.group(6)))
            except ValueError:
                pass

        # Current year date: 12月06日 10:00 (or 9月28日 晚上7:22)
        match = re.match(r'(\d{1,2})月(\d{1,2})日\s*' + period_pattern + r'(\d{1,2})[:：](\d{1,2})', text)
        if match:
            try:
                period = match.group(3)
                h = int(match.group(4))
                h = adjust_hour(h, period)
                return datetime(reference_date.year, int(match.group(1)), int(match.group(2)), 
                               h, int(match.group(5)))
            except ValueError:
                pass

        # Yesterday: 昨天 10:00
        match = re.match(r'昨天\s*' + period_pattern + r'(\d{1,2})[:：](\d{1,2})', text)
        if match:
            period = match.group(1)
            h = int(match.group(2))
            h = adjust_hour(h, period)
            d = reference_date - timedelta(days=1)
            return d.replace(hour=h, minute=int(match.group(3)), second=0, microsecond=0)

        # Weekday: 星期一 10:00
        weekdays = {'一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '日': 6, '天': 6}
        match = re.match(r'星期([一二三四五六日天])\s*' + period_pattern + r'(\d{1,2})[:：](\d{1,2})', text)
        if match:
            target_wd = weekdays[match.group(1)]
            current_wd = reference_date.weekday()
            days_diff = (current_wd - target_wd) % 7
            if days_diff == 0:
                 days_diff = 7
            d = reference_date - timedelta(days=days_diff)
            period = match.group(2)
            h = int(match.group(3))
            h = adjust_hour(h, period)
            return d.replace(hour=h, minute=int(match.group(4)), second=0, microsecond=0)

        # Today: 10:00
        match = re.match(r'^' + period_pattern + r'(\d{1,2})[:：](\d{1,2})$', text)
        if match:
            try:
                period = match.group(1)
                h = int(match.group(2))
                h = adjust_hour(h, period)
                return reference_date.replace(hour=h, minute=int(match.group(3)), second=0, microsecond=0)
            except ValueError:
                pass

        return reference_date

    def parse(self, regions: List[TextRegion]) -> List[Message]:
        """Parse text regions into messages.

        函数级注释：
        - 改进“发送方归属”判定：不再使用所有区域 x 的简单平均作为左右分割线，
          而是基于“全图近似宽度的中线 + 气泡中心 x”进行更稳健的判断；
        - 保留现有的行聚合（按垂直/水平邻近度分组）逻辑，确保同一气泡的多行文本被合并；
        - 新增“同侧连续气泡的卡片式聚合”逻辑：当相邻的 2-5 个气泡来自同一侧且
          合并文本命中分享卡片启发式（如星巴克礼物），则将这些气泡合并为一条 SHARE 消息；
          该逻辑用于覆盖微信小程序分享卡片在 OCR 中被切分成多行/多块的情况。
        - 在识别分享卡片（小红书/哔哩哔哩/微信小程序）前，对引用气泡进行清洗，
          以避免昵称/时间戳干扰主体内容。
        - [FIX] 修复时间戳问题：引入 current_context_time 状态变量，
          解析系统消息中的时间字符串（如 "9月28日 晚上7:22"）并更新上下文时间；
          后续消息将使用该上下文时间，而非扫描时间 datetime.now()。

        Args:
            regions: OCR 检测到的文本区域列表

        Returns:
            List[Message]: 结构化消息列表
        """
        # print(f"DEBUG: parse called with {len(regions)} regions")
        if not regions:
            return []

        # Sort regions top-to-bottom, then left-to-right for determinism
        regions_sorted = sorted(
            regions,
            key=lambda r: (r.bounding_box.y, r.bounding_box.x)
        )

        # Context time for messages (updates when a time separator is encountered)
        current_context_time = datetime.now()

        # 更稳健的左右分割线：以“全图近似宽度的一半”为基线
        # 若调用方显式提供 left_right_split_x，则优先使用
        split_x = self.options.left_right_split_x
        if split_x is None:
            try:
                # 以所有区域的右侧坐标最大值近似整图宽度（因为区域来自同一整图）
                approx_width = max((r.bounding_box.x + r.bounding_box.width) for r in regions_sorted)
                # 若异常或近似宽度偏小，回退为所有 x 的中位数
                if approx_width <= 0:
                    xs = sorted([r.bounding_box.x for r in regions_sorted])
                    mid = xs[len(xs) // 2] if xs else 0
                    split_x = int(mid)
                else:
                    split_x = int(approx_width * 0.5)
            except Exception:
                xs = sorted([r.bounding_box.x for r in regions_sorted])
                mid = xs[len(xs) // 2] if xs else 0
                split_x = int(mid)

        # Group lines into bubbles using simple proximity heuristics
        bubbles: List[List[TextRegion]] = []
        current_group: List[TextRegion] = []

        for region in regions_sorted:
            if not current_group:
                current_group = [region]
                continue

            last = current_group[-1]
            v_gap_raw = region.bounding_box.y - (last.bounding_box.y + last.bounding_box.height)
            v_gap = v_gap_raw if v_gap_raw > 0 else 0
            h_gap = abs(region.bounding_box.x - last.bounding_box.x)

            if v_gap <= self.options.line_grouping_vertical_gap and h_gap <= self.options.line_grouping_horizontal_gap:
                current_group.append(region)
            else:
                bubbles.append(current_group)
                current_group = [region]

        if current_group:
            bubbles.append(current_group)

        # 预计算每个气泡的元信息，便于后续进行“同侧连续气泡的卡片式聚合”
        bubble_infos = []
        for bubble in bubbles:
            # Apply OCR correction immediately to lines
            lines = [self._correct_text(line.text.strip()) for line in bubble if line.text.strip()]
            content = "\n".join(lines)
            
            # Check if this bubble is a time separator (system message)
            is_time = self._is_time_separator(content)
            
            raw_text = " ".join([line.text for line in bubble])
            avg_conf = sum([line.confidence for line in bubble]) / max(len(bubble), 1)
            # 计算中心 x 与纵向范围
            try:
                centers_x = [ln.bounding_box.x + max(ln.bounding_box.width, 1) / 2.0 for ln in bubble]
                bubble_center_x = sum(centers_x) / max(len(centers_x), 1)
            except Exception:
                bubble_center_x = bubble[0].bounding_box.x
            top_y = min(ln.bounding_box.y for ln in bubble)
            bottom_y = max(ln.bounding_box.y + ln.bounding_box.height for ln in bubble)
            # 计算气泡包围盒（几何用于识别无文字媒体气泡）
            min_x = min(ln.bounding_box.x for ln in bubble)
            max_x = max(ln.bounding_box.x + ln.bounding_box.width for ln in bubble)
            min_y = min(ln.bounding_box.y for ln in bubble)
            max_y = max(ln.bounding_box.y + ln.bounding_box.height for ln in bubble)
            bbox_w = max(1, int(max_x - min_x))
            bbox_h = max(1, int(max_y - min_y))
            sender = "我" if bubble_center_x >= split_x else "对方"
            bubble_infos.append({
                "bubble": bubble,
                "lines": lines,
                "content": content,
                "is_time": is_time,
                "raw_text": raw_text,
                "avg_conf": avg_conf,
                "center_x": bubble_center_x,
                "top_y": top_y,
                "bottom_y": bottom_y,
                "min_x": min_x,
                "min_y": min_y,
                "bbox_w": bbox_w,
                "bbox_h": bbox_h,
                "sender": sender,
            })
        
        # print(f"DEBUG: bubble_infos count: {len(bubble_infos)}")

        messages: List[Message] = []
        i = 0
        # 同侧连续气泡聚合的阈值（像素）：适度放宽以覆盖卡片被分块的情况
        agg_vertical_gap = max(self.options.line_grouping_vertical_gap * 5, 60)
        max_agg_bubbles = 5  # 最多向后合并 5 个气泡，防止过度聚合

        while i < len(bubble_infos):
            info = bubble_infos[i]
            sender = info["sender"]
            merged_lines = list(info["lines"])  # 起始气泡的行
            merged_regions = list(info["bubble"])
            merged_raw = info["raw_text"]
            merged_conf_sum = info["avg_conf"]
            merged_count = 1
            last_bottom_y = info["bottom_y"]
            
            # 尝试向后合并同侧且相邻的气泡
            # 如果当前气泡是时间分隔符，则不进行合并（保持独立以被识别为 SYSTEM）
            j = i + 1
            if not info["is_time"]:
                while j < len(bubble_infos) and (j - i) < max_agg_bubbles:
                    nxt = bubble_infos[j]
                    # 如果下一个气泡是时间分隔符，也不合并（它是独立的系统消息）
                    if nxt["is_time"]:
                        break
                    if nxt["sender"] != sender:
                        break
                    v_gap_raw = nxt["top_y"] - last_bottom_y
                    v_gap = v_gap_raw if v_gap_raw > 0 else 0
                    h_diff = abs(nxt["center_x"] - info["center_x"])  # 同侧卡片通常水平位置接近
                    if v_gap <= agg_vertical_gap and h_diff <= (self.options.line_grouping_horizontal_gap * 2):
                        merged_lines.extend(nxt["lines"])
                        merged_regions.extend(nxt["bubble"])
                        merged_raw += " " + nxt["raw_text"]
                        merged_conf_sum += nxt["avg_conf"]
                        merged_count += 1
                        last_bottom_y = nxt["bottom_y"]
                        j += 1
                    else:
                        break

            merged_content = "\n".join([ln for ln in merged_lines if ln])
            share_card = self._extract_share_card(merged_content)

            merged_has_sticker_region = any(getattr(r, "type", "text") == "sticker" for r in merged_regions)

            # [NEW] Check if merged content looks like an IMAGE (Poster/Ad)
            # But exclude if it looks like a Sticker (short + emoji/mood words)
            if (
                (not merged_has_sticker_region)
                and bool((merged_content or "").strip())
                and (not self._looks_like_sticker_text(merged_lines))
                and self._is_likely_image_with_text(merged_regions, merged_content)
            ):
                # [FIX] If the text is garbage (but large enough to be detected as image), clear it
                if self._is_garbage_text(merged_content):
                    merged_content = ""
                
                # Calculate merged bounding box for image cropping
                min_x = min(r.bounding_box.x for r in merged_regions)
                min_y = min(r.bounding_box.y for r in merged_regions)
                max_x = max(r.bounding_box.x + r.bounding_box.width for r in merged_regions)
                max_y = max(r.bounding_box.y + r.bounding_box.height for r in merged_regions)
                merged_rect = Rectangle(x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y)

                msg_id = str(uuid.uuid4())
                messages.append(
                    Message(
                        id=msg_id,
                        sender=sender,
                        content=merged_content, 
                        message_type=MessageType.IMAGE,
                        timestamp=current_context_time,
                        confidence_score=(merged_conf_sum / merged_count),
                        raw_ocr_text=merged_raw,
                        share_card=None,
                        quote_meta=None,
                        original_region=merged_rect,
                    )
                )
                logging.getLogger(__name__).info(f"📸 Merged bubbles detected as IMAGE. ID={msg_id[-6:]}")
                i = j
                continue

            if share_card:
                # 命中分享卡片：将合并后的内容作为一条 SHARE 消息，跳过已合并的后续气泡
                msg_id = str(uuid.uuid4())
                messages.append(
                    Message(
                        id=msg_id,
                        sender=sender,
                        content=merged_content,
                        message_type=MessageType.SHARE,
                        timestamp=current_context_time,
                        confidence_score=(merged_conf_sum / merged_count),
                        raw_ocr_text=merged_raw,
                        share_card=share_card,
                        quote_meta=None,
                    )
                )
                i = j  # 跳过已合并的气泡
                continue

            # 非分享：若连续同侧小间距气泡形成一句完整文本，合并为单条 TEXT
            if (j - i) >= 2:
                # ...若序列中包含图片/语音/系统提示词，禁止文本合并，避免跨类型合并
                image_hints = ["[图片]", "图片", "photo", "image", "img"]
                voice_hints = ["[语音]", "语音", "voice", "audio"]
                system_hints = ["你已添加", "已成为你的朋友", "系统消息", "joined", "left", "invited"]
                seq_contents = [info.get("content", "")] + [bf.get("content", "") for bf in bubble_infos[i+1:j]]
                has_special = any(
                    any(h in c for h in (image_hints + voice_hints + system_hints))
                    for c in seq_contents
                )
                if (not has_special) and self._should_merge_bubbles_as_text(merged_lines):
                    # 引用清洗在合并后的文本上进行一次，以避免昵称/时间戳影响
                    q_meta, sanitized_merged = self._extract_quote_and_sanitize(list(merged_lines))
                    merged_text = "\n".join([ln for ln in sanitized_merged if ln])
                    msg_id = str(uuid.uuid4())
                    messages.append(
                    Message(
                        id=msg_id,
                        sender=sender,
                        content=merged_text,
                        message_type=MessageType.TEXT if merged_text.strip() else MessageType.UNKNOWN,
                        timestamp=current_context_time,
                        confidence_score=(merged_conf_sum / merged_count),
                        raw_ocr_text=merged_raw,
                        share_card=None,
                        quote_meta=q_meta,
                    )
                )
                    i = j
                    continue

            if self.options.enable_compact_card:
                try:
                    compact = self._is_compact_card(bubble_infos[i:j])
                except Exception:
                    compact = False
                if compact:
                    hints = {"小红书", "哔哩哔哩", "bilibili", "小程序", "微信小程序", "星巴克", "礼物", "查收", "点击打开", "来源"}
                    low = merged_content.lower()
                    has_url = ("http://" in merged_content) or ("https://" in merged_content)
                    has_hint = any((h in merged_content) or (h in low) for h in hints)
                    if has_url or has_hint:
                        sc = self._extract_share_card(merged_content)
                        if not sc:
                            lines_all = [ln.strip() for ln in merged_content.splitlines() if ln.strip()]
                            title = lines_all[0] if lines_all else ""
                            body = "\n".join(lines_all[1:]) if len(lines_all) > 1 else None
                            platform = None
                            if "小红书" in merged_content:
                                platform = "小红书"
                            elif ("哔哩哔哩" in merged_content) or ("bilibili" in low):
                                platform = "哔哩哔哩"
                            elif "小程序" in merged_content or "微信小程序" in merged_content or "星巴克" in merged_content:
                                platform = "微信小程序"
                            import re
                            m = re.search(r"https?://\S+", merged_content)
                            url = m.group(0) if m else None
                            sc = ShareCard(platform=(platform or "分享"), title=title, body=body, source=platform, canonical_url=url)
                        msg_id = str(uuid.uuid4())
                        messages.append(
                            Message(
                                id=msg_id,
                                sender=sender,
                                content=merged_content,
                                message_type=MessageType.SHARE,
                                timestamp=current_context_time,
                                confidence_score=(merged_conf_sum / merged_count),
                                raw_ocr_text=merged_raw,
                                share_card=sc,
                                quote_meta=None,
                            )
                        )
                        i = j
                        continue

            # 未命中分享卡片：回退为单气泡解析与引用清洗
            lines = list(info["lines"])  # 复制以免影响原数据
            quote_meta, sanitized = self._extract_quote_and_sanitize(lines)
            content = "\n".join(sanitized)
            content = self._correct_text(content)
            
            # [NEW] Check for self-scanning first
            if self._is_self_log_text(content):
                logging.getLogger(__name__).warning("⚠️ Detected application logs in scan area. Please move the log window away from the chat window!")
                # Skip this message completely
                i += 1
                continue

            # [FIX] 过滤 OCR 乱码（如误读的表情包），置空后可触发后续的几何识别逻辑
            is_garbage_fallback = False
            if self._is_garbage_text(content):
                # print(f"DEBUG: Garbage text detected: '{content}'")
                content = ""
                is_garbage_fallback = True

            # 时间分隔消息（系统）优先识别，避免被贴图/普通文本误判
            if self._is_time_separator(content):
                # Update context time from the separator text
                # Use current real time as reference for relative dates (Yesterday/Today)
                parsed_t = self.parse_wechat_time(content, datetime.now())
                current_context_time = parsed_t

                msg_id = str(uuid.uuid4())
                messages.append(
                    Message(
                        id=msg_id,
                        sender="系统",
                        content=content,
                        message_type=MessageType.SYSTEM,
                        timestamp=current_context_time,
                        confidence_score=info["avg_conf"],
                        raw_ocr_text=info["raw_text"],
                        share_card=None,
                        quote_meta=None,
                    )
                )
                i += 1
                continue
            # 贴图/表情包识别：在常规类型分类之前进行一次“短句 + 语气词”启发式判断
            # 若命中，则将类型置为 STICKER；文本为空时保留记录并在导出阶段给出备注
            if self._looks_like_sticker_text(sanitized):
                msg_type = MessageType.STICKER
                # 若 OCR 未识别到文字（或全部为空白），仍保留消息记录，文本置空
                if not content.strip():
                    content = ""
            else:
                # 无文字气泡几何识别：当文本为空时，基于包围盒尺寸与长宽比判断媒体气泡
                if not content.strip():
                    has_sticker_region = any(getattr(r, "type", "text") == "sticker" for r in info["bubble"])
                    has_image_region = any(getattr(r, "type", "text") in ("image", "sticker") for r in info["bubble"])
                    
                    bw = int(info.get("bbox_w", 1))
                    bh = int(info.get("bbox_h", 1))
                    area = bw * bh
                    aspect = bw / max(bh, 1)
                    
                    # 绝对阈值：过滤掉极小区域
                    # 如果已有 image 标记，则放宽几何检查（信任上游判断）
                    # [MOD] 放宽阈值以支持较小的表情包/Emoji (原: 60px/5000px -> 40px/2000px)
                    # [FIX] Relax aspect ratio for long screenshots (0.5->0.2) or wide images (2.5->5.0)
                    is_valid_geometry = (min(bw, bh) >= 40 and area >= 2000 and 0.2 <= aspect <= 5.0)
                    
                    if has_sticker_region:
                        msg_type = MessageType.STICKER
                    elif has_image_region or is_valid_geometry:
                        # 当上游已经明确标记为 image 时，优先信任标记，不做“乱码回退”的宽高比否决。
                        if is_garbage_fallback and (not has_image_region):
                            if aspect > 3.0:
                                msg_type = MessageType.UNKNOWN
                                logging.getLogger(__name__).debug(
                                    f"Rejecting garbage fallback as image due to wide aspect {aspect:.2f}"
                                )
                            else:
                                if 0.8 <= aspect <= 1.25 and area <= 25000:
                                    msg_type = MessageType.STICKER
                                else:
                                    msg_type = MessageType.IMAGE
                        else:
                            if 0.8 <= aspect <= 1.25 and area <= 25000:
                                msg_type = MessageType.STICKER
                            else:
                                msg_type = MessageType.IMAGE
                    else:
                        # print("DEBUG: Invalid geometry for empty content, marking UNKNOWN")
                        msg_type = MessageType.UNKNOWN
                else:
                    # [NEW] Check if any region is explicitly marked as image by OCR processor
                    has_sticker_region = any(getattr(r, "type", "text") == "sticker" for r in info["bubble"])
                    has_image_region = any(getattr(r, "type", "text") in ("image", "sticker") for r in info["bubble"])

                    if has_sticker_region:
                        msg_type = MessageType.STICKER
                    elif has_image_region:
                        msg_type = MessageType.IMAGE
                        logging.getLogger(__name__).info(f"📸 Bubble classified as IMAGE by OCR type flag. Content: '{content[:10]}...'")
                    # [NEW] 即使有文字，也可能是包含文字的图片（如海报、广告图）
                    # 结合字体大小、气泡尺寸和内容特征进行判断
                    elif self._is_likely_image_with_text(info["bubble"], content):
                        msg_type = MessageType.IMAGE
                    else:
                        msg_type = self._classify_message_type(content)
            
            # 构造原始区域信息（基于气泡整体包围盒）
            try:
                bubble_rect = None
                if "min_x" in info and "min_y" in info and "bbox_w" in info and "bbox_h" in info:
                    # 确保坐标为整数
                    bx = int(info["min_x"])
                    by = int(info["min_y"])
                    bw = int(info["bbox_w"])
                    bh = int(info["bbox_h"])
                    # 简单校验避免无效区域
                    if bw > 0 and bh > 0:
                        bubble_rect = Rectangle(x=bx, y=by, width=bw, height=bh)
            except Exception:
                bubble_rect = None

            msg_id = str(uuid.uuid4())
            msg = Message(
                id=msg_id,
                sender=sender,
                content=content,
                message_type=msg_type,
                timestamp=current_context_time,
                confidence_score=info["avg_conf"],
                raw_ocr_text=info["raw_text"],
                share_card=None,
                quote_meta=quote_meta,
                original_region=bubble_rect,
            )
            
            # User Requirement: Log type judgment and confidence
            if msg.message_type == MessageType.TEXT and msg.confidence_score < 0.9:
                logging.getLogger(__name__).warning(
                    f"⚠️ Low confidence text ({msg.confidence_score:.2f}): '{msg.content[:20].replace(chr(10), ' ')}...'"
                )
            elif msg.message_type == MessageType.IMAGE:
                 logging.getLogger(__name__).info(
                     f"📸 Classified as IMAGE. ID={msg.id[-6:]}, Conf={msg.confidence_score:.2f}"
                 )
            
            # print(f"DEBUG: Appending message {msg_id}, type={msg_type}, content='{content}'")
            messages.append(msg)
            i += 1

        return messages

    def _is_likely_image_with_text(self, bubble_regions: List[TextRegion], content: str) -> bool:
        """
        Check if a text-containing bubble is likely an image (poster, ad, screenshot).
        
        Criteria:
        1. Large font size: If any text line has height > 40px (heuristic for poster titles).
        2. Sparse layout: Large total height but few lines.
        3. Keywords: Ad/Poster related keywords combined with geometry.
        """
        if not bubble_regions:
            return False
            
        try:
            # 1. Geometry Metrics
            heights = [r.bounding_box.height for r in bubble_regions]
            max_h = max(heights) if heights else 0
            
            min_y = min(r.bounding_box.y for r in bubble_regions)
            max_y = max(r.bounding_box.y + r.bounding_box.height for r in bubble_regions)
            total_h = max_y - min_y
            
            line_count = len(bubble_regions)
            
            # 2. Font Size Heuristic (Poster titles are usually large)
            # Standard chat font is usually 20-30px. 40px is a safe threshold for "Big Title".
            # [Updated] Increased to 60px to account for Retina scaling (2x).
            if max_h >= 60:
                logging.getLogger(__name__).info(f"Image detection: Max line height {max_h} > 60. Content: {content[:20]}...")
                return True
                
            # Safety: If too many lines, it's likely a long text or screenshot of conversation
            if line_count > 10:
                return False
                
            # 3. Layout Heuristic (Large vertical space but sparse text)
            # If total height > 150px and average line spacing is large (> 60px/line)
            # [Updated] Increased threshold to 60px to avoid capturing double-spaced text bubbles.
            if total_h > 150:
                avg_space_per_line = total_h / max(line_count, 1)
                if avg_space_per_line > 60:
                    logging.getLogger(__name__).info(f"Image detection: Sparse layout (H={total_h}, AvgSpace={avg_space_per_line:.1f}). Content: {content[:20]}...")
                    return True
                else:
                    logging.getLogger(__name__).debug(f"Image detection: Sparse layout check failed. H={total_h}, AvgSpace={avg_space_per_line:.1f} <= 60. Content: {content[:20]}...")

            # 4. Content + Layout Heuristic
            # If it contains ad keywords AND has a somewhat large layout
            ad_keywords = ["USDT", "L" + "Bank", "合约", "中奖", "扫码", "二维码", "海报", "发件人", "截图", "详情", "点击", "长按"]
            if any(k in content for k in ad_keywords) and total_h >= 120: # Increased from 80
                logging.getLogger(__name__).info(f"Image detection: Keyword match in large bubble (H={total_h}). Content: {content[:20]}...")
                return True

            # 5. [NEW] Low Text Density Heuristic (Large area but few characters)
            # Example: A photo with just a small logo text or noise
            # Area > 40000 (e.g. 200x200) and char count < 30
            bbox_w = max(r.bounding_box.x + r.bounding_box.width for r in bubble_regions) - min(r.bounding_box.x for r in bubble_regions)
            area = bbox_w * total_h
            if area > 40000 and len(content.strip()) < 30:
                 logging.getLogger(__name__).info(f"Image detection: Low text density (Area={area}, Chars={len(content.strip())}). Content: {content[:20]}...")
                 return True

            # 6. [NEW] Absolute Height Heuristic
            # If a bubble is very tall, it's almost certainly an image (or long screenshot), not a text bubble
            # Standard text bubble rarely exceeds 400px unless it's a copy-paste essay
            if total_h > 300:
                logging.getLogger(__name__).info(f"Image detection: Large height ({total_h} > 300). Content: {content[:20]}...")
                return True

            # 7. [NEW] Small Low-Confidence Heuristic (Stickers/Emojis with garbage text)
            # e.g. a 50x50 sticker detected as text "xx" with low confidence
            avg_conf = sum(r.confidence for r in bubble_regions) / max(len(bubble_regions), 1)
            bbox_w = max(r.bounding_box.x + r.bounding_box.width for r in bubble_regions) - min(r.bounding_box.x for r in bubble_regions)
            area = bbox_w * total_h
            if area >= 900 and area <= 40000 and len(content.strip()) < 8 and avg_conf < 0.6:
                 logging.getLogger(__name__).info(f"Image detection: Small low-conf bubble (Area={area}, Conf={avg_conf:.2f}, Text='{content}').")
                 return True

            # Log why we failed if it was somewhat large
            if total_h > 100:
                logging.getLogger(__name__).info(f"Image detection REJECTED: H={total_h}, MaxH={max_h}, LineCount={line_count}. Content: {content[:20]}...")
                
        except Exception as e:
            logging.getLogger(__name__).error(f"Image detection error: {e}")
            pass
        
        return False

    def _classify_message_type(self, content: str) -> MessageType:
        """Classify the message type based on content heuristics.

        This is a simple baseline classifier using keywords; a production
        implementation can combine visual cues and richer patterns.
        """
        text = content.lower()
        # Common hints (Chinese and English)
        image_hints = ["[图片]", "图片", "photo", "image", "img"]
        voice_hints = ["[语音]", "语音", "voice", "audio"]
        system_hints = ["你已添加", "已成为你的朋友", "系统消息", "joined", "left", "invited"]

        if any(hint in content for hint in image_hints):
            return MessageType.IMAGE
        if any(hint in content for hint in voice_hints):
            return MessageType.VOICE
        if any(hint in content for hint in system_hints):
            return MessageType.SYSTEM

        # Default to TEXT if content is non-empty
        if content.strip():
            return MessageType.TEXT
        return MessageType.UNKNOWN

    def _is_time_separator(self, content: str) -> bool:
        try:
            if not content:
                return False
            text = content.strip()
            # 单行或两行，常见“日期/时间/星期”分隔
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if len(lines) > 2:
                return False
            import re
            def _weekday_line(s: str) -> bool:
                return bool(re.match(r"^\s*(星期|周)[一二三四五六日天]\s*[凌晨|早上|上午|中午|下午|晚上]?\s*[0-2]?\d:\d{2}\s*$", s))
            
            # Debugging
            # print(f"DEBUG: Checking time separator for '{text}'")
            
            # 复用时间戳行判定 + 扩展星期形式
            if all((self._is_timestamp_line(ln) or _weekday_line(ln)) for ln in lines):
                # 排除含其它汉字的复杂文本：仅允许“星期X/周X/今天/昨天/前天/纯时间/日期”组合
                pure = re.sub(r"[0-9\s:年/月日号\-\.今天昨天前天星期周一二三四五六日天凌晨早上午中午下午晚上]", "", text)
                if len(pure.strip()) == 0:
                    return True
                # else:
                #    print(f"DEBUG: Failed pure check. Pure: '{pure}'")
            
            # 兼容紧凑形式：如“星期五23:53”（无空格）
            if _weekday_line(text):
                return True
            return False
        except Exception as e:
            # print(f"DEBUG: Exception in _is_time_separator: {e}")
            return False

    def _is_self_log_text(self, content: str) -> bool:
        """Check if text looks like the application's own logs (self-scanning)."""
        if not content:
            return False
        # Keywords that appear in the app's own logs or UI
        keywords = [
            "[WARNING]", "[INFO]", "[ERROR]", "[DEBUG]", "[HARNING]", "[CRITICAL]",
            "services.message_parser", "confidence text", 
            "运行日志", "Run logs", "Image detection:", 
            "Low confidence text"
        ]
        return any(k in content for k in keywords)

    def _is_garbage_text(self, text: str) -> bool:
        """Check if text is likely OCR garbage/hallucination from emojis.
        
        函数级注释：
        - 识别并过滤 PaddleOCR 在表情包/Emoji 上产生的典型乱码（如 '4:8080/#'）；
        - 启发式规则：
        1. 包含特定乱码模式（如 '4:8080'）；
        2. 长字符串（>15字符）且无空格、非 URL，看起来像乱码；
        3. 纯符号或极短且无意义的字符组合。
        4. [NEW] 包含常见的 OCR 幻觉模式（如 'itext', 'tcxt', 'confidence' 等非正常文本）。
        5. [NEW] 过滤 UI 元素误识别（如 '最大滚动', '输出目录'）。
        """
        if not text:
            return False
        
        t = text.strip()
        
        # 1. 已知乱码黑名单 (用户反馈)
        blacklist = ["4:8080/#", "p-diveintotheprotocolsdefiningthepos"]
        if t in blacklist:
            return True
            
        # 2. 包含 '4:8080' 这种典型端口号样式的误读
        if "4:8080" in t:
            return True
            
        # 3. UI 元素关键词过滤 (针对用户反馈的误识别)
        ui_keywords = [
            "最大滚动", "全量模式", "输出目录", "fUsers/", "格式：", "前缀：", 
            "SPM范围", "聊天区域", "激动控制", "aut", "圜口标题"
        ]
        if any(k in t for k in ui_keywords):
            return True
            
        # 4. 极短且全为非中英文字符（纯符号/数字混合）
        import re
        # Allow some punctuation but if it's ONLY punctuation/symbols/digits (and short)
        if len(t) < 8 and re.match(r"^[0-9:/.#@$%^&*()_+\-=\[\]{}|;<>?~`'\" ]*$", t):
            # 排除纯数字（可能是金额或验证码）
            if not t.replace(" ", "").isdigit():
                return True

        # 4. [NEW] Common OCR hallucinations observed in logs
        # e.g. 'itext', 'tcxt', 'text (0.85)', '(.87):'
        low_t = t.lower()
        if "text" in low_t or "conf" in low_t or "txt" in low_t:
             # If it looks like "text (0.xx)" pattern
             if re.search(r"(?:text|txt|conf).*[\(（].*[\)）]", low_t):
                 return True
             # If it looks like just "text" or "itext"
             if low_t in ["text", "itext", "tcxt", "confidence"]:
                 return True

        # 5. [NEW] Repeated patterns of nonsense
        if re.match(r'^[\(\)0-9a-zA-Z\.: ]{1,10}$', t):
             # Short alphanumeric string that isn't a word?
             # Hard to say without dictionary. But "0.BS" is garbage.
             if "0.b" in low_t or "o.b" in low_t:
                 return True
                
        return False

    def _is_timestamp_line(self, text: str) -> bool:
        """Check if a line looks like a timestamp."""
        import re
        # "10:00", "Yesterday 10:00", "2023年10月1日 10:00"
        if re.match(r'^(\d{4}年)?(\d{1,2}月\d{1,2}日|昨天|今天|前天)?\s*([凌晨|早上|上午|中午|下午|晚上])?\s*\d{1,2}[:：]\d{2}$', text.strip()):
            return True
        return False
        
    def _correct_text(self, text: str) -> str:
        """Apply simple OCR corrections."""
        # Replace common OCR errors if needed
        return text

    def _looks_like_sticker_text(self, lines: List[str]) -> bool:
        """Check if text looks like a sticker description (short, emojis, mood words)."""
        if not lines:
            return False
        content = "\n".join(lines).strip()
        
        # DEBUG
        # print(f"DEBUG: Checking sticker for '{content}' len={len(content)} ord={[ord(c) for c in content]}")
        
        if len(content) > self.options.emoji_sticker_max_length:
            return False
            
        # 1. Common sticker phrases (mood words)
        sticker_keywords = ["晚安", "早安", "哈哈", "收到", "好的", "OK", "ok", "谢谢", "加油", "开心", "难过", "流泪", "再见", "拜拜", "打卡"]
        if any(k in content for k in sticker_keywords):
            return True
            
        # 2. Repeated chars (e.g. "？？？", "！！！", "哈哈哈")
        # If it's short and repetitive, and not just basic punctuation/digits
        if len(set(content)) == 1 and len(content) >= 1:
             import re
             # Exclude simple punctuation/digits (e.g. "...", "111")
             if not re.match(r'^[a-zA-Z0-9\.,;\'"\?!\-]+$', content):
                 return True

        # 3. Contains Emoji (Simple heuristic)
        # Check for high unicode code points (Supplementary Planes) where many emojis live
        # Also check BMP emojis (e.g. ☺ which is 0x263A, or others in 0x2000-0x3000 range? No, most are > 0x1F000)
        # But wait, 0x1F000 is 126976.
        # ord('😄') is 128516. 128516 > 126976. So it should be True.
        if any(ord(c) > 0x1F000 for c in content):
            # print(f"DEBUG: Found emoji char {ord(content[0])}")
            return True
            
        return False

    def _extract_share_card(self, content: str) -> Optional[ShareCard]:
        """Extract share card info from content."""
        import re

        raw_lines = [ln.strip() for ln in (content or "").splitlines()]
        lines = [ln for ln in raw_lines if ln]
        if not lines:
            return None

        low_all = "\n".join(lines).lower()
        url_match = re.search(r"https?://\S+", "\n".join(lines))
        url = url_match.group(0) if url_match else None

        joined = "\n".join(lines)

        platform: Optional[str] = None
        if any(ln == "小红书" for ln in lines) or ("xiaohongshu.com" in low_all):
            platform = "小红书"
        elif any(ln in ("哔哩哔哩", "bilibili") for ln in lines) or ("bilibili.com" in low_all):
            platform = "哔哩哔哩" if any(ln == "哔哩哔哩" for ln in lines) else "bilibili"
        elif any(ln in ("微信小程序", "小程序") for ln in lines) or ("miniapp" in low_all):
            platform = "微信小程序"

        has_source = "来源" in joined
        has_platform_label = bool(platform) and any(ln == platform for ln in lines)
        looks_like_share = bool(url) or has_source or (has_platform_label and len(lines) >= 3)
        if not looks_like_share:
            return None

        source: Optional[str] = None
        up_name: Optional[str] = None
        play_count: Optional[int] = None

        def _parse_play_count(s: str) -> Optional[int]:
            t = (s or "").strip()
            t = t.replace(",", "")
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([万亿]?)", t)
            if not m:
                return None
            try:
                val = float(m.group(1))
            except Exception:
                return None
            unit = m.group(2)
            mul = 1
            if unit == "万":
                mul = 10_000
            elif unit == "亿":
                mul = 100_000_000
            return int(round(val * mul))

        body_lines: list[str] = []
        for ln in lines:
            if ln.startswith("来源：") or ln.startswith("来源:"):
                source = ln.split("：", 1)[1] if "：" in ln else ln.split(":", 1)[1]
                source = source.strip() if source else None
                continue
            if ln.startswith("UP主：") or ln.startswith("UP主:"):
                up_name = ln.split("：", 1)[1] if "：" in ln else ln.split(":", 1)[1]
                up_name = up_name.strip() if up_name else None
                continue
            if ln.startswith("播放量：") or ln.startswith("播放量:"):
                val = ln.split("：", 1)[1] if "：" in ln else ln.split(":", 1)[1]
                play_count = _parse_play_count(val)
                continue
            if ln.startswith("http://") or ln.startswith("https://"):
                continue
            body_lines.append(ln)

        title = ""
        body: Optional[str] = None
        if platform and body_lines and body_lines[0] == platform:
            if len(body_lines) >= 2:
                title = body_lines[1]
                rest = body_lines[2:]
            else:
                title = body_lines[0]
                rest = []
        else:
            title = body_lines[0] if body_lines else lines[0]
            rest = body_lines[1:] if body_lines else []

        if rest:
            body = "\n".join(rest).strip() or None

        if platform == "微信小程序" and not source:
            for ln in lines:
                if "星巴克" in ln:
                    source = "星巴克"
                    break

        return ShareCard(
            platform=(platform or "分享"),
            title=title,
            body=body,
            source=source or platform,
            up_name=up_name,
            play_count=play_count,
            canonical_url=url,
        )

    def _extract_quote_and_sanitize(self, lines: List[str]):
        """Extract quote meta and return sanitized lines."""
        if not lines:
            return None, lines

        cleaned = [ln.strip() for ln in lines if (ln or "").strip()]
        if len(cleaned) < 3:
            return None, cleaned

        first = cleaned[0]
        second = cleaned[1]
        if self._is_timestamp_line(first) or self._is_timestamp_line(second):
            return None, cleaned

        nickname = first.replace("<", "").replace(">", "").strip()
        quoted_text = second.strip()
        label = "我" if nickname.startswith("我") else "对方"
        meta = QuoteMeta(original_nickname=nickname, original_sender_label=label, quoted_text=quoted_text)

        sanitized: list[str] = [quoted_text]
        for ln in cleaned[2:]:
            if self._is_timestamp_line(ln):
                continue
            sanitized.append(ln)

        return meta, sanitized

    def _is_compact_card(self, bubble_infos) -> bool:
        """Check if bubbles form a compact card."""
        try:
            infos = list(bubble_infos or [])
            if not infos:
                return False
            regions: list[TextRegion] = []
            for info in infos:
                regions.extend(info.get("bubble", []) or [])
            if not regions:
                return False

            regions_sorted = sorted(regions, key=lambda r: (r.bounding_box.y, r.bounding_box.x))
            line_count = len(regions_sorted)
            if line_count < self.options.compact_card_min_lines or line_count > self.options.compact_card_max_lines:
                return False

            gaps = []
            for a, b in zip(regions_sorted, regions_sorted[1:]):
                raw = b.bounding_box.y - (a.bounding_box.y + a.bounding_box.height)
                gaps.append(raw if raw > 0 else 0)
            avg_h = sum(r.bounding_box.height for r in regions_sorted) / max(1, line_count)
            avg_h = max(1.0, float(avg_h))
            max_gap_norm = (max(gaps) / avg_h) if gaps else 0.0
            if max_gap_norm > float(self.options.compact_card_max_gap_norm):
                return False

            xs = [r.bounding_box.x for r in regions_sorted]
            mx = sum(xs) / max(1, len(xs))
            var = sum((x - mx) ** 2 for x in xs) / max(1, len(xs))
            hstd = var ** 0.5
            return hstd <= float(self.options.compact_card_max_hstd_px)
        except Exception:
            return False

    def _should_merge_bubbles_as_text(self, lines: List[str]) -> bool:
        """Check if bubbles should be merged as text."""
        if not lines:
            return False
        cleaned = [ln.strip() for ln in lines if (ln or "").strip()]
        if len(cleaned) < 2:
            return False
        merged = "\n".join(cleaned)
        low = merged.lower()
        if "http://" in low or "https://" in low:
            return False
        hints = ("小红书", "哔哩哔哩", "bilibili", "小程序", "微信小程序", "来源：")
        if any(h in merged for h in hints):
            return False
        if sum(len(x) for x in cleaned) > 400:
            return False
        return True
