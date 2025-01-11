import asyncio
from typing import Dict, Optional, Callable, Awaitable
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass

from cognistruct.utils.logging import setup_logger

logger = setup_logger(__name__)


@dataclass
class Task:
    """Базовый класс для задач"""
    name: str
    callback: Callable[[], Awaitable[None]]
    next_run: datetime
    interval: Optional[timedelta] = None
    
    def is_recurring(self) -> bool:
        """Проверяет, является ли задача повторяющейся"""
        return self.interval is not None
    
    def schedule_next_run(self) -> None:
        """Планирует следующий запуск задачи"""
        if self.is_recurring():
            self.next_run = datetime.now() + self.interval
        else:
            self.next_run = None


class Scheduler:
    """Планировщик задач"""
    def __init__(self, tick_interval: float = 1.0):
        """
        Инициализация планировщика
        
        Args:
            tick_interval: Интервал проверки задач в секундах
        """
        self.tick_interval = tick_interval
        self.tasks: Dict[str, Task] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Запускает планировщик"""
        if self._running:
            return
            
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.debug("Scheduler started with tick interval %.2f seconds", self.tick_interval)
        
    async def stop(self):
        """Останавливает планировщик"""
        if not self._running:
            return
            
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.debug("Scheduler stopped")
        
    def schedule_task(self, name: str, callback: Callable[[], Awaitable[None]], 
                     delay: timedelta, interval: Optional[timedelta] = None) -> None:
        """
        Планирует новую задачу
        
        Args:
            name: Уникальное имя задачи
            callback: Асинхронная функция для выполнения
            delay: Задержка до первого выполнения
            interval: Интервал повторения (None для одноразовых задач)
        """
        if name in self.tasks:
            raise ValueError(f"Task '{name}' already exists")
            
        next_run = datetime.now() + delay
        task = Task(name=name, callback=callback, next_run=next_run, interval=interval)
        self.tasks[name] = task
        logger.info("Scheduled task '%s' to run at %s", name, next_run)
        
    def cancel_task(self, name: str) -> None:
        """Отменяет запланированную задачу"""
        if name in self.tasks:
            del self.tasks[name]
            logger.info("Cancelled task '%s'", name)
            
    async def _run(self):
        """Основной цикл планировщика"""
        while self._running:
            now = datetime.now()
            tasks_to_run = []
            
            # Собираем задачи для выполнения
            for task in self.tasks.values():
                if task.next_run and now >= task.next_run:
                    tasks_to_run.append(task)
            
            # Выполняем задачи
            for task in tasks_to_run:
                try:
                    logger.debug("Running task '%s'", task.name)
                    await task.callback()
                    task.schedule_next_run()
                    if not task.is_recurring():
                        self.cancel_task(task.name)
                except Exception as e:
                    logger.exception("Error running task '%s'", task.name)
            
            # Ждем следующего тика
            await asyncio.sleep(self.tick_interval) 