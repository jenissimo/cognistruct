from abc import ABC, abstractmethod
from typing import List, Optional, Any
from rich import print
from core import BaseAgent
from utils.prompts import load_prompt


class Stage(ABC):
    """Абстрактный класс для этапов пайплайна"""
    
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
    def run(self, db: Any, llm: Any, agent: BaseAgent) -> bool:
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

    def run(self, db: Any, llm: Any, agent: BaseAgent) -> bool:
        """
        Запускаем каждую стадию по порядку
        
        Args:
            db: Объект базы данных
            llm: Объект языковой модели
            agent: Ссылка на агента для доступа к плагинам
            
        Returns:
            bool: True если все этапы выполнены успешно, False если произошла ошибка
        """
        for stage in self.stages:
            print(f"\n[bold blue]=== Запуск стадии: {stage.__class__.__name__} ===[/bold blue]")
            try:
                success = stage.run(db, llm, agent)
                if not success:
                    print(f"[bold yellow]⚠ Остановка на стадии {stage.__class__.__name__}[/bold yellow]")
                    return False
            except Exception as e:
                print(f"[bold red]❌ Ошибка в стадии {stage.__class__.__name__}: {str(e)}[/bold red]")
                return False
                
        print("\n[bold green]✨ Пайплайн успешно завершён![/bold green]")
        return True 