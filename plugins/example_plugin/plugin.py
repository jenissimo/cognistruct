from typing import List, Dict, Any

from plugins.base_plugin import BasePlugin
from llm.interfaces import ToolSchema, ToolParameter


class CalculatorPlugin(BasePlugin):
    """Плагин для выполнения математических вычислений"""
    
    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": "calculator",
            "description": "Выполняет математические вычисления",
            "version": "1.0",
            "priority": 50
        }
        
    def get_tools(self) -> List[ToolSchema]:
        return [
            ToolSchema(
                name="calculate",
                description="Выполняет математические вычисления",
                parameters=[
                    ToolParameter(
                        name="expression",
                        type="string",
                        description="Математическое выражение для вычисления"
                    )
                ]
            )
        ]
        
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        if tool_name == "calculate":
            expression = params["expression"]
            try:
                # Создаем безопасное окружение для eval
                safe_dict = {
                    "abs": abs,
                    "float": float,
                    "int": int,
                    "max": max,
                    "min": min,
                    "pow": pow,
                    "round": round
                }
                
                # Вычисляем выражение
                result = eval(expression, {"__builtins__": {}}, safe_dict)
                return str(result)
                
            except Exception as e:
                return f"Ошибка вычисления: {str(e)}"
                
        return f"Неизвестный инструмент: {tool_name}" 