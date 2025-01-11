import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import zoneinfo

from cognistruct.core import BasePlugin, IOMessage, PluginMetadata
from cognistruct.llm.interfaces import ToolSchema, ToolParameter
from cognistruct.core.scheduler import Scheduler, Task
from cognistruct.utils.logging import setup_logger

logger = setup_logger(__name__)


class SchedulerPlugin(BasePlugin):
    """Плагин для управления запланированными задачами"""
    
    def __init__(self, tick_interval: float = 1.0, timezone: str = "Europe/Moscow"):
        super().__init__()
        self.scheduler = Scheduler(tick_interval=tick_interval)
        self._callbacks: Dict[str, callable] = {}
        self.timezone = zoneinfo.ZoneInfo(timezone)
        self._started = False
        self._agent = None  # Ссылка на агента для выполнения задач
        
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="scheduler",
            description="Управление запланированными задачами",
            version="1.0.0",
            priority=100
        )
        
    async def setup(self):
        if not self._started:
            await self.scheduler.start()
            logger.info("Scheduler plugin started with timezone: %s", self.timezone)
            self._started = True
        
    async def cleanup(self):
        if self._started:
            await self.scheduler.stop()
            logger.info("Scheduler plugin stopped")
            self._started = False

    def set_agent(self, agent):
        """Устанавливает ссылку на агента для выполнения задач"""
        self._agent = agent
        
    def get_tools(self) -> List[ToolSchema]:
        return [
            ToolSchema(
                name="schedule_task",
                description="Планирует выполнение задачи агентом. Задача будет выполнена с использованием всех доступных инструментов",
                parameters=[
                    ToolParameter(
                        name="name",
                        type="string",
                        description="Уникальное имя задачи"
                    ),
                    ToolParameter(
                        name="task_prompt",
                        type="string",
                        description="Описание задачи для выполнения агентом (например, 'Поздравить пользователя с днем рождения')"
                    ),
                    ToolParameter(
                        name="delay_seconds",
                        type="integer",
                        description="Задержка до выполнения в секундах (используется, если не указана конкретная дата)",
                        required=False
                    ),
                    ToolParameter(
                        name="interval_seconds",
                        type="integer",
                        description="Интервал повторения в секундах (0 для одноразовых задач)",
                        required=False
                    ),
                    ToolParameter(
                        name="date",
                        type="string",
                        description="Дата выполнения в формате YYYY-MM-DD (например, 2024-03-10)",
                        required=False
                    ),
                    ToolParameter(
                        name="time",
                        type="string",
                        description="Время выполнения в формате HH:MM (например, 09:00)",
                        required=False
                    ),
                    ToolParameter(
                        name="yearly",
                        type="boolean",
                        description="Повторять ежегодно в указанную дату",
                        required=False
                    ),
                    ToolParameter(
                        name="system_prompt",
                        type="string",
                        description="Дополнительный системный промпт для выполнения задачи",
                        required=False
                    ),
                    ToolParameter(
                        name="notify_on_complete",
                        type="boolean",
                        description="Отправлять уведомление о результате выполнения задачи (по умолчанию True)",
                        required=False
                    )
                ]
            ),
            ToolSchema(
                name="cancel_task",
                description="Отменяет запланированную задачу",
                parameters=[
                    ToolParameter(
                        name="name",
                        type="string",
                        description="Имя задачи для отмены"
                    )
                ]
            ),
            ToolSchema(
                name="list_tasks",
                description="Показывает список запланированных задач",
                parameters=[]
            )
        ]
        
    def _calculate_next_run(self, date_str: Optional[str], time_str: Optional[str], 
                          yearly: bool = False) -> datetime:
        """Вычисляет время следующего запуска задачи"""
        now = datetime.now(self.timezone)
        
        if date_str and time_str:
            # Парсим дату и время
            task_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            task_time = datetime.strptime(time_str, "%H:%M").time()
            
            # Создаем datetime в указанном часовом поясе
            next_run = datetime.combine(task_date, task_time)
            next_run = next_run.replace(tzinfo=self.timezone)
            
            # Если дата уже прошла и задача ежегодная
            if yearly and next_run < now:
                next_run = next_run.replace(year=now.year + 1)
                
            return next_run
            
        return now  # Если дата/время не указаны, запускаем сейчас
        
    def _calculate_interval(self, yearly: bool, interval_seconds: Optional[int]) -> Optional[timedelta]:
        """Вычисляет интервал повторения задачи"""
        if yearly:
            # Примерно год в секундах (учитываем високосные годы)
            return timedelta(days=365.25)
        elif interval_seconds:
            return timedelta(seconds=interval_seconds)
        return None

    async def _execute_task(self, name: str, task_prompt: str, system_prompt: Optional[str] = None, notify_on_complete: bool = True):
        """Выполняет задачу через LLM"""
        if not self._agent:
            logger.error("Agent not set for task execution")
            return
            
        try:
            logger.info("Executing scheduled task '%s': %s", name, task_prompt)
            
            # Выполняем задачу через агента
            response = await self._agent.process_message(
                message=task_prompt,
                system_prompt=system_prompt
            )
            
            logger.info("Task '%s' completed: %s", name, response)
            
            # Отправляем результат через output_hook только если нужно уведомление
            if notify_on_complete:
                await self.output_hook(IOMessage(
                    type="scheduled_task_result",
                    content={
                        "task_name": name,
                        "task_prompt": task_prompt,
                        "result": response
                    }
                ))
            
        except Exception as e:
            logger.error("Error executing task '%s': %s", name, str(e))
            # Всегда уведомляем об ошибках
            await self.output_hook(IOMessage(
                type="scheduled_task_error",
                content={
                    "task_name": name,
                    "task_prompt": task_prompt,
                    "error": str(e)
                }
            ))
        
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> str:
        if tool_name == "schedule_task":
            name = params["name"]
            task_prompt = params["task_prompt"]
            system_prompt = params.get("system_prompt")
            notify_on_complete = params.get("notify_on_complete", True)
            
            # Определяем время следующего запуска
            date_str = params.get("date")
            time_str = params.get("time")
            yearly = params.get("yearly", False)
            
            if date_str or time_str:
                next_run = self._calculate_next_run(date_str, time_str, yearly)
                delay = next_run - datetime.now(self.timezone)
            else:
                delay = timedelta(seconds=params.get("delay_seconds", 0))
                next_run = datetime.now(self.timezone) + delay
                
            # Определяем интервал повторения
            interval = self._calculate_interval(
                yearly=yearly,
                interval_seconds=params.get("interval_seconds")
            )
            
            # Создаем замыкание для сохранения параметров задачи
            async def task_callback():
                await self._execute_task(name, task_prompt, system_prompt, notify_on_complete)
            
            self.scheduler.schedule_task(name, task_callback, delay, interval)
            
            # Формируем понятное описание
            result = f"Задача '{name}' ({task_prompt}) запланирована на {next_run.strftime('%d.%m.%Y %H:%M')}"
            if yearly:
                result += " (повторяется ежегодно)"
            elif interval:
                result += f" (повторяется каждые {interval.total_seconds()} секунд)"
            if not notify_on_complete:
                result += " (без уведомления о выполнении)"
            return result
            
        elif tool_name == "cancel_task":
            name = params["name"]
            self.scheduler.cancel_task(name)
            return f"Задача '{name}' отменена"
            
        elif tool_name == "list_tasks":
            tasks = []
            for name, task in self.scheduler.tasks.items():
                task_info = {
                    "name": name,
                    "next_run": task.next_run.astimezone(self.timezone).strftime("%d.%m.%Y %H:%M"),
                    "recurring": task.is_recurring()
                }
                tasks.append(task_info)
            
            if not tasks:
                return "Нет запланированных задач"
                
            result = "Запланированные задачи:\n"
            for task in tasks:
                result += f"- {task['name']}: следующий запуск в {task['next_run']}"
                if task['recurring']:
                    result += " (повторяющаяся)"
                result += "\n"
            return result.strip()
            
        return f"Неизвестный инструмент: {tool_name}" 