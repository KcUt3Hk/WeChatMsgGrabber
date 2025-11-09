"""
综合测试消息去重和存储功能

测试内容包括：
1. 批内去重功能
2. 跨批次去重功能  
3. 不同输出格式支持
4. 去重索引文件管理
5. 消息键生成策略
"""
import json
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# 动态将项目根目录加入 Python 路径（tests 目录位于项目根目录下）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models.data_models import Message, MessageType
from models.config import OutputConfig
from services.storage_manager import StorageManager


def create_test_messages():
    """创建测试消息数据，包含重复消息"""
    base_time = datetime(2024, 1, 1, 12, 0, 0)
    
    return [
        # 有ID的重复消息
        Message(
            id="msg_001",
            sender="张三",
            content="你好，今天天气不错",
            message_type=MessageType.TEXT,
            timestamp=base_time,
            confidence_score=0.95,
            raw_ocr_text="你好，今天天气不错",
        ),
        Message(
            id="msg_001",  # 重复ID
            sender="张三", 
            content="你好，今天天气不错",
            message_type=MessageType.TEXT,
            timestamp=base_time,
            confidence_score=0.95,
            raw_ocr_text="你好，今天天气不错",
        ),
        # 无ID的重复消息（使用后备键）
        Message(
            id="",
            sender="李四",
            content="收到，谢谢！",
            message_type=MessageType.TEXT,
            timestamp=base_time + timedelta(minutes=1),
            confidence_score=0.92,
            raw_ocr_text="收到，谢谢！",
        ),
        Message(
            id="",
            sender="李四",
            content="收到，谢谢！", 
            message_type=MessageType.TEXT,
            timestamp=base_time + timedelta(minutes=1),
            confidence_score=0.92,
            raw_ocr_text="收到，谢谢！",
        ),
        # 唯一消息
        Message(
            id="msg_003",
            sender="王五",
            content="会议改到下午3点",
            message_type=MessageType.TEXT,
            timestamp=base_time + timedelta(minutes=2),
            confidence_score=0.88,
            raw_ocr_text="会议改到下午3点",
        ),
        # 系统消息
        Message(
            id="sys_001",
            sender="系统",
            content="张三修改了群名为'测试群组'",
            message_type=MessageType.SYSTEM,
            timestamp=base_time + timedelta(minutes=3),
            confidence_score=0.99,
            raw_ocr_text="张三修改了群名为'测试群组'",
        ),
    ]


