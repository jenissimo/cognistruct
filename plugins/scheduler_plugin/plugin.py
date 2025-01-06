from datetime import datetime, timedelta, time
import zoneinfo
from typing import Dict, List, Optional, Any

from plugins.base_plugin import BasePlugin
from llm.interfaces import ToolSchema, ToolParameter
from utils.scheduler import Scheduler, Task
from utils.logging import setup_logger

logger = setup_logger(__name__)


class SchedulerPlugin(BasePlugin):
    """Плагин для управления запланированными задачами"""
    
    def __init__(self, tick_interval: float = 1.0, timezone: str = "Europe/Moscow"):
        super().__init__()
        self.scheduler = Scheduler(tick_interval=tick_interval)
        self._callbacks: Dict[str, callable] = {}
        self.timezone = zoneinfo.ZoneInfo(timezone)
        self._started = False
        
    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": "scheduler",
            "description": "Управление запланированными задачами",
            "version": "1.0",
            "priority": 100
        }
        
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
        
    def get_tools(self) -> List[ToolSchema]:
        return [
            ToolSchema(
                name="schedule_task",
                description="Планирует выполнение задачи",
                parameters=[
                    ToolParameter(
                        name="name",
                        type="string",
                        description="Уникальное имя задачи"
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
                        name="message",
                        type="string",
                        description="Сообщение для отправки агенту при выполнении задачи"
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
        
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> str:
        if tool_name == "schedule_task":
            name = params["name"]
            message = params["message"]
            
            # Определяем время следующего запуска
            date_str = params.get("date")
            time_str = params.get("time")
            yearly = params.get("yearly", False)
            
            if date_str or time_str:
                next_run = self._calculate_next_run(date_str, time_str, yearly)
                delay = next_run - datetime.now(self.timezone)
            else:
                delay = timedelta(seconds=params.get("delay_seconds", 0))
                
            # Определяем интервал повторения
            interval = self._calculate_interval(
                yearly=yearly,
                interval_seconds=params.get("interval_seconds")
            )
            
            # Создаем замыкание для сохранения сообщения
            async def task_callback():
                logger.info("Task '%s' executed with message: %s", name, message)
                # TODO: Здесь можно добавить обработку сообщения агентом
            
            self.scheduler.schedule_task(name, task_callback, delay, interval)
            
            # Формируем понятное описание
            result = f"Задача '{name}' запланирована на {next_run.strftime('%d.%m.%Y %H:%M')}"
            if yearly:
                result += " (повторяется ежегодно)"
            elif interval:
                result += f" (повторяется каждые {interval.total_seconds()} секунд)"
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