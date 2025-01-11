import aiosqlite
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

from cognistruct.core.base_plugin import BasePlugin, PluginMetadata, IOMessage


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
        self._db: Optional[aiosqlite.Connection] = None

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
        
        # Создаем директорию если нужно
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # Подключаемся к базе данных
        self._db = await aiosqlite.connect(self.db_path)
        
        # Создаем таблицу
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.commit()
    
    async def cleanup(self):
        """Очистка устаревших записей"""
        if not self._db:
            return
            
        # Оставляем только последние max_messages сообщений для каждого пользователя
        await self._db.execute("""
            DELETE FROM memory 
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY user_id 
                        ORDER BY timestamp DESC
                    ) as rn 
                    FROM memory
                ) ranked 
                WHERE rn <= ?
            )
        """, (self.max_messages,))
        await self._db.commit()
        
        # Закрываем соединение
        await self._db.close()
        await super().cleanup()

    async def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Добавляет сообщение в память"""
        # Добавляем новое сообщение
        await self._db.execute(
            "INSERT INTO memory (user_id, role, content, metadata) VALUES (?, ?, ?, ?)",
            (
                self.user_id,
                role,
                content,
                json.dumps(metadata or {})
            )
        )
        
        # Удаляем старые сообщения если превышен лимит для данного пользователя
        await self._db.execute("""
            DELETE FROM memory 
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY user_id 
                        ORDER BY timestamp DESC
                    ) as rn 
                    FROM memory
                    WHERE user_id = ?
                ) ranked 
                WHERE rn <= ?
            )
            AND user_id = ?
        """, (self.user_id, self.max_messages, self.user_id))
        
        await self._db.commit()

    async def get_recent(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Получает последние сообщения"""
        async with self._db.execute(
            """
            SELECT role, content, metadata, timestamp 
            FROM memory 
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (self.user_id, limit or self.max_messages)
        ) as cursor:
            rows = await cursor.fetchall()
            
        return [
            {
                "value": {
                    "role": row[0],
                    "content": row[1],
                    "metadata": json.loads(row[2])
                },
                "timestamp": row[3]
            }
            for row in rows
        ]

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