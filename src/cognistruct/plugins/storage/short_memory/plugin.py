import aiosqlite
import json
from typing import Dict, Any, List, Optional
from pathlib import Path

from cognistruct.core.base_plugin import BasePlugin, PluginMetadata, IOMessage
from cognistruct.utils import Config, init_logging, setup_logger, get_timezone

logger = setup_logger(__name__)

class ShortMemoryPlugin(BasePlugin):
    """Плагин для хранения краткосрочной памяти (последних сообщений чата)"""

    def __init__(self, max_messages: int = 10):
        """
        Args:
            max_messages: Максимальное количество сообщений, подставляемых в контекст
        """
        super().__init__()
        self.max_messages = max_messages
        self._db = None
        
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="short_term_memory",
            version="1.0.0",
            description="Хранит все сообщения, а последние подставляет в контекст",
            priority=90  # Высокий приоритет для контекста
        )
    
    async def setup(self):
        """Инициализация плагина"""
        await super().setup()
        
        # Создаем директорию если нужно
        db_dir = Path("data/short_term_memory.db").parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # Подключаемся к базе данных
        self._db = await aiosqlite.connect("data/short_term_memory.db")
        self._db.row_factory = aiosqlite.Row
        
        # Создаем таблицу, если она не существует
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.commit()
    
    async def cleanup(self):
        """Закрываем соединение с базой данных"""
        if not self._db:
            return
            
        await self._db.close()
        await super().cleanup()

    async def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Добавляет сообщение в базу данных (без удаления старых записей)"""
        user_id = metadata.get("user_id") if metadata else None
        if not user_id:
            # Если нет user_id в метаданных, можно пропустить сообщение или залогировать
            logger.warning("No user_id in metadata, skipping message")
            return
            
        # Очищаем метаданные от несериализуемых объектов
        clean_metadata = {}
        if metadata:
            for key, value in metadata.items():
                if key in ["user_id", "chat_id", "telegram"]:
                    clean_metadata[key] = value
        
        await self._db.execute(
            "INSERT INTO memory (user_id, role, content, metadata) VALUES (?, ?, ?, ?)",
            (
                user_id,
                role,
                content,
                json.dumps(clean_metadata)
            )
        )
        await self._db.commit()

    async def get_recent(self, user_id: str = None) -> List[Dict[str, Any]]:
        """Получает последние сообщения для пользователя для формирования контекста"""
        if not user_id:
            return []
            
        # Включаем возврат строк как словарей
        self._db.row_factory = aiosqlite.Row
        
        async with self._db.execute(
            """
            SELECT user_id, role, content, metadata, timestamp 
            FROM memory 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
            """,
            (user_id, self.max_messages)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{
                "value": {
                    "role": row["role"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"]),
                    "timestamp": row["timestamp"]
                }
            } for row in rows]

    async def input_hook(self, message: IOMessage) -> bool:
        """Сохраняет входящее сообщение"""
        await self.add_message(
            role="user",
            content=message.content,
            metadata=message.metadata
        )
        return False  # Продолжаем обработку

    async def output_hook(self, message: IOMessage) -> Optional[IOMessage]:
        """Сохраняет ответ ассистента"""
        if not message.type == "stream":  # Для стрима сохраняем после завершения
            await self.add_message(
                role="assistant",
                content=message.content.content if hasattr(message.content, 'content') else message.content,
                metadata=message.metadata
            )
        return message

    async def rag_hook(self, message: IOMessage) -> Optional[Dict[str, Any]]:
        """Возвращает историю сообщений"""
        messages = await self.get_messages()
        if not messages:
            return None
        return {
            "recent_messages": "\n".join(
                f"{msg['role']}: {msg['content']}" 
                for msg in messages[-self.max_messages:]
            )
        }
