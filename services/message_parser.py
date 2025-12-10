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

from models.data_models import Message, MessageType, TextRegion, ShareCard, QuoteMeta


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
            text: Time string (e.g. "10:00", "Yesterday 10:00", "Monday 10:00")
            reference_date: Reference date (usually scan date)
            
        Returns:
            datetime: Parsed datetime
        """
        import re
        from datetime import timedelta
        
        text = text.strip()
        
        # Full date: 2025年12月06日 10:00
        match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})[:：](\d{1,2})', text)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), 
                               int(match.group(4)), int(match.group(5)))
            except ValueError:
                pass

        # Current year date: 12月06日 10:00
        match = re.match(r'(\d{1,2})月(\d{1,2})日\s*(\d{1,2})[:：](\d{1,2})', text)
        if match:
            try:
                return datetime(reference_date.year, int(match.group(1)), int(match.group(2)), 
                               int(match.group(3)), int(match.group(4)))
            except ValueError:
                pass

        # Yesterday: 昨天 10:00
        match = re.match(r'昨天\s*(\d{1,2})[:：](\d{1,2})', text)
        if match:
            d = reference_date - timedelta(days=1)
            return d.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0)

        # Weekday: 星期一 10:00
        weekdays = {'一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '日': 6, '天': 6}
        match = re.match(r'星期([一二三四五六日天])\s*(\d{1,2})[:：](\d{1,2})', text)
        if match:
            target_wd = weekdays[match.group(1)]
            current_wd = reference_date.weekday()
            days_diff = (current_wd - target_wd) % 7
            if days_diff == 0:
                 days_diff = 7
            d = reference_date - timedelta(days=days_diff)
            return d.replace(hour=int(match.group(2)), minute=int(match.group(3)), second=0, microsecond=0)

        # Today: 10:00
        match = re.match(r'^(\d{1,2})[:：](\d{1,2})$', text)
        if match:
            try:
                return reference_date.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0)
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

        Args:
            regions: OCR 检测到的文本区域列表

        Returns:
            List[Message]: 结构化消息列表
        """
        if not regions:
            return []

        # Sort regions top-to-bottom, then left-to-right for determinism
        regions_sorted = sorted(
            regions,
            key=lambda r: (r.bounding_box.y, r.bounding_box.x)
        )

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
            v_gap = abs(region.bounding_box.y - last.bounding_box.y)
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
            lines = [line.text.strip() for line in bubble if line.text.strip()]
            content = "\n".join(lines)
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
                "raw_text": raw_text,
                "avg_conf": avg_conf,
                "center_x": bubble_center_x,
                "top_y": top_y,
                "bottom_y": bottom_y,
                "bbox_w": bbox_w,
                "bbox_h": bbox_h,
                "sender": sender,
            })

        messages: List[Message] = []
        i = 0
        # 同侧连续气泡聚合的阈值（像素）：适度放宽以覆盖卡片被分块的情况
        agg_vertical_gap = max(self.options.line_grouping_vertical_gap * 5, 60)
        max_agg_bubbles = 5  # 最多向后合并 5 个气泡，防止过度聚合

        while i < len(bubble_infos):
            info = bubble_infos[i]
            sender = info["sender"]
            merged_lines = list(info["lines"])  # 起始气泡的行
            merged_raw = info["raw_text"]
            merged_conf_sum = info["avg_conf"]
            merged_count = 1
            last_bottom_y = info["bottom_y"]
            # 尝试向后合并同侧且相邻的气泡
            j = i + 1
            while j < len(bubble_infos) and (j - i) < max_agg_bubbles:
                nxt = bubble_infos[j]
                if nxt["sender"] != sender:
                    break
                v_gap = abs(nxt["top_y"] - last_bottom_y)
                h_diff = abs(nxt["center_x"] - info["center_x"])  # 同侧卡片通常水平位置接近
                if v_gap <= agg_vertical_gap and h_diff <= (self.options.line_grouping_horizontal_gap * 2):
                    merged_lines.extend(nxt["lines"])
                    merged_raw += " " + nxt["raw_text"]
                    merged_conf_sum += nxt["avg_conf"]
                    merged_count += 1
                    last_bottom_y = nxt["bottom_y"]
                    j += 1
                else:
                    break

            merged_content = "\n".join([ln for ln in merged_lines if ln])
            share_card = self._extract_share_card(merged_content)

            if share_card:
                # 命中分享卡片：将合并后的内容作为一条 SHARE 消息，跳过已合并的后续气泡
                msg_id = str(uuid.uuid4())
                messages.append(
                    Message(
                        id=msg_id,
                        sender=sender,
                        content=merged_content,
                        message_type=MessageType.SHARE,
                        timestamp=datetime.now(),
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
                # 若序列中包含图片/语音/系统提示词，禁止文本合并，避免跨类型合并
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
                        timestamp=datetime.now(),
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
                                timestamp=datetime.now(),
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
            # 时间分隔消息（系统）优先识别，避免被贴图/普通文本误判
            if self._is_time_separator(content):
                msg_id = str(uuid.uuid4())
                messages.append(
                    Message(
                        id=msg_id,
                        sender="系统",
                        content=content,
                        message_type=MessageType.SYSTEM,
                        timestamp=datetime.now(),
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
                    bw = int(info.get("bbox_w", 1))
                    bh = int(info.get("bbox_h", 1))
                    area = bw * bh
                    aspect = bw / max(bh, 1)
                    # 绝对阈值：过滤掉极小区域
                    if min(bw, bh) >= 60 and area >= 5000 and 0.5 <= aspect <= 2.5:
                        # 更接近正方形、且面积中等的气泡倾向判定为贴图；否则为图片
                        if 0.8 <= aspect <= 1.25 and area <= 25000:
                            msg_type = MessageType.STICKER
                        else:
                            msg_type = MessageType.IMAGE
                    else:
                        msg_type = MessageType.UNKNOWN
                else:
                    msg_type = self._classify_message_type(content)
            msg_id = str(uuid.uuid4())
            messages.append(
                Message(
                    id=msg_id,
                    sender=sender,
                    content=content,
                    message_type=msg_type,
                    timestamp=datetime.now(),
                    confidence_score=info["avg_conf"],
                    raw_ocr_text=info["raw_text"],
                    share_card=None,
                    quote_meta=quote_meta,
                )
            )
            i += 1

        return messages

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
                return bool(re.match(r"^\s*(星期|周)[一二三四五六日天]\s*[上|下]?午?\s*[0-2]?\d:\d{2}\s*$", s))
            # 复用时间戳行判定 + 扩展星期形式
            if all((self._is_timestamp_line(ln) or _weekday_line(ln)) for ln in lines):
                # 排除含其它汉字的复杂文本：仅允许“星期X/周X/今天/昨天/前天/纯时间/日期”组合
                pure = re.sub(r"[0-9\s:年/月日\-\.今天昨天前天星期周一二三四五六日天上下午]", "", text)
                return len(pure.strip()) == 0
            # 兼容紧凑形式：如“星期五23:53”（无空格）
            if _weekday_line(text):
                return True
            return False
        except Exception:
            return False

    def _should_merge_bubbles_as_text(self, lines: List[str]) -> bool:
        """判断多气泡文本是否应合并为单条文本消息。
        条件（保守）：
        - 总行数在 2-8 之间；
        - 合并文本不包含 URL 或明显平台/来源关键词（避免误并分享卡片，已在前面检测）；
        - 最前一段末尾不以句末标点结束（中文“。！？…”或英文 .!?），且整体中文字符比例较高；
        - 非时间分隔（避免将日期时间并入普通文本）。
        """
        try:
            if not lines:
                return False
            valid = [ln.strip() for ln in lines if ln and ln.strip()]
            if len(valid) < 2 or len(valid) > 8:
                return False
            text = "\n".join(valid)
            if self._is_time_separator(text):
                return False
            import re
            if re.search(r"https?://", text.lower()):
                return False
            # 末段判断：第一段最后一行是否为“未完句”
            first_line = valid[0]
            if re.search(r"[。！？!?…]$", first_line):
                return False
            pure = re.sub(r"\s", "", text)
            zh_chars = re.findall(r"[\u4e00-\u9fa5]", pure)
            zh_ratio = (len(zh_chars) / max(len(pure), 1)) if pure else 0.0
            return zh_ratio >= 0.4
        except Exception:
            return False

    def _looks_like_sticker_text(self, lines: List[str]) -> bool:
        """Heuristically decide whether given lines look like a sticker overlay text.

        函数级注释：
        - 目标：避免将贴图/表情包上的短句文字误判为普通 TEXT；
        - 触发特征（保守启发式）：
          1) 行数不超过 2（贴图上的文字通常为 1-2 行短句）；
          2) 合并后长度在 3-16 中文字符之间，且中文字符占比高；
          3) 至少包含一个口语化语气词或常见短句关键词（如“吧/啦/呢/别怕/加油/不哭/晚安/早安/抱抱/亲亲/安心/休息/走吧/再见/拜拜/辛苦了/对不起”等）。
        - 这是一个防御型规则：若普通文本恰好也命中上述特征，可能被识别为 STICKER；
          因此仅在行数很少且以口语语气词结尾的短句时触发，尽量减少误判。
        """
        import re
        if not lines:
            return False
        # 合并并标准化空白
        text = " ".join([ln.strip() for ln in lines if ln and ln.strip()])
        if not text:
            return True  # 无文字但存在气泡，视为贴图（后续导出给出“未识别出文字”备注）

        # 行数限制
        if len([ln for ln in lines if ln.strip()]) > 2:
            return False

        # 中文字符比例与长度窗口
        pure = re.sub(r"\s", "", text)
        # 先检测 emoji-only / 短句+emoji 的贴图
        emoji_pat = re.compile(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]")
        has_emoji = bool(emoji_pat.search(pure))
        if has_emoji:
            # 若纯 emoji 或中文<=4 且总长度不超过阈值，倾向判定为贴图
            zh_chars_emoji = re.findall(r"[\u4e00-\u9fa5]", pure)
            if (len(zh_chars_emoji) <= 4) and (len(pure) <= (self.options.emoji_sticker_max_length if hasattr(self, 'options') else 8)):
                return True
        # 仅计数常见中文字符
        zh_chars = re.findall(r"[\u4e00-\u9fa5]", pure)
        zh_ratio = (len(zh_chars) / max(len(pure), 1)) if pure else 0.0
        if not (3 <= len(zh_chars) <= 16 and zh_ratio >= 0.6):
            return False

        # 语气词与常见贴图短句关键词
        particles = {"吧", "啦", "呢", "呗", "嘛", "呀", "哟", "哦", "哇"}
        keywords = {
            "安心", "休息", "走吧", "不哭", "晚安", "早安", "加油", "抱抱", "亲亲",
            "辛苦了", "别怕", "别急", "对不起", "再见", "拜拜", "可以", "你可以", "你安心",
            # 追加更常见的聊天贴图短句/语气
            "晚安呀", "哈哈", "哈哈哈", "哈哈哈哈", "谢谢", "不怕", "害怕", "抱抱你",
            "不会的", "对的", "是的", "是的呀", "好可爱", "太可爱了", "笑死", "笑死我了",
        }
        # 合并外部扩展关键词
        try:
            extra = set(self.options.extra_sticker_keywords or [])
            if extra:
                keywords |= extra
        except Exception:
            pass
        # 至少出现一个语气词或关键词（在词尾出现更可信）
        has_particle = any(p in pure for p in particles)
        has_keyword = any(k in pure for k in keywords)
        if not (has_particle or has_keyword):
            return False

        # 句末语气词或轻微表态（提高可信度）
        if re.search(r"[吧啦呢嘛哟哦呀哇]$", pure):
            return True
        # 或者整体为鼓励/安慰类短句
        return has_keyword

    def _extract_share_card(self, content: str) -> Optional[ShareCard]:
        """Attempt to extract a structured ShareCard from message content.

        函数级注释：
        - 基于关键词与弱格式规则识别“小红书/哔哩哔哩”分享内容，并提取标题/正文/来源等字段；
        - 新增“微信小程序”分享识别（如星巴克咖啡礼物），通过常见短语与行级结构提取 app/source/title/body；
        - 为避免过拟合，采用保守的行级启发式，确保解析失败时回退为普通文本；
        - 返回 ShareCard 或 None（未命中分享）。
        """
        text = content.strip()
        if not text:
            return None
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        low = text.lower()

        # 提取第一个 URL（作为 canonical_url）
        import re
        url_match = re.search(r"https?://\S+", text)
        canonical_url = url_match.group(0) if url_match else None

        # 小红书分享识别
        if ("小红书" in text) or ("red" in low and "book" in low):
            # 标题：排除明显来源/链接/平台标识后的第一行
            title = None
            body_parts: List[str] = []
            for ln in lines:
                if ("小红书" in ln) or (ln.startswith("链接")) or (ln.startswith("点击打开")) or (ln.startswith("来源")):
                    continue
                if title is None:
                    title = ln
                else:
                    body_parts.append(ln)
            if title is None:
                title = lines[0] if lines else ""
            body = "\n".join(body_parts) if body_parts else None
            return ShareCard(platform="小红书", title=title, body=body, source="小红书", canonical_url=canonical_url)

        # 哔哩哔哩分享识别
        if ("哔哩哔哩" in text) or ("bilibili" in low):
            title = None
            up_name = None
            play_count = None
            body_parts: List[str] = []

            import re
            up_pat = re.compile(r"(?:UP主|作者)[：:]{0,1}\s*(.+)")
            play_pat = re.compile(r"(?:播放|播放次数|播放量)[：:]{0,1}\s*([0-9,\.万亿]+)")

            for ln in lines:
                m_up = up_pat.search(ln)
                if m_up and not up_name:
                    up_name = m_up.group(1).strip()
                    continue
                m_play = play_pat.search(ln)
                if m_play and not play_count:
                    play_count = self._parse_play_count(m_play.group(1))
                    continue
                if ("哔哩哔哩" in ln) or ("bilibili" in ln.lower()) or ln.startswith("链接") or (ln.startswith("来源")):
                    continue
                if title is None:
                    title = ln
                else:
                    body_parts.append(ln)
            if title is None:
                title = lines[0] if lines else ""
            body = "\n".join(body_parts) if body_parts else None
            return ShareCard(platform="哔哩哔哩", title=title, body=body, source="哔哩哔哩", up_name=up_name, play_count=play_count, canonical_url=canonical_url)

        # 微信小程序（通用）/ 星巴克咖啡礼物识别
        # 触发条件（其一）：
        # - 文本包含“星巴克”且出现“礼物/咖啡礼物/查收/快拆开”等礼物分享常见短语；
        # - 或包含“微信小程序/小程序”与平台或礼物关键词。
        mini_prog_hints = {"小程序", "微信小程序"}
        gift_hints = {"礼物", "咖啡礼物", "查收", "快拆开"}
        has_mini_prog = any(h in text for h in mini_prog_hints)
        has_starbucks = ("星巴克" in text)
        has_gift = any(h in text for h in gift_hints)
        if (has_starbucks and has_gift) or (has_mini_prog and (has_starbucks or has_gift)):
            # 识别 app 名（来源）：优先使用包含“星巴克”的行；否则使用包含“小程序”的行的最后一个词
            source = None
            app_line = next((ln for ln in lines if "星巴克" in ln), None)
            if app_line:
                source = "星巴克"
            elif has_mini_prog:
                # 尝试从“XX 小程序”提取平台名
                import re
                for ln in lines:
                    if "小程序" in ln:
                        m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]+)\s*小程序", ln)
                        if m:
                            source = m.group(1)
                            break
            if not source:
                source = "微信小程序"

            # 识别标题：优先选取包含礼物/查收/快拆开/生日祝语的行
            title = None
            for ln in lines:
                if any(h in ln for h in gift_hints) or ("生日快乐" in ln):
                    title = ln
                    break
            if title is None:
                # 退化为首行非平台/链接/来源行
                for ln in lines:
                    if ("小程序" in ln) or ("链接" in ln) or ("来源" in ln):
                        continue
                    title = ln
                    break
            if title is None:
                title = lines[0] if lines else ""

            # 正文：除去平台/链接/来源/标题后剩余的行
            body_parts: List[str] = []
            for ln in lines:
                if ln == title:
                    continue
                if ("小程序" in ln) or ("链接" in ln) or ("来源" in ln):
                    continue
                body_parts.append(ln)
            body = "\n".join(body_parts) if body_parts else None

            return ShareCard(platform="微信小程序", title=title, body=body, source=source, canonical_url=canonical_url)

        return None

    def _parse_play_count(self, s: str) -> Optional[int]:
        """Parse a human-readable play count into integer.

        函数级注释：
        - 支持“12,345”“12.3万”“1.2亿”等常见格式；
        - 失败时返回 None，避免抛出异常影响整体解析。
        """
        try:
            st = s.strip().replace(",", "")
            if "万" in st:
                num = float(st.replace("万", ""))
                return int(num * 10000)
            if "亿" in st:
                num = float(st.replace("亿", ""))
                return int(num * 100000000)
            return int(float(st))
        except Exception:
            return None

    def _extract_quote_and_sanitize(self, lines: List[str]) -> tuple[Optional[QuoteMeta], List[str]]:
        """Detect quote bubble and sanitize lines.

        函数级注释：
        - 识别首行昵称 + 次行正文的“引用气泡”，剔除昵称与时间戳行；
        - 生成 QuoteMeta（original_nickname / original_sender_label / quoted_text）；
        - 返回 (quote_meta, sanitized_lines)。若未命中，quote_meta 为 None，返回原始 lines。
        """
        if not lines or len(lines) < 2:
            return None, lines

        nick = lines[0]
        # 简单昵称判定：长度适中、非长句、可能包含特殊字符或表情
        if not self._looks_like_nickname(nick):
            return None, lines

        # 保守触发条件：必须在后续行中出现至少一行时间戳，避免误将普通两行文本识别为“引用气泡”
        has_timestamp = any(self._is_timestamp_line(ln) for ln in lines[1:])
        if not has_timestamp:
            return None, lines

        escaped_nick = self._escape_nickname(nick)
        # 纯文本：移除首行昵称与所有时间戳行
        remaining = [ln for ln in lines[1:] if not self._is_timestamp_line(ln)]
        quoted_text = remaining[0] if remaining else ""
        # 身份标签：根据昵称是否近似“我/自己/Me”等
        label = "我" if self._is_self_nickname(nick) else "对方"
        meta = QuoteMeta(original_nickname=escaped_nick, original_sender_label=label, quoted_text=quoted_text)
        return meta, remaining

    def _looks_like_nickname(self, s: str) -> bool:
        """Heuristic check whether a string looks like a nickname.

        函数级注释：
        - 昵称通常不超过 32 字符，包含中英文、数字、空格、少量标点或表情；
        - 排除明显长句（含多个空格或句末标点）、过长文本与 URL 行。
        """
        import re
        st = s.strip()
        if len(st) > 32:
            return False
        if re.search(r"https?://", st):
            return False
        # 过长句子的简单排除：超过 2 个空格或包含常见句末标点
        if len([c for c in st if c == " "]) >= 3:
            return False
        if re.search(r"[。！？!?]$", st):
            return False
        return True

    def _is_timestamp_line(self, s: str) -> bool:
        """Check if a line looks like a timestamp.

        函数级注释：
        - 支持“YYYY-MM-DD HH:MM”“YYYY年M月D日 HH:MM”“今天/昨天 HH:MM”等；
        - 仅用于引用气泡清洗，避免误伤普通正文。
        """
        import re
        st = s.strip()
        pats = [
            r"^\d{4}[\-/年]\d{1,2}[\-/月]\d{1,2}(\s+[0-2]?\d:\d{2})?$",
            r"^[上|下]?午\s*[0-2]?\d:\d{2}$",
            r"^(昨天|今天|前天)\s*[0-2]?\d:\d{2}$",
            r"^[0-2]?\d:\d{2}$",
        ]
        for p in pats:
            if re.match(p, st):
                return True
        return False

    def _escape_nickname(self, s: str) -> str:
        """Escape nickname to avoid rendering issues in HTML/Tkinter.

        函数级注释：
        - 替换尖括号与和号，移除不可见控制字符；
        - 保留常见 emoji 与中英文字符，避免过度清洗导致信息丢失。
        """
        import re
        st = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # 移除所有控制字符
        st = re.sub(r"[\u0000-\u001F\u007F]", "", st)
        return st

    def _is_self_nickname(self, s: str) -> bool:
        """Decide whether the nickname implies 'self'.

        函数级注释：
        - 通过关键词近似判断（我/我方/自己/me），用于为引用气泡打上“我/对方”标签；
        - 在不知道真实备注名的情况下，这是一个保守近似。
        """
        st = s.strip().lower()
        candidates = {"我", "我方", "自己", "me", "me."}
        return (st in candidates) or st.startswith("我")
    def _is_compact_card(self, infos_slice: List[dict]) -> bool:
        try:
            regions = []
            for inf in infos_slice:
                for ln in inf.get("bubble", []):
                    regions.append(ln.bounding_box)
            if not regions or len(regions) < self.options.compact_card_min_lines:
                return False
            lines = sorted(regions, key=lambda r: (r.y, r.x))
            hs = [max(1, r.height) for r in lines]
            avg_h = sum(hs) / max(1, len(hs))
            gaps = []
            lefts = []
            for k in range(1, len(lines)):
                gaps.append(abs(lines[k].y - lines[k-1].y))
            for r in lines:
                lefts.append(r.x)
            if not gaps:
                return False
            import statistics
            med_gap = statistics.median(gaps)
            gap_norm = med_gap / max(1.0, avg_h)
            import numpy as np
            hstd = float(np.std(lefts))
            n = len(lines)
            if n < self.options.compact_card_min_lines or n > self.options.compact_card_max_lines:
                return False
            if gap_norm <= self.options.compact_card_max_gap_norm and hstd <= float(self.options.compact_card_max_hstd_px):
                return True
            return False
        except Exception:
            return False
