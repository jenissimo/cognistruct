import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import asyncio
from pathlib import Path

from plugins.base_plugin import BasePlugin, PluginMetadata, IOMessage


class ShortTermMemoryPlugin(BasePlugin):
    """Плагин для хранения краткосрочной памяти (последних сообщений)"""

    def __init__(self, max_messages: int = 10, db_path: str = "data/short_term_memory.db"):
        """
        Args:
            max_messages: Максимальное количество хранимых сообщений
            db_path: Путь к файлу базы данных
        """
        super().__init__()
        self.db_path = db_path
        self.max_messages = max_messages

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="short_term_memory",
            version="1.0.0",
            description="Хранит последние сообщения чата",
            priority=90  # Высокий приоритет для контекста
        )
    
    async def setup(self):
        """Инициализация плагина"""
        await super().setup()
        await self._setup_db()
    
    async def _setup_db(self):
        """Инициализация базы данных"""
        def _setup():
            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        
        await asyncio.to_thread(_setup)
    
    async def cleanup(self):
        """Очистка устаревших записей"""
        def _cleanup():
            with sqlite3.connect(self.db_path) as conn:
                # Оставляем только последние max_messages сообщений
                conn.execute("""
                    DELETE FROM memory 
                    WHERE id NOT IN (
                        SELECT id FROM memory 
                        ORDER BY timestamp DESC 
                        LIMIT ?
                    )
                """, (self.max_messages,))
                conn.commit()
        
        await asyncio.to_thread(_cleanup)
        await super().cleanup()

    async def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Добавляет сообщение в память"""
        def _add():
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO memory (role, content, metadata) VALUES (?, ?, ?)",
                    (
                        role,
                        content,
                        json.dumps(metadata or {})
                    )
                )
                # Удаляем старые сообщения если превышен лимит
                conn.execute("""
                    DELETE FROM memory 
                    WHERE id NOT IN (
                        SELECT id FROM memory 
                        ORDER BY timestamp DESC 
                        LIMIT ?
                    )
                """, (self.max_messages,))
                conn.commit()
        
        await asyncio.to_thread(_add)

    async def get_recent(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Получает последние сообщения"""
        def _get_recent():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT role, content, metadata, timestamp 
                    FROM memory 
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit or self.max_messages,)
                )
                return [
                    {
                        "value": {
                            "role": row[0],
                            "content": row[1],
                            "metadata": json.loads(row[2])
                        },
                        "timestamp": row[3]
                    }
                    for row in cursor.fetchall()
                ]
        
        return await asyncio.to_thread(_get_recent)

    async def input_hook(self, message: IOMessage) -> bool:
        """Сохраняем входящие сообщения"""
        await self.add_message(
            role="user",
            content=message.content,
            metadata=message.metadata
        )
        return False  # Продолжаем обработку

    async def output_hook(self, message: IOMessage):
        """Сохраняем исходящие сообщения"""
        await self.add_message(
            role="assistant",
            content=message.content,
            metadata=message.metadata
        )

    async def rag_hook(self, query: str) -> Dict[str, Any]:
        """Добавляем последние сообщения в контекст"""
        recent_messages = await self.get_recent()
        
        if not recent_messages:
            return {}
            
        # Форматируем сообщения для контекста
        context = []
        for msg in recent_messages:
            data = msg["value"]
            context.append(f"{data['role'].title()}: {data['content']}")
            
        return {
            "recent_messages": "\n".join(reversed(context))  # Реверсируем чтобы старые были сверху
        } 