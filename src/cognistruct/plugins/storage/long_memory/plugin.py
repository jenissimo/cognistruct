import aiosqlite
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from cognistruct.core.base_plugin import BasePlugin, PluginMetadata, IOMessage
from cognistruct.llm.interfaces import ToolSchema, ToolParameter


class LongTermMemoryPlugin(BasePlugin):
    """Плагин для хранения долгосрочной памяти с тегами"""
    
    def __init__(self, 
                 max_context_memories: int = 5,
                 recency_weight: float = 0.3,
                 db_path: str = "data/long_term_memory.db"):
        """
        Args:
            max_context_memories: Максимальное количество воспоминаний в контексте
            recency_weight: Вес недавних обращений (0-1)
            db_path: Путь к базе данных
        """
        super().__init__()
        self.db_path = db_path
        self.max_context_memories = max_context_memories
        self.recency_weight = recency_weight
        self.vectorizer = TfidfVectorizer()
        self._db: Optional[aiosqlite.Connection] = None
        
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="long_term_memory",
            version="1.0.0",
            description="Хранит важные факты с возможностью поиска по тегам",
            priority=80
        )
        
    def get_tools(self) -> List[ToolSchema]:
        return [
            ToolSchema(
                name="remember",
                description="Сохраняет важный факт в долгосрочную память",
                parameters=[
                    ToolParameter(
                        name="fact",
                        type="string",
                        description="Факт для запоминания, наприме 'Пользователя зовут Женя'"
                    ),
                    ToolParameter(
                        name="tags",
                        type="array",
                        description="Список тегов для поиска"
                    )
                ]
            ),
            ToolSchema(
                name="recall",
                description="Ищет факты по тегам или тексту",
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="Поисковый запрос"
                    )
                ]
            )
        ]
        
    async def setup(self):
        """Инициализация базы данных"""
        await super().setup()
        
        # Создаем директорию если нужно
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # Подключаемся к базе данных
        self._db = await aiosqlite.connect(self.db_path)
        
        # Создаем таблицу фактов
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content TEXT NOT NULL,
                tags TEXT NOT NULL,
                last_accessed DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.commit()
        
    async def cleanup(self):
        """Закрытие соединения с БД"""
        if self._db:
            await self._db.close()
            await super().cleanup()
        
    async def add_memory(self, content: str, tags: List[str], user_id: Optional[int] = None):
        """
        Добавляет новый факт в память
        
        Args:
            content: Содержание факта
            tags: Список тегов
            user_id: ID пользователя (если не указан, берется из контекста)
        """
        await self._db.execute(
            "INSERT INTO memories (user_id, content, tags, last_accessed) VALUES (?, ?, ?, ?)",
            (
                user_id if user_id is not None else self.user_id,
                content,
                json.dumps(tags),
                datetime.now().isoformat()
            )
        )
        await self._db.commit()
        
    async def update_access_time(self, memory_id: int):
        """Обновляет время последнего доступа"""
        await self._db.execute(
            "UPDATE memories SET last_accessed = ? WHERE id = ?",
            (datetime.now().isoformat(), memory_id)
        )
        await self._db.commit()
        
    async def search_memories(self, query: str, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Ищет релевантные воспоминания
        
        Args:
            query: Поисковый запрос
            user_id: ID пользователя (если не указан, берется из контекста)
        """
        # Получаем воспоминания только для указанного пользователя
        async with self._db.execute(
            "SELECT id, content, tags, last_accessed FROM memories WHERE user_id = ?",
            (user_id if user_id is not None else self.user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            
        memories = [
            {
                "id": row[0],
                "content": row[1],
                "tags": json.loads(row[2]),
                "last_accessed": datetime.fromisoformat(row[3])
            }
            for row in rows
        ]
            
        if not memories:
            return []
            
        # Векторизуем запрос и содержимое
        texts = [query] + [m["content"] for m in memories]
        tfidf_matrix = self.vectorizer.fit_transform(texts)
        
        # Считаем косинусное сходство
        similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
        
        # Добавляем вес недавних обращений
        now = datetime.now()
        recency_scores = np.array([
            1.0 - (now - m["last_accessed"]).total_seconds() / (24 * 3600)  # Нормализуем на 24 часа
            for m in memories
        ])
        recency_scores = np.clip(recency_scores, 0, 1)
        
        # Комбинируем оценки
        final_scores = (1 - self.recency_weight) * similarities + self.recency_weight * recency_scores
        
        # Сортируем и возвращаем топ-N
        indices = np.argsort(final_scores)[::-1][:self.max_context_memories]
        return [memories[i] for i in indices]
        
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> str:
        """Выполняет инструмент"""
        if tool_name == "remember":
            await self.add_memory(
                params["fact"], 
                params["tags"],
                params.get("user_id")  # Добавляем поддержку user_id
            )
            return f"Запомнил: {params['fact']}"
            
        elif tool_name == "recall":
            memories = await self.search_memories(
                params["query"],
                params.get("user_id")  # Добавляем поддержку user_id
            )
            if not memories:
                return "Не могу ничего вспомнить по этому запросу"
                
            # Обновляем время доступа
            for memory in memories:
                await self.update_access_time(memory["id"])
                
            # Форматируем ответ
            result = "Вот что я помню:\n\n"
            for i, memory in enumerate(memories, 1):
                result += f"{i}. {memory['content']}\n"
                result += f"   Теги: {', '.join(memory['tags'])}\n\n"
            return result.strip()
            
        return f"Неизвестный инструмент: {tool_name}"
        
    async def rag_hook(self, message: IOMessage) -> Dict[str, Any]:
        """Добавляет релевантные воспоминания в контекст"""
        if not isinstance(message, IOMessage):
            return {}
        
        query = message.content  # Используем контент сообщения как запрос
        if not isinstance(query, str):
            return {}
        
        memories = await self.search_memories(query)
        if not memories:
            return {}
        
        return {
            "relevant_memories": "\n".join(
                f"Memory: {memory.content}" for memory in memories
            )
        } 