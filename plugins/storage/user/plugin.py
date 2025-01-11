import os
import sqlite3
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from core import BasePlugin, PluginMetadata
from utils.logging import setup_logger

logger = setup_logger(__name__)

@dataclass
class User:
    """Модель пользователя"""
    id: int
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    metadata: Dict[str, Any] = None
    created_at: float = None
    updated_at: float = None

class UserStoragePlugin(BasePlugin):
    """Плагин для хранения информации о пользователях"""

    def __init__(self, db_path: str = "data/users.db"):
        """
        Инициализация плагина
        
        Args:
            db_path: Путь к файлу базы данных SQLite
        """
        super().__init__()
        self.db_path = db_path
        self._conn = None
        self._setup_db()

    def get_metadata(self) -> PluginMetadata:
        """Получить метаданные плагина"""
        return PluginMetadata(
            name="user_storage",
            description="Хранение информации о пользователях",
            version="1.0.0",
            author="CogniStruct"
        )

    def _setup_db(self):
        """Инициализация базы данных"""
        # Создаем директорию если нужно
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Подключаемся к базе
        self._conn = sqlite3.connect(self.db_path)
        
        # Создаем таблицу пользователей
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    display_name TEXT,
                    email TEXT,
                    metadata TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            """)

    async def cleanup(self):
        """Очистка ресурсов"""
        if self._conn:
            self._conn.close()

    async def create_user(self, username: str, **kwargs) -> User:
        """
        Создать нового пользователя
        
        Args:
            username: Уникальное имя пользователя
            **kwargs: Дополнительные поля (display_name, email, metadata)
        
        Returns:
            User: Созданный пользователь
        """
        import time
        import json
        
        now = time.time()
        
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO users (
                    username, display_name, email, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    kwargs.get('display_name'),
                    kwargs.get('email'),
                    json.dumps(kwargs.get('metadata', {})),
                    now,
                    now
                )
            )
            
            user_id = cursor.lastrowid
            
            return User(
                id=user_id,
                username=username,
                display_name=kwargs.get('display_name'),
                email=kwargs.get('email'),
                metadata=kwargs.get('metadata', {}),
                created_at=now,
                updated_at=now
            )

    async def get_user(self, user_id: int) -> Optional[User]:
        """
        Получить пользователя по ID
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Optional[User]: Найденный пользователь или None
        """
        import json
        
        with self._conn:
            cursor = self._conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
                
            return User(
                id=row[0],
                username=row[1],
                display_name=row[2],
                email=row[3],
                metadata=json.loads(row[4]) if row[4] else {},
                created_at=row[5],
                updated_at=row[6]
            )

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Получить пользователя по имени
        
        Args:
            username: Имя пользователя
            
        Returns:
            Optional[User]: Найденный пользователь или None
        """
        import json
        
        with self._conn:
            cursor = self._conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
                
            return User(
                id=row[0],
                username=row[1],
                display_name=row[2],
                email=row[3],
                metadata=json.loads(row[4]) if row[4] else {},
                created_at=row[5],
                updated_at=row[6]
            )

    async def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        """
        Обновить данные пользователя
        
        Args:
            user_id: ID пользователя
            **kwargs: Поля для обновления
            
        Returns:
            Optional[User]: Обновленный пользователь или None
        """
        import time
        import json
        
        # Получаем текущего пользователя
        user = await self.get_user(user_id)
        if not user:
            return None
            
        # Обновляем поля
        updates = {}
        if 'display_name' in kwargs:
            updates['display_name'] = kwargs['display_name']
        if 'email' in kwargs:
            updates['email'] = kwargs['email']
        if 'metadata' in kwargs:
            updates['metadata'] = json.dumps(kwargs['metadata'])
            
        if not updates:
            return user
            
        # Добавляем время обновления
        updates['updated_at'] = time.time()
        
        # Формируем SQL запрос
        fields = ', '.join(f"{k} = ?" for k in updates.keys())
        values = tuple(updates.values())
        
        with self._conn:
            self._conn.execute(
                f"UPDATE users SET {fields} WHERE id = ?",
                values + (user_id,)
            )
            
        # Получаем обновленного пользователя
        return await self.get_user(user_id)

    async def delete_user(self, user_id: int) -> bool:
        """
        Удалить пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если пользователь был удален
        """
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM users WHERE id = ?",
                (user_id,)
            )
            return cursor.rowcount > 0

    async def search_users(self, query: str) -> List[User]:
        """
        Поиск пользователей по имени или отображаемому имени
        
        Args:
            query: Поисковый запрос
            
        Returns:
            List[User]: Список найденных пользователей
        """
        import json
        
        with self._conn:
            cursor = self._conn.execute(
                """
                SELECT * FROM users 
                WHERE username LIKE ? OR display_name LIKE ?
                """,
                (f"%{query}%", f"%{query}%")
            )
            
            users = []
            for row in cursor:
                users.append(User(
                    id=row[0],
                    username=row[1],
                    display_name=row[2],
                    email=row[3],
                    metadata=json.loads(row[4]) if row[4] else {},
                    created_at=row[5],
                    updated_at=row[6]
                ))
                
            return users 