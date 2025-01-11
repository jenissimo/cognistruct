import os
import time
import uuid
import logging
import aiosqlite
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TelegramDatabase:
    """Класс для работы с базой данных Telegram плагина"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join("data", "telegram.db")
        self.db = None
        
    async def connect(self):
        """Подключение к базе данных"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self._create_tables()
        
    async def close(self):
        """Закрытие соединения"""
        if self.db:
            await self.db.close()
            
    async def _create_tables(self):
        """Создание таблиц"""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS secret_keys (
                key TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE
            )
        """)
        
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS chat_links (
                chat_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS confirmations (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                message TEXT NOT NULL,
                callback_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (chat_id) REFERENCES chat_links(chat_id)
            )
        """)
        
        await self.db.commit()
        
    async def generate_secret_key(self, user_id: str, expires_in: int = 3600) -> str:
        """Генерирует секретный ключ для привязки"""
        key = str(uuid.uuid4())
        expires_at = time.time() + expires_in
        
        logger.info(f"Generating secret key: {key} for user {user_id}, expires at {expires_at}")
        
        await self.db.execute(
            "INSERT INTO secret_keys (key, user_id, expires_at) VALUES (?, ?, ?)",
            (key, user_id, expires_at)
        )
        await self.db.commit()
        
        return key
        
    async def check_secret_key(self, key: str) -> Optional[Dict[str, Any]]:
        """Проверяет секретный ключ"""
        current_time = time.time()
        async with self.db.execute(
            """
            SELECT user_id, used, expires_at 
            FROM secret_keys 
            WHERE key = ? AND expires_at > ? AND used = FALSE
            """,
            (key, current_time)
        ) as cursor:
            row = await cursor.fetchone()
            
        if row:
            return dict(row)
        return None
        
    async def mark_key_used(self, key: str):
        """Помечает ключ как использованный"""
        await self.db.execute(
            "UPDATE secret_keys SET used = TRUE WHERE key = ?",
            (key,)
        )
        await self.db.commit()
        
    async def link_chat(self, chat_id: str, user_id: str):
        """Привязывает чат к пользователю"""
        await self.db.execute(
            "INSERT OR REPLACE INTO chat_links (chat_id, user_id) VALUES (?, ?)",
            (chat_id, user_id)
        )
        await self.db.commit()
        
    async def get_chat_link(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о привязке чата"""
        async with self.db.execute(
            "SELECT user_id FROM chat_links WHERE chat_id = ?",
            (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            
        if row:
            return dict(row)
        return None
        
    async def create_confirmation(self, message: str, chat_id: str, callback_data: str = "", expires_in: int = 3600) -> str:
        """Создает запрос на подтверждение"""
        confirmation_id = str(uuid.uuid4())
        await self.db.execute(
            """
            INSERT INTO confirmations (id, chat_id, message, callback_data, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                confirmation_id,
                chat_id,
                message,
                callback_data,
                time.time() + expires_in
            )
        )
        await self.db.commit()
        return confirmation_id
        
    async def update_confirmation_status(self, confirmation_id: str, status: str):
        """Обновляет статус подтверждения"""
        await self.db.execute(
            "UPDATE confirmations SET status = ? WHERE id = ?",
            (status, confirmation_id)
        )
        await self.db.commit()
        
    async def get_chat_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о чате по user_id"""
        async with self.db.execute(
            "SELECT chat_id FROM chat_links WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            
        if row:
            return dict(row)
        return None
        
    async def get_all_chats_by_user(self, user_id: str) -> list[Dict[str, Any]]:
        """Получает информацию о всех чатах пользователя"""
        async with self.db.execute(
            "SELECT chat_id FROM chat_links WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            
        return [dict(row) for row in rows] 