class TestMessageDeduplicationStorage:
    """消息去重和存储功能测试类"""
    
    def test_batch_deduplication_json(self, tmp_path):
        """测试JSON格式的批内去重功能"""
        print("🧪 测试JSON格式批内去重...")
        
        cfg = OutputConfig(format="json", directory=str(tmp_path), enable_deduplication=True)
        storage = StorageManager(cfg)
        
        messages = create_test_messages()
        path = storage.save_messages(messages, filename_prefix="batch_dedup")
        
        # 验证文件存在且格式正确
        assert path.exists()
        assert path.suffix == ".json"
        
        # 验证去重结果
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 4  # 6条消息去重后应为4条
        
        # 验证唯一消息都存在
        message_ids = {msg["id"] for msg in data}
        expected_ids = {"msg_001", "", "msg_003", "sys_001"}
        assert message_ids == expected_ids
        
        print("✅ JSON批内去重测试通过")
    
    def test_batch_deduplication_csv(self, tmp_path):
        """测试CSV格式的批内去重功能"""
        print("🧪 测试CSV格式批内去重...")
        
        cfg = OutputConfig(format="csv", directory=str(tmp_path), enable_deduplication=True)
        storage = StorageManager(cfg)
        
        messages = create_test_messages()
        path = storage.save_messages(messages, filename_prefix="batch_dedup_csv")
        
        # 验证文件存在且格式正确
        assert path.exists()
        assert path.suffix == ".csv"
        
        # 验证去重结果
        content = path.read_text(encoding="utf-8").strip()
        lines = content.splitlines()
        assert len(lines) == 5  # 表头 + 4条数据
        
        # 验证CSV格式
        reader = csv.DictReader(lines)
        rows = list(reader)
        assert len(rows) == 4
        
        print("✅ CSV批内去重测试通过")
    
    def test_cross_batch_deduplication(self, tmp_path):
        """测试跨批次去重功能"""
        print("🧪 测试跨批次去重...")
        
        cfg = OutputConfig(format="json", directory=str(tmp_path), enable_deduplication=True)
        storage = StorageManager(cfg)
        
        # 第一批消息
        batch1 = [
            Message(
                id="cross_001",
                sender="用户A",
                content="第一批消息1",
                message_type=MessageType.TEXT,
                timestamp=datetime(2024, 1, 1, 10, 0, 0),
                confidence_score=0.95,
                raw_ocr_text="第一批消息1",
            ),
            Message(
                id="cross_002", 
                sender="用户B",
                content="第一批消息2",
                message_type=MessageType.TEXT,
                timestamp=datetime(2024, 1, 1, 10, 1, 0),
                confidence_score=0.92,
                raw_ocr_text="第一批消息2",
            ),
        ]
        
        path1 = storage.save_messages(batch1, filename_prefix="cross_batch_1")
        assert path1.exists()
        
        # 第二批消息（包含重复和新的）
        batch2 = [
            Message(
                id="cross_001",  # 重复消息
                sender="用户A",
                content="第一批消息1",
                message_type=MessageType.TEXT,
                timestamp=datetime(2024, 1, 1, 10, 0, 0),
                confidence_score=0.95,
                raw_ocr_text="第一批消息1",
            ),
            Message(
                id="cross_003",  # 新消息
                sender="用户C",
                content="第二批消息1",
                message_type=MessageType.TEXT,
                timestamp=datetime(2024, 1, 1, 10, 2, 0),
                confidence_score=0.90,
                raw_ocr_text="第二批消息1",
            ),
        ]
        
        path2 = storage.save_messages(batch2, filename_prefix="cross_batch_2")
        assert path2.exists()
        
        # 验证第二批只包含新消息
        data2 = json.loads(path2.read_text(encoding="utf-8"))
        assert len(data2) == 1
        assert data2[0]["id"] == "cross_003"
        
        # 验证去重索引文件存在
        index_path = tmp_path / ".dedup_index.json"
        assert index_path.exists()
        
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        assert isinstance(index_data, list)
        assert "cross_001" in index_data
        assert "cross_002" in index_data
        assert "cross_003" in index_data
        
        print("✅ 跨批次去重测试通过")
    
    def test_deduplication_disabled(self, tmp_path):
        """测试禁用去重功能"""
        print("🧪 测试禁用去重功能...")
        
        cfg = OutputConfig(format="json", directory=str(tmp_path), enable_deduplication=False)
        storage = StorageManager(cfg)
        
        messages = create_test_messages()
        path = storage.save_messages(messages, filename_prefix="no_dedup")
        
        # 验证所有消息都被保存（无去重）
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 6  # 无去重，所有6条消息都保存
        
        # 验证去重索引文件不存在
        index_path = tmp_path / ".dedup_index.json"
        assert not index_path.exists()
        
        print("✅ 禁用去重功能测试通过")
    
    def test_deduplication_index_management(self, tmp_path):
        """测试去重索引文件管理"""
        print("🧪 测试去重索引文件管理...")
        
        cfg = OutputConfig(format="json", directory=str(tmp_path), enable_deduplication=True)
        storage = StorageManager(cfg)
        
        # 第一次保存
        messages1 = [
            Message(
                id="index_001",
                sender="测试用户",
                content="索引测试消息1",
                message_type=MessageType.TEXT,
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                confidence_score=0.95,
                raw_ocr_text="索引测试消息1",
            )
        ]
        
        path1 = storage.save_messages(messages1, filename_prefix="index_test_1")
        assert path1.exists()
        
        # 验证索引文件创建
        index_path = tmp_path / ".dedup_index.json"
        assert index_path.exists()
        
        index_data1 = json.loads(index_path.read_text(encoding="utf-8"))
        assert "index_001" in index_data1
        
        # 第二次保存（相同消息）
        path2 = storage.save_messages(messages1, filename_prefix="index_test_2")
        assert path2.exists()
        
        # 验证第二次保存没有新内容（去重生效）
        data2 = json.loads(path2.read_text(encoding="utf-8"))
        assert len(data2) == 0
        
        # 测试清空索引
        storage.clear_dedup_index()
        assert not index_path.exists()
        
        # 再次保存相同消息（索引清空后应该重新保存）
        path3 = storage.save_messages(messages1, filename_prefix="index_test_3")
        assert path3.exists()
        
        data3 = json.loads(path3.read_text(encoding="utf-8"))
        assert len(data3) == 1
        
        print("✅ 去重索引文件管理测试通过")
    
    def test_message_stable_key_generation(self):
        """测试消息稳定键生成策略"""
        print("🧪 测试消息稳定键生成...")
        
        # 测试有ID的消息
        msg_with_id = Message(
            id="test_id_123",
            sender="测试用户",
            content="测试内容",
            message_type=MessageType.TEXT,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            confidence_score=0.95,
            raw_ocr_text="测试内容",
        )
        
        key1 = msg_with_id.stable_key()
        assert key1 == "test_id_123"
        
        # 测试无ID的消息（使用后备键）
        msg_without_id = Message(
            id="",
            sender="测试用户",
            content="测试内容",
            message_type=MessageType.TEXT,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            confidence_score=0.95,
            raw_ocr_text="测试内容",
        )
        
        key2 = msg_without_id.stable_key()
        expected_key = "测试用户|2024-01-01T12:00:00|测试内容"
        assert key2 == expected_key
        
        # 测试相同消息生成相同键
        msg_duplicate = Message(
            id="",
            sender="测试用户",
            content="测试内容",
            message_type=MessageType.TEXT,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            confidence_score=0.95,
            raw_ocr_text="测试内容",
        )
        
        key3 = msg_duplicate.stable_key()
        assert key3 == expected_key
        
        print("✅ 消息稳定键生成测试通过")
    
    def test_multiple_output_formats(self, tmp_path):
        """测试多种输出格式支持"""
        print("🧪 测试多种输出格式...")
        
        test_messages = [
            Message(
                id="format_test",
                sender="格式测试",
                content="测试多种输出格式",
                message_type=MessageType.TEXT,
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                confidence_score=0.95,
                raw_ocr_text="测试多种输出格式",
            )
        ]
        
        # 测试JSON格式
        cfg_json = OutputConfig(format="json", directory=str(tmp_path), enable_deduplication=True)
        storage_json = StorageManager(cfg_json)
        path_json = storage_json.save_messages(test_messages, filename_prefix="format_json")
        assert path_json.exists() and path_json.suffix == ".json"
        
        # 测试CSV格式
        cfg_csv = OutputConfig(format="csv", directory=str(tmp_path / "csv"), enable_deduplication=True)
        storage_csv = StorageManager(cfg_csv)
        path_csv = storage_csv.save_messages(test_messages, filename_prefix="format_csv")
        assert path_csv.exists() and path_csv.suffix == ".csv"
        
        # 测试TXT格式
        cfg_txt = OutputConfig(format="txt", directory=str(tmp_path / "txt"), enable_deduplication=True)
        storage_txt = StorageManager(cfg_txt)
        path_txt = storage_txt.save_messages(test_messages, filename_prefix="format_txt")
        assert path_txt.exists() and path_txt.suffix == ".txt"
        
        # 测试Markdown格式
        cfg_md = OutputConfig(format="md", directory=str(tmp_path / "md"), enable_deduplication=True)
        storage_md = StorageManager(cfg_md)
        path_md = storage_md.save_messages(test_messages, filename_prefix="format_md")
        assert path_md.exists() and path_md.suffix == ".md"
        
        # 验证各格式内容
        json_content = json.loads(path_json.read_text(encoding="utf-8"))
        assert len(json_content) == 1
        
        csv_content = path_csv.read_text(encoding="utf-8")
        assert "format_test" in csv_content
        
        txt_content = path_txt.read_text(encoding="utf-8")
        assert "格式测试" in txt_content
        
        md_content = path_md.read_text(encoding="utf-8")
        assert "# WeChat Chat Export" in md_content
        
        print("✅ 多种输出格式测试通过")


def run_comprehensive_tests():
    """运行综合测试"""
    print("🚀 开始消息去重和存储功能综合测试\n")
    
    # 使用pytest运行测试
    test_result = pytest.main([
        "-v",
        "tests/test_message_deduplication_storage.py",
        "--tb=short"
    ])
    
    if test_result == 0:
        print("\n🎉 所有消息去重和存储功能测试通过！")
        return True
    else:
        print(f"\n❌ 测试失败，返回码: {test_result}")
        return False


if __name__ == "__main__":
    run_comprehensive_tests()