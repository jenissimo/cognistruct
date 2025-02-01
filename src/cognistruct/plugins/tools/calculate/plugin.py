import asyncio
from typing import Dict, Any, List, Optional
import math

from cognistruct.core import BasePlugin, PluginMetadata
from cognistruct.llm.interfaces import ToolSchema, ToolParameter
from cognistruct.core.context import RequestContext


class CalculatorPlugin(BasePlugin):
    """Плагин для выполнения математических вычислений"""
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="calculator",
            description="Выполняет математические вычисления",
            version="1.0.0",
            priority=50
        )
        
    def get_tools(self) -> List[ToolSchema]:
        return [
            ToolSchema(
                name="calculate",
                description="Выполняет математические вычисления, возвращает ответ текстом",
                parameters=[
                    ToolParameter(
                        name="expression",
                        type="string",
                        description="Математическое выражение для вычисления"
                    )
                ]
            )
        ]
        
    async def execute_tool(self, tool_name: str, params: Dict[str, Any], context: Optional['RequestContext'] = None) -> Any:
        """Выполняет инструмент калькулятора
        
        Args:
            tool_name: Имя инструмента
            params: Параметры инструмента
            context: Контекст запроса (опционально)
            
        Returns:
            Результат вычисления
            
        Raises:
            ValueError: Если инструмент не найден или выражение некорректно
        """
        if tool_name != "calculate":
            raise ValueError(f"Unknown tool: {tool_name}")
            
        expression = params.get("expression")
        if not expression:
            raise ValueError("Expression parameter is required")
            
        try:
            # Создаем безопасное окружение для eval
            safe_dict = {
                'abs': abs, 'round': round,
                'max': max, 'min': min,
                'sum': sum, 'len': len,
                'int': int, 'float': float
            }
            
            # Вычисляем выражение
            result = eval(expression, {"__builtins__": {}}, safe_dict)
            return str(result)
            
        except Exception as e:
            raise ValueError(f"Failed to evaluate expression: {str(e)}") 