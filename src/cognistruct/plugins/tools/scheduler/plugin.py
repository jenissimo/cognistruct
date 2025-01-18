import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import zoneinfo
import uuid

from cognistruct.core import BasePlugin, IOMessage, PluginMetadata
from cognistruct.llm.interfaces import ToolSchema, ToolParameter
from .database import SchedulerDatabase
from cognistruct.utils.logging import setup_logger

logger = setup_logger(__name__)


class SchedulerPlugin(BasePlugin):
    """Плагин для управления запланированными задачами"""
    
    def __init__(self, db_path: str = None, tick_interval: float = 1.0, timezone: str = "UTC"):
        super().__init__()
        self.db = SchedulerDatabase(db_path, timezone)
        self.tick_interval = tick_interval
        self._running = False
        self._disabled_tools = set()  # Множество отключенных инструментов
        
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="scheduler",
            description="Управление запланированными задачами",
            version="1.0.0",
            priority=100
        )
        
    async def setup(self):
        await self.db.connect()
        self._running = True
        asyncio.create_task(self._tick())
        
    async def cleanup(self):
        self._running = False
        await self.db.close()
        
    async def disable_tool(self, tool_name: str):
        """Временно отключает инструмент"""
        self._disabled_tools.add(tool_name)
        
    async def enable_tool(self, tool_name: str):
        """Включает ранее отключенный инструмент"""
        self._disabled_tools.discard(tool_name)
        
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> str:
        # Проверяем, не отключен ли инструмент
        if tool_name in self._disabled_tools:
            return f"Инструмент {tool_name} временно недоступен"
            
        if tool_name == "schedule_task":
            user_id = params.pop("user_id", None)
            if not user_id:
                return "Ошибка: не указан user_id"
                
            task_id = str(uuid.uuid4())
            name = params["name"]
            task_prompt = params["task_prompt"]
            
            # Рассчитываем время следующего запуска
            next_run = datetime.now()
            if "delay" in params:
                next_run += timedelta(seconds=params["delay"])
                
            # Добавляем задачу в БД
            await self.db.add_task(
                task_id=task_id,
                user_id=user_id,
                name=name,
                task_prompt=task_prompt,
                next_run=next_run,
                interval=params.get("interval"),
                system_prompt=params.get("system_prompt"),
                notify_on_complete=params.get("notify_on_complete", True)
            )
            
            return f"Задача '{name}' запланирована на {next_run.strftime('%d.%m.%Y %H:%M')}"
            
        elif tool_name == "list_tasks":
            user_id = params.pop("user_id", None)
            if not user_id:
                return "Ошибка: не указан user_id"
                
            tasks = await self.db.get_user_tasks(user_id)
            if not tasks:
                return "У вас нет запланированных задач"
                
            result = "Ваши задачи:\n"
            for task in tasks:
                next_run = datetime.fromisoformat(task["next_run"])
                result += f"- {task['name']}: {next_run.strftime('%d.%m.%Y %H:%M')}\n"
            return result.strip()
            
    async def _tick(self):
        """Проверяет и выполняет задачи"""
        while self._running:
            try:
                now = datetime.now(self.db.timezone)
                
                # Получаем все задачи из БД
                async with self.db.db.execute(
                    "SELECT * FROM tasks WHERE next_run <= ?",
                    (now.isoformat(),)
                ) as cursor:
                    tasks = [dict(row) for row in await cursor.fetchall()]
                    
                for task in tasks:
                    # Отключаем инструменты планировщика на время выполнения задачи
                    await self.disable_tool("schedule_task")
                    await self.disable_tool("list_tasks")
                    
                    try:
                        message = IOMessage(
                            type="text",
                            content=task["task_prompt"],
                            metadata={
                                "user_id": task["user_id"],
                                "scheduled": True,
                                "task_id": task["id"],
                                "task_name": task["name"]
                            }
                        )
                        
                        await self.agent.handle_message(
                            message,
                            system_prompt=task["system_prompt"],
                            stream=False
                        )
                        
                    finally:
                        # Включаем инструменты обратно
                        await self.enable_tool("schedule_task")
                        await self.enable_tool("list_tasks")
                    
                    # Обновляем время следующего запуска
                    if task["interval"]:
                        next_run = datetime.fromisoformat(task["next_run"]) + \
                                 timedelta(seconds=task["interval"])
                        await self.db.db.execute(
                            "UPDATE tasks SET next_run = ? WHERE id = ?",
                            (next_run.isoformat(), task["id"])
                        )
                    else:
                        await self.db.db.execute(
                            "DELETE FROM tasks WHERE id = ?",
                            (task["id"],)
                        )
                        
                    await self.db.db.commit()
                    
            except Exception as e:
                logger.error(f"Error in scheduler tick: {e}")
                
            await asyncio.sleep(self.tick_interval) 