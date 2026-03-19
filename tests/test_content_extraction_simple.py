#!/usr/bin/env python3
"""
简化版内容识别和提取功能测试
避免直接使用OCR，专注于消息解析和内容处理逻辑
"""

import os
import sys
import time
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.data_models import TextRegion, Rectangle, Message, MessageType
from services.message_parser import MessageParser

def setup_logging():
    """设置日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def test_message_parser_basic():
    """测试消息解析器基础功能"""
    print("🧪 测试消息解析器基础功能...")
    
    parser = MessageParser()
    
    # 创建模拟文本区域 - 典型的微信聊天格式
    test_regions = [
        # 发送者 + 时间
        TextRegion(
            text="张三 14:30",
            confidence=0.95,
            bounding_box=Rectangle(x=50, y=100, width=120, height=25)
        ),
        # 消息内容
        TextRegion(
            text="你好，今天天气不错，适合出门散步",
            confidence=0.92,
            bounding_box=Rectangle(x=50, y=130, width=280, height=35)
        ),
        # 另一个发送者 + 时间
        TextRegion(
            text="李四 14:31",
            confidence=0.94,
            bounding_box=Rectangle(x=400, y=180, width=120, height=25)
        ),
        # 回复消息
        TextRegion(
            text="是的，我正准备出去",
            confidence=0.91,
            bounding_box=Rectangle(x=400, y=210, width=200, height=30)
        ),
        # 系统消息
        TextRegion(
            text="系统消息：张三修改了群名为'测试群组'",
            confidence=0.98,
            bounding_box=Rectangle(x=200, y=280, width=300, height=25)
        )
    ]
    
    try:
        messages = parser.parse(test_regions)
        print(f"✅ 解析出 {len(messages)} 条消息")
        
        # 验证解析结果 - 每个文本区域都被解析为单独的消息
        expected_count = 5  # 5个文本区域应该解析出5条消息
        if len(messages) != expected_count:
            print(f"❌ 预期 {expected_count} 条消息，实际 {len(messages)} 条")
            return False
        
        # 检查每条消息的结构
        for i, msg in enumerate(messages):
            print(f"   消息 {i+1}:")
            print(f"     发送者: {msg.sender}")
            print(f"     内容: {repr(msg.content)}")
            print(f"     类型: {msg.message_type}")
            print(f"     置信度: {msg.confidence_score:.3f}")
            
            # 基本验证
            if not msg.sender or not msg.content:
                print(f"❌ 消息 {i+1} 缺少必要字段")
                return False
        
        print("✅ 所有消息结构验证通过")
        return True
        
    except Exception as e:
        print(f"❌ 消息解析失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_message_parser_edge_cases():
    """测试边界情况"""
    print("\n🧪 测试边界情况...")
    
    parser = MessageParser()
    
    # 测试空输入
    try:
        messages = parser.parse([])
        if len(messages) == 0:
            print("✅ 空输入处理正确")
        else:
            print("❌ 空输入处理错误")
            return False
    except Exception as e:
        print(f"❌ 空输入处理异常: {e}")
        return False
    
    # 测试单条消息
    single_region = [
        TextRegion(
            text="单条测试消息",
            confidence=0.90,
            bounding_box=Rectangle(x=100, y=100, width=150, height=30)
        )
    ]
    
    try:
        messages = parser.parse(single_region)
        if len(messages) == 1:
            print("✅ 单条消息处理正确")
        else:
            print("❌ 单条消息处理错误")
            return False
    except Exception as e:
        print(f"❌ 单条消息处理异常: {e}")
        return False
    
    return True

def test_content_summarization():
    """测试内容摘要功能（模拟）"""
    print("\n🧪 测试内容摘要功能...")
    
    # 模拟从AdvancedScrollController中提取的摘要功能
    def summarize_content(messages):
        """模拟内容摘要函数"""
        if not messages:
            return "无内容"
        
        # 提取关键信息
        senders = set()
        content_words = []
        
        for msg in messages:
            senders.add(msg.sender)
            # 简单提取关键词（实际实现会更复杂）
            words = msg.content.split()
            content_words.extend(words[:3])  # 取前3个词
        
        sender_list = ", ".join(sorted(senders))
        keyword_summary = " ".join(sorted(set(content_words))[:5])  # 取前5个唯一关键词
        
        return f"发送者: {sender_list} | 关键词: {keyword_summary}"
    
    # 创建测试消息（使用正确的构造函数参数）
    from datetime import datetime
    import uuid
    
    test_messages = [
        Message(
            id=str(uuid.uuid4()),
            sender="张三",
            content="今天天气很好",
            message_type=MessageType.TEXT,
            timestamp=datetime.now(),
            confidence_score=0.9,
            raw_ocr_text="今天天气很好"
        ),
        Message(
            id=str(uuid.uuid4()),
            sender="李四", 
            content="是的适合出门",
            message_type=MessageType.TEXT,
            timestamp=datetime.now(),
            confidence_score=0.88,
            raw_ocr_text="是的适合出门"
        ),
        Message(
            id=str(uuid.uuid4()),
            sender="王五",
            content="我同意这个观点",
            message_type=MessageType.TEXT, 
            timestamp=datetime.now(),
            confidence_score=0.85,
            raw_ocr_text="我同意这个观点"
        )
    ]
    
    summary = summarize_content(test_messages)
    print(f"✅ 内容摘要: {summary}")
    
    # 验证摘要包含关键信息
    if "张三" in summary and "李四" in summary and "王五" in summary:
        print("✅ 摘要包含所有发送者")
    else:
        print("❌ 摘要缺少发送者信息")
        return False
    
    if "天气" in summary or "出门" in summary or "同意" in summary:
        print("✅ 摘要包含关键词")
    else:
        print("❌ 摘要缺少关键词")
        return False
    
    return True

def test_scroll_state_capture():
    """测试滚动状态捕获功能（模拟）"""
    print("\n🧪 测试滚动状态捕获功能...")
    
    # 模拟AdvancedScrollController中的状态捕获
    def capture_scroll_state(scroll_count, messages):
        """模拟滚动状态捕获"""
        return {
            "scroll_count": scroll_count,
            "timestamp": time.time(),
            "message_count": len(messages),
            "messages": messages,
            "content_summary": "测试摘要" if messages else "无内容"
        }
    
    # 测试不同状态
    states = []
    
    # 状态1: 无消息
    state1 = capture_scroll_state(1, [])
    states.append(state1)
    print(f"✅ 状态1 - 滚动次数: {state1['scroll_count']}, 消息数: {state1['message_count']}")
    
    # 状态2: 有消息
    from datetime import datetime
    import uuid
    
    test_messages = [
        Message(
            id=str(uuid.uuid4()),
            sender="User1", 
            content="消息1", 
            message_type=MessageType.TEXT, 
            timestamp=datetime.now(),
            confidence_score=0.9,
            raw_ocr_text="消息1"
        ),
        Message(
            id=str(uuid.uuid4()),
            sender="User2", 
            content="消息2", 
            message_type=MessageType.TEXT, 
            timestamp=datetime.now(),
            confidence_score=0.85,
            raw_ocr_text="消息2"
        )
    ]
    state2 = capture_scroll_state(2, test_messages)
    states.append(state2)
    print(f"✅ 状态2 - 滚动次数: {state2['scroll_count']}, 消息数: {state2['message_count']}")
    
    # 验证状态捕获
    if len(states) == 2 and states[0]['message_count'] == 0 and states[1]['message_count'] == 2:
        print("✅ 状态捕获功能正常")
        return True
    else:
        print("❌ 状态捕获功能异常")
        return False

def main():
    """主测试函数"""
    print("=" * 60)
    print("🧪 简化版内容识别和提取功能测试")
    print("=" * 60)
    
    setup_logging()
    
    # 运行测试
    tests = [
        ("基础消息解析", test_message_parser_basic),
        ("边界情况处理", test_message_parser_edge_cases), 
        ("内容摘要功能", test_content_summarization),
        ("滚动状态捕获", test_scroll_state_capture)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 开始测试: {test_name}")
        success = test_func()
        results.append((test_name, success))
        print(f"  结果: {'✅ 通过' if success else '❌ 失败'}")
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总:")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    print(f"\n🎯 总体通过率: {passed}/{total} ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 所有内容识别和提取功能测试通过！")
        return True
    else:
        print("⚠️  部分测试未通过，需要进一步调试")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)