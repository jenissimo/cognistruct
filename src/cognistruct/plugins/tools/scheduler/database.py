import os
import aiosqlite
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import zoneinfo

logger = logging.getLogger(__name__)

class SchedulerDatabase:
    """База данных для планировщика"""
    
    def __init__(self, db_path: str = None, timezone: str = "UTC"):
        self.db_path = db_path or os.path.join("data", "scheduler.db")
        self.timezone = zoneinfo.ZoneInfo(timezone)
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
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                task_prompt TEXT NOT NULL,
                system_prompt TEXT,
                next_run TIMESTAMP NOT NULL,
                interval INTEGER,
                notify_on_complete BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                timezone TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        await self.db.commit()
        
    async def add_task(self, task_id: str, user_id: str, name: str, task_prompt: str,
                      next_run: datetime, interval: Optional[int] = None,
                      system_prompt: Optional[str] = None,
                      notify_on_complete: bool = True) -> bool:
        """Добавляет задачу в базу"""
        try:
            # Конвертируем время в указанный часовой пояс
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=self.timezone)
                
            await self.db.execute(
                """
                INSERT INTO tasks (
                    id, user_id, name, task_prompt, system_prompt, 
                    next_run, interval, notify_on_complete, timezone
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, user_id, name, task_prompt, system_prompt,
                 next_run.isoformat(), interval, notify_on_complete, str(self.timezone))
            )
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding task: {e}")
            return False
            
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Получает задачу по ID"""
        async with self.db.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None
        
    async def get_user_tasks(self, user_id: str) -> List[Dict[str, Any]]:
        """Получает все задачи пользователя"""
        async with self.db.execute(
            "SELECT * FROM tasks WHERE user_id = ? ORDER BY next_run",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows] 