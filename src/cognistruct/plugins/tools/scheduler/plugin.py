import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import zoneinfo
import uuid
import logging

from cognistruct.core import BasePlugin, IOMessage, PluginMetadata, RequestContext
from cognistruct.llm.interfaces import ToolSchema, ToolParameter
from .database import SchedulerDatabase
from cognistruct.utils.logging import setup_logger

logger = logging.getLogger(__name__)


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
        
    def get_tools(self) -> List[ToolSchema]:
        """Возвращает инструменты для работы с планировщиком"""
        return [
            ToolSchema(
                name="schedule_task",
                description="Планирует отложенную задачу в виде промпта для тебя (например напомнить пользователю о чем-то) в указанное время или с заданной периодичностью. Если тебе не хватает контекста о дате/времени выполнения задачи, то уточни его у пользователя.",
                parameters=[
                    ToolParameter(
                        name="task_prompt",
                        type="string",
                        description="Промпт для LLM, описывающий что нужно сделать в указанное время, например \"Напомнить пользователю купить молоко\" или \"Написать пользователю мотивирующее сообщение\"."
                    ),
                    ToolParameter(
                        name="scheduled_for",
                        type="string",
                        description="Дата и время выполнения в формате 'DD.MM.YYYY HH:mm:ss'. Например: '25.12.2024 15:30:00'."
                    ),
                    ToolParameter(
                        name="recurrence",
                        type="string",
                        enum=["none", "daily", "weekly", "monthly", "yearly"],
                        description="Частота повторения. Возможные значения: 'none', 'daily', 'weekly', 'monthly', 'yearly'. По умолчанию: 'none'",
                        required=False
                    )
                ]
            ),
            #ToolSchema(
            #    name="list_tasks",
            #    description="Показывает список запланированных задач",
            #    parameters=[]
            #)
        ]
        
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
        
    async def execute_tool(self, tool_name: str, params: Dict[str, Any], context: Optional['RequestContext'] = None) -> Dict[str, Any]:
        print(f"Executing tool {tool_name} with params: {params}")
        
        if tool_name in self._disabled_tools:
            return {"content": f"Инструмент {tool_name} временно недоступен"}
        
        if tool_name == "schedule_task":
            task_id = str(uuid.uuid4())
            task_prompt = params["task_prompt"]
            scheduled_for = datetime.strptime(params["scheduled_for"], "%d.%m.%Y %H:%M:%S")
            recurrence = params.get("recurrence", "none")
            
            # Получаем user_id из контекста или параметров
            user_id = context.user_id if context else None
            
            # Рассчитываем интервал повторения
            interval = None
            if recurrence == "daily":
                interval = 24 * 60 * 60  # каждые 24 часа
            elif recurrence == "weekly":
                interval = 7 * 24 * 60 * 60  # каждые 7 дней
            elif recurrence == "monthly":
                interval = 30 * 24 * 60 * 60  # примерно месяц
            elif recurrence == "yearly":
                interval = 365 * 24 * 60 * 60  # примерно год
            
            # Добавляем задачу в БД
            await self.db.add_task(
                task_id=task_id,
                user_id=user_id,  # используем user_id из контекста
                name="llm_task",
                task_prompt=task_prompt,
                next_run=scheduled_for,
                interval=interval,
                notify_on_complete=True
            )
            
            recurrence_text = f" (повторяется {recurrence})" if recurrence != "none" else ""
            return {
                "content": f"Задача запланирована на {scheduled_for.strftime('%d.%m.%Y %H:%M')}{recurrence_text}"
            }
            
        elif tool_name == "list_tasks":
            tasks = await self.db.get_user_tasks(None)  # user_id будет браться из контекста
            if not tasks:
                return {"content": "У вас нет запланированных задач"}
                
            result = "Ваши задачи:\n"
            for task in tasks:
                next_run = datetime.fromisoformat(task["next_run"])
                interval_text = " (повторяющаяся)" if task["interval"] else ""
                result += f"- {task['task_prompt']}: {next_run.strftime('%d.%m.%Y %H:%M')}{interval_text}\n"
            return {"content": result.strip()}
            
        return {"content": f"Неизвестный инструмент: {tool_name}"}
        
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
                        # Создаем контекст запроса
                        request_context = RequestContext(
                            user_id=task["user_id"],
                            metadata={
                                "scheduled": True,
                                "task_id": task["id"],
                                "platform": "scheduler",
                                "task_prompt": task["task_prompt"],
                                "next_run": task["next_run"]
                            },
                            timestamp=datetime.now().timestamp()
                        )
                        
                        # Создаем сообщение с промптом для LLM
                        message = IOMessage(
                            type="text",
                            content=task["task_prompt"],
                            metadata={
                                "user_id": task["user_id"],
                                "scheduled": True,
                                "task_id": task["id"]
                            },
                            source="scheduler",
                            context=request_context
                        )
                        
                        # Обрабатываем промпт через LLM
                        await self.agent.handle_message(
                            message,
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