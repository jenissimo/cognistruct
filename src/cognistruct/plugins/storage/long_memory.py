async def rag_hook(self, message: IOMessage) -> Optional[Dict[str, str]]:
    """Получает релевантные воспоминания для контекста"""
    if not isinstance(message, IOMessage) or "user_id" not in message.metadata:
        return None
        
    user_id = message.metadata["user_id"]
    query = message.content
    
    # Получаем релевантные воспоминания для пользователя
    memories = await self.db.search_memories(
        user_id=user_id,
        query=query,
        limit=self.max_context_memories
    )
    
    if not memories:
        return None
        
    # Форматируем воспоминания в контекст
    context = {}
    for memory in memories:
        context[f"memory_{memory.id}"] = memory.content
        
    return context 