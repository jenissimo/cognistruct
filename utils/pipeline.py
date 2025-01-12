from abc import ABC, abstractmethod
from typing import List, Optional, Any
from rich import print
from core import BaseAgent
from utils.prompts import load_prompt


class Stage(ABC):
    """Абстрактный класс для этапов пайплайна"""
    
    def __init__(self):
        """Инициализация этапа"""
        self.stage_name = self.__class__.__name__.replace('Stage', '')
    
    def load_prompt(self, template_name: str, **kwargs) -> str:
        """
        Загружает и рендерит промпт из шаблона
        
        Args:
            template_name: Имя файла шаблона (без пути)
            **kwargs: Параметры для рендеринга
            
        Returns:
            str: Отрендеренный текст промпта
        """
        return load_prompt(template_name, **kwargs)
    
    @abstractmethod
    async def run(self, db: Any, llm: Any, agent: BaseAgent) -> bool:
        """
        Выполняет этап обработки
        
        Args:
            db: Объект базы данных
            llm: Объект языковой модели
            agent: Ссылка на агента для доступа к плагинам
            
        Returns:
            bool: True если этап выполнен успешно, False в противном случае
        """
        pass


class StageChain:
    """Цепочка этапов обработки с поддержкой оператора >>"""
    
    def __init__(self, stages: Optional[List[Stage]] = None):
        self.stages = stages or []

    def __rshift__(self, next_stage: 'Stage | StageChain') -> 'StageChain':
        """
        Перегружаем оператор >>, чтобы добавлять этапы в цепочку
        
        Args:
            next_stage: Следующий этап или цепочка этапов
            
        Returns:
            StageChain: Новая цепочка с добавленным этапом
        """
        if isinstance(next_stage, StageChain):
            return StageChain(self.stages + next_stage.stages)
        else:
            return StageChain(self.stages + [next_stage])

    async def run(self, db: Any, llm: Any, agent: BaseAgent, start_from: Optional[str] = None) -> bool:
        """
        Запускаем каждую стадию по порядку
        
        Args:
            db: Объект базы данных
            llm: Объект языковой модели
            agent: Ссылка на агента для доступа к плагинам
            start_from: Имя этапа с которого начать выполнение (опционально)
            
        Returns:
            bool: True если все этапы выполнены успешно, False если произошла ошибка
        """
        # Определяем начальный индекс
        start_idx = 0
        if start_from:
            for i, stage in enumerate(self.stages):
                if stage.stage_name == start_from:
                    start_idx = i
                    print(f"[bold blue]🔄 Продолжаем с этапа: {start_from}[/bold blue]")
                    break
            else:
                print(f"[bold red]❌ Этап {start_from} не найден в пайплайне[/bold red]")
                return False
        
        # Выполняем этапы начиная с указанного
        for stage in self.stages[start_idx:]:
            print(f"\n[bold blue]=== Запуск этапа: {stage.stage_name} ===[/bold blue]")
            try:
                success = await stage.run(db, llm, agent)
                if not success:
                    print(f"[bold yellow]⚠ Остановка на этапе {stage.stage_name}[/bold yellow]")
                    return False
            except Exception as e:
                print(f"[bold red]❌ Ошибка в этапе {stage.stage_name}: {str(e)}[/bold red]")
                return False
                
        print("\n[bold green]✨ Пайплайн успешно завершён![/bold green]")
        return True 