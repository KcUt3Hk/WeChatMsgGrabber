import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

def parse_filename_date(filename: str) -> datetime:
    """Extract date from filename like auto_wechat_scan_20251206_105339.json"""
    match = re.search(r'(\d{8})_(\d{6})', filename)
    if match:
        return datetime.strptime(f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M%S")
    return datetime.now()

def parse_wechat_time(text: str, reference_date: datetime) -> datetime:
    """
    Parse WeChat time strings like:
    - 10:00 (Today)
    - 昨天 10:00 (Yesterday)
    - 星期一 10:00 (Last Monday)
    - 2024年11月10日 10:00
    - 11月10日 10:00 (Current year)
    """
    text = text.strip()
    
    # Full date: 2025年12月06日 10:00
    match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{1,2})', text)
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
            pass # Invalid date, fallback

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
        # Calculate days to subtract. 
        # If today is Sat (5) and we want Mon (0), diff is 5.
        # If today is Mon (0) and we want Sun (6), diff is 1 (last Sunday).
        days_diff = (current_wd - target_wd) % 7
        if days_diff == 0:
             days_diff = 7 # Assume last week if same day? Or today? usually WeChat says "10:00" for today.
        
        d = reference_date - timedelta(days=days_diff)
        return d.replace(hour=int(match.group(2)), minute=int(match.group(3)), second=0, microsecond=0)

    # Today: 10:00
    match = re.match(r'^(\d{1,2})[:：](\d{1,2})$', text)
    if match:
        try:
            return reference_date.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0)
        except ValueError:
            pass

    # Fallback: return reference date
    return reference_date

def process_file(filepath: Path) -> List[Dict]:
    print(f"Processing {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    scan_date = parse_filename_date(filepath.name)
    print(f"  Scan Date: {scan_date}")
    
    processed_msgs = []
    
    current_time = scan_date
    
    for msg in data:
        # Check if it's a system message OR looks like a timestamp
        content = msg.get('content', '').strip()
        msg_type = msg.get('message_type')
        
        # Check if content looks like a timestamp
        is_timestamp = False
        parsed_time = parse_wechat_time(content, scan_date)
        
        # If parsed_time changed (not equal to scan_date ref passed in) OR content matches specific patterns
        # But parse_wechat_time returns ref_date if no match.
        # So check if it matches patterns.
        
        # Strict patterns for detection
        patterns = [
            r'^\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}[:：]\d{1,2}$',
            r'^\d{1,2}月\d{1,2}日\s*\d{1,2}[:：]\d{1,2}$',
            r'^昨天\s*\d{1,2}[:：]\d{1,2}$',
            r'^星期[一二三四五六日天]\s*\d{1,2}[:：]\d{1,2}$',
            r'^\d{1,2}[:：]\d{1,2}$'
        ]
        
        if any(re.match(p, content) for p in patterns):
            is_timestamp = True
            current_time = parsed_time
            # If it was misclassified as text, change to system (optional, but good for cleanliness)
            # Or just mark it.
            msg['message_type'] = 'system' # Force update type
            msg['real_time'] = current_time.strftime("%Y-%m-%d %H:%M:%S")
            processed_msgs.append(msg)
        elif msg_type == 'system':
             # It is system but maybe regex didn't catch it? 
             # Or it's a system message like "You recalled a message"
             # If it's "You recalled...", it shouldn't change time.
             # Only update time if it looks like time.
             # But wait, existing logic assumed all system msgs are time?
             # If content is "You recalled a message", parse_wechat_time returns scan_date.
             # This would RESET time to scan_date! That's BAD.
             
             # Fix: Only update current_time if it actually looks like a time.
             if is_timestamp: # Already handled above
                 pass
             else:
                 # It's a system message but NOT a timestamp (e.g. "Recalled message")
                 # Keep current_time
                 msg['real_time'] = current_time.strftime("%Y-%m-%d %H:%M:%S")
                 processed_msgs.append(msg)
        else:
            msg['real_time'] = current_time.strftime("%Y-%m-%d %H:%M:%S")
            processed_msgs.append(msg)
            
    return processed_msgs

def merge_files(files: List[str], output_file: str):
    all_msgs = []
    for f in files:
        all_msgs.extend(process_file(Path(f)))
    
    print(f"Total messages before dedup: {len(all_msgs)}")
    
    # Sort by real_time
    all_msgs.sort(key=lambda x: x.get('real_time', ''))
    
    # Deduplicate
    # Key: (sender, content, real_time)
    # But real_time might vary slightly if one file inferred it differently.
    # Let's try to match exact content + sender + date (YYYY-MM-DD). Time might vary.
    
    unique_msgs = []
    seen_keys = set()
    
    duplicates = 0
    for msg in all_msgs:
        # Create a key
        rt = msg.get('real_time', '')
        # Use minute precision for dedup? Or just full string?
        # If the parsing is consistent, full string should match.
        key = (msg.get('sender'), msg.get('content'), rt)
        
        if key not in seen_keys:
            seen_keys.add(key)
            unique_msgs.append(msg)
        else:
            duplicates += 1
            
    print(f"Removed {duplicates} duplicates.")
    print(f"Final count: {len(unique_msgs)}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(unique_msgs, f, ensure_ascii=False, indent=2)
    
    print(f"Saved to {output_file}")

if __name__ == "__main__":
    # 示例用法：请修改以下路径为实际文件路径
    # Example usage: Please modify the paths below to your actual file paths
    files = [
        # "output/scan_result_1.json",
        # "output/scan_result_2.json"
    ]
    output = "merged_output.json"
    
    if not files:
        print("Please configure input files in the script or use CLI arguments.")
        sys.exit(1)
        
    merge_files(files, output)
