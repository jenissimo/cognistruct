from typing import Any, Dict, List

from llm.interfaces import ToolSchema


def convert_tool_schema(tools: List[ToolSchema]) -> List[Dict[str, Any]]:
    """
    Конвертирует схемы инструментов в формат OpenAI
    
    Args:
        tools: Список схем инструментов
        
    Returns:
        Список инструментов в формате OpenAI
    """
    openai_tools = []
    for tool in tools:
        # Собираем параметры
        properties = {}
        required = []
        for param in tool.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description
            }
            if param.required:
                required.append(param.name)

        # Формируем схему функции
        function_definition = {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }

        # Оборачиваем функцию в структуру с "type": "function"
        openai_tools.append({
            "type": "function",
            "function": function_definition
        })

    return openai_tools 