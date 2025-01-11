import os
from typing import Dict, Any, Optional, List
from jinja2 import Template, Environment, FileSystemLoader, ChoiceLoader
from pathlib import Path

class PromptManager:
    """Менеджер для работы с промптами"""
    
    def __init__(self):
        self._prompt_dirs: List[str] = []
        self._env: Optional[Environment] = None
        
    def add_prompt_dir(self, path: str | Path):
        """
        Добавляет директорию с промптами
        
        Args:
            path: Путь к директории с промптами (абсолютный или относительный)
        """
        path = str(Path(path).absolute())
        if path not in self._prompt_dirs:
            self._prompt_dirs.append(path)
            self._rebuild_env()
            
    def _rebuild_env(self):
        """Пересоздает окружение Jinja2 с учетом всех директорий"""
        loaders = [FileSystemLoader(path) for path in self._prompt_dirs]
        self._env = Environment(
            loader=ChoiceLoader(loaders),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
    def load_prompt(self, template_name: str, **kwargs) -> str:
        """
        Загружает и рендерит промпт из шаблона
        
        Args:
            template_name: Имя файла шаблона (без пути)
            **kwargs: Параметры для рендеринга
            
        Returns:
            str: Отрендеренный текст промпта
            
        Examples:
            >>> prompt = prompt_manager.load_prompt("analyze_text.j2", 
            ...     text="Sample text", 
            ...     max_tokens=100
            ... )
        """
        if not self._env:
            raise RuntimeError("No prompt directories added. Use add_prompt_dir() first.")
            
        try:
            template = self._env.get_template(template_name)
            return template.render(**kwargs)
        except Exception as e:
            print(f"Error loading prompt template {template_name}: {e}")
            return ""
            
    def register_filter(self, name: str, filter_func: callable):
        """
        Регистрирует новый фильтр для шаблонов
        
        Args:
            name: Имя фильтра
            filter_func: Функция фильтра
            
        Examples:
            >>> def uppercase(text: str) -> str:
            ...     return text.upper()
            >>> prompt_manager.register_filter('upper', uppercase)
            >>> # Теперь в шаблоне можно использовать: {{ text | upper }}
        """
        if not self._env:
            raise RuntimeError("No prompt directories added. Use add_prompt_dir() first.")
        self._env.filters[name] = filter_func


# Создаем глобальный экземпляр менеджера
prompt_manager = PromptManager()

# Добавляем стандартную директорию промптов из пакета
package_prompts = os.path.join(Path(__file__).parent.parent, "prompts")
if os.path.exists(package_prompts):
    prompt_manager.add_prompt_dir(package_prompts)

# Для обратной совместимости
def load_prompt(template_name: str, **kwargs) -> str:
    return prompt_manager.load_prompt(template_name, **kwargs)

def register_prompt_filter(name: str, filter_func: callable):
    prompt_manager.register_filter(name, filter_func) 