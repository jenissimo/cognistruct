from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass
import sqlite3
import json
import time
from pathlib import Path
import asyncio
import re
import uuid
import os
import logging

from sklearn.feature_extraction.text import TfidfVectorizer
from core import BasePlugin, PluginMetadata

logger = logging.getLogger(__name__)


@dataclass
class VersionedArtifact:
    """Версионированный артефакт"""
    key: str
    value: Any
    version: int
    created_at: float
    metadata: Dict[str, Any]


class VersionedStoragePlugin(BasePlugin):
    """
    Плагин для хранения версионированных артефактов
    
    Каждый артефакт имеет:
    - key: уникальный ключ
    - value: значение (может быть любым JSON-сериализуемым объектом)
    - version: версия (автоматически увеличивается при обновлении)
    - created_at: время создания версии
    - metadata: дополнительные метаданные (включая теги)
    """
    
    def __init__(self, 
                 db_path: str = "versioned_storage.db",
                 version_weight: float = 0.3,  # Вес версии при ранжировании
                 time_weight: float = 0.2):    # Вес времени создания
        super().__init__()
        self._db: Optional[sqlite3.Connection] = None
        self.db_path = db_path
        self.version_weight = version_weight
        self.time_weight = time_weight
        self.vectorizer = TfidfVectorizer()
        
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="versioned_storage",
            description="Хранилище версионированных артефактов",
            version="0.2.0",
            author="Cognistruct"
        )
        
    async def setup(self):
        """Инициализация БД"""
        def _setup():
            self._db = sqlite3.connect(self.db_path)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS artifacts (
                    key TEXT,
                    value TEXT,
                    version INTEGER,
                    created_at REAL,
                    metadata TEXT,
                    PRIMARY KEY (key, version)
                )
            """)
            self._db.commit()
            
        await asyncio.to_thread(_setup)
        
    async def cleanup(self):
        """Закрытие соединения с БД"""
        if self._db:
            self._db.close()
            
    async def create(self, data: Dict[str, Any]) -> VersionedArtifact:
        """Создание нового артефакта"""
        key = data["key"]
        value = data["value"]
        metadata = data.get("metadata", {})
        
        # Проверяем существование артефакта
        cursor = self._db.execute(
            "SELECT MAX(version) FROM artifacts WHERE key = ?",
            (key,)
        )
        result = cursor.fetchone()
        version = 1 if result[0] is None else result[0] + 1
        
        # Сохраняем новую версию
        created_at = time.time()
        self._db.execute(
            "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?)",
            (key, json.dumps(value), version, created_at, json.dumps(metadata))
        )
        self._db.commit()
        
        return VersionedArtifact(key, value, version, created_at, metadata)
        
    async def read(self, id: str) -> Optional[Dict[str, Any]]:
        """Получение последней версии артефакта по ключу"""
        cursor = self._db.execute("""
            SELECT value, version, created_at, metadata 
            FROM artifacts 
            WHERE key = ? 
            ORDER BY version DESC 
            LIMIT 1
        """, (id,))
        row = cursor.fetchone()
        
        if not row:
            return None
            
        return {
            "key": id,
            "value": json.loads(row[0]),
            "version": row[1],
            "created_at": row[2],
            "metadata": json.loads(row[3])
        }
        
    async def update(self, id: str, data: Dict[str, Any]) -> bool:
        """
        Обновление артефакта (создает новую версию)
        Возвращает True, так как всегда создает новую версию
        """
        return bool(await self.create({"key": id, **data}))
        
    async def delete(self, id: str) -> bool:
        """Удаление всех версий артефакта"""
        cursor = self._db.execute("DELETE FROM artifacts WHERE key = ?", (id,))
        self._db.commit()
        return cursor.rowcount > 0
        
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Умный поиск артефактов
        
        Поддерживаемые параметры:
        - key_prefix: префикс ключа
        - version: конкретная версия
        - latest_only: только последние версии
        - text_query: текстовый поиск по содержимому
        - tags: список тегов для фильтрации
        """
        def _search():
            sql = "SELECT key, value, version, created_at, metadata FROM artifacts"
            params = []
            where_clauses = []
            
            # Базовая фильтрация
            if "key_prefix" in query:
                where_clauses.append("key LIKE ?")
                params.append(f"{query['key_prefix']}%")
                
            if "version" in query:
                where_clauses.append("version = ?")
                params.append(query["version"])
                
            if "tags" in query:
                tags = query["tags"]
                if isinstance(tags, str):
                    tags = [tags]
                # Поиск по тегам в метаданных через JSON
                tags_conditions = []
                for tag in tags:
                    tags_conditions.append(f"json_extract(metadata, '$.tags') LIKE '%{tag}%'")
                if tags_conditions:
                    where_clauses.append(f"({' OR '.join(tags_conditions)})")
                
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
                
            if query.get("latest_only"):
                sql = f"""
                    WITH latest_versions AS (
                        SELECT key, MAX(version) as max_version
                        FROM ({sql}) sub
                        GROUP BY key
                    )
                    SELECT a.* 
                    FROM artifacts a
                    JOIN latest_versions lv 
                        ON a.key = lv.key 
                        AND a.version = lv.max_version
                """
                
            cursor = self._db.execute(sql, params)
            artifacts = []
            
            for row in cursor.fetchall():
                key, value, version, created_at, metadata = row
                artifacts.append({
                    "key": key,
                    "value": json.loads(value),
                    "version": version,
                    "created_at": created_at,
                    "metadata": json.loads(metadata)
                })
                
            if not artifacts:
                return []
                
            # Если есть текстовый запрос, используем TF-IDF
            if "text_query" in query and query["text_query"]:
                # Подготавливаем тексты для векторизации
                search_query = query["text_query"]
                texts = [search_query]
                
                # Извлекаем текстовое содержимое из артефактов
                for artifact in artifacts:
                    if isinstance(artifact["value"], dict) and "text" in artifact["value"]:
                        texts.append(artifact["value"]["text"])
                    else:
                        texts.append(json.dumps(artifact["value"]))
                
                # Векторизуем и считаем сходство
                tfidf_matrix = self.vectorizer.fit_transform(texts)
                similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
                
                # Нормализуем версии и время создания
                max_version = max(a["version"] for a in artifacts)
                version_scores = np.array([a["version"] / max_version for a in artifacts])
                
                latest_time = max(a["created_at"] for a in artifacts)
                time_scores = np.array([a["created_at"] / latest_time for a in artifacts])
                
                # Комбинируем оценки
                content_weight = 1 - self.version_weight - self.time_weight
                final_scores = (
                    content_weight * similarities + 
                    self.version_weight * version_scores +
                    self.time_weight * time_scores
                )
                
                # Сортируем по финальной оценке
                scored_artifacts = list(zip(artifacts, final_scores))
                scored_artifacts.sort(key=lambda x: x[1], reverse=True)
                
                return [artifact for artifact, _ in scored_artifacts]
            
            # Если нет текстового запроса, сортируем по версии и времени
            artifacts.sort(key=lambda x: (x["version"], x["created_at"]), reverse=True)
            return artifacts
            
        return await asyncio.to_thread(_search)
        
    def get_tools(self) -> List[Dict[str, Any]]:
        """Возвращает инструмент для работы с артефактами"""
        return [{
            "name": "manage_artifact",
            "description": "Управление версионированными артефактами",
            "parameters": {
                "action": {
                    "type": "string",
                    "enum": ["create", "read", "update", "delete", "search"],
                    "description": "Действие"
                },
                "key": {
                    "type": "string",
                    "description": "Ключ артефакта (для create/read/update/delete)"
                },
                "value": {
                    "type": "object",
                    "description": "Значение артефакта (для create/update)"
                },
                "metadata": {
                    "type": "object",
                    "description": "Метаданные и теги (для create/update)"
                },
                "search_params": {
                    "type": "object",
                    "description": "Параметры поиска (key_prefix, version, latest_only, text_query, tags)"
                }
            }
        }]
        
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Выполняет действия с артефактами"""
        if tool_name != "manage_artifact":
            raise NotImplementedError(f"Unknown tool: {tool_name}")
            
        action = params["action"]
        
        if action == "create":
            return await self.create({
                "key": params["key"],
                "value": params["value"],
                "metadata": params.get("metadata", {})
            })
        elif action == "read":
            return await self.read(params["key"])
        elif action == "update":
            return await self.update(params["key"], {
                "value": params["value"],
                "metadata": params.get("metadata", {})
            })
        elif action == "delete":
            return await self.delete(params["key"])
        elif action == "search":
            return await self.search(params["search_params"])
        else:
            raise ValueError(f"Unknown action: {action}") 
        
    def generate_id(self, prefix: str, title: Optional[str] = None) -> str:
        """
        Генерирует уникальный ID для артефакта
        
        Args:
            prefix: Префикс для типа артефакта (например, 'note', 'prompt')
            title: Опциональное название для создания slug
            
        Returns:
            Уникальный ID
        """
        if title:
            # Создаем slug из заголовка (транслит + нижний регистр + замена пробелов)
            slug = re.sub(r'[^a-z0-9]+', '_', title.lower())
            # Добавляем короткий хэш для уникальности
            return f"{prefix}/{slug}_{uuid.uuid4().hex[:6]}"
        else:
            # Просто используем префикс и UUID
            return f"{prefix}/{uuid.uuid4().hex[:12]}"
            
    def generate_hierarchical_id(self, *parts: Union[str, Tuple[str, str]]) -> str:
        """
        Генерирует иерархический ID из частей, поддерживая шаблоны вида Type{value}
        
        Args:
            *parts: Части ID. Каждая часть может быть:
                   - строкой (используется как есть)
                   - кортежем (тип, значение) для генерации Type{value}
        
        Examples:
            >>> generate_hierarchical_id("books", ("book", "1"), ("chapter", "12"), ("scene", "3"))
            "books/Book1/Chapter12/Scene3"
            
            >>> generate_hierarchical_id(("book", "hp1"), "chapters", ("scene", "battle"))
            "Book_hp1/chapters/Scene_battle"
        """
        formatted_parts = []
        for part in parts:
            if isinstance(part, tuple) and len(part) == 2:
                type_name, value = part
                # Очищаем значение и делаем первую букву типа заглавной
                clean_value = re.sub(r'[^a-z0-9_-]+', '_', str(value).lower())
                formatted_type = type_name.capitalize()
                formatted_parts.append(f"{formatted_type}{clean_value}")
            else:
                # Для обычных строк просто очищаем
                clean_part = re.sub(r'[^a-z0-9_-]+', '_', str(part).lower())
                formatted_parts.append(clean_part)
                
        return "/".join(formatted_parts) 