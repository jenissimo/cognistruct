from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import sqlite3
import json
import time
from pathlib import Path
import asyncio

from core import BasePlugin, PluginMetadata


@dataclass
class Project:
    """Проект в системе"""
    id: int
    user_id: int
    name: str
    description: str
    created_at: float
    updated_at: float
    metadata: Dict[str, Any]


class ProjectStoragePlugin(BasePlugin):
    """
    Плагин для управления проектами
    
    Каждый проект имеет:
    - id: уникальный числовой идентификатор
    - user_id: ID владельца проекта
    - name: название проекта
    - description: описание
    - created_at: время создания
    - updated_at: время последнего обновления
    - metadata: дополнительные метаданные (соавторы, теги и т.д.)
    """
    
    def __init__(self, db_path: str = "project_storage.db"):
        super().__init__()
        self._db: Optional[sqlite3.Connection] = None
        self.db_path = db_path
        
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="project_storage",
            description="Управление проектами",
            version="0.1.0",
            author="Cognistruct"
        )
        
    async def setup(self):
        """Инициализация БД"""
        def _setup():
            self._db = sqlite3.connect(self.db_path)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at REAL,
                    updated_at REAL,
                    metadata TEXT
                )
            """)
            self._db.commit()
            
        await asyncio.to_thread(_setup)
        
    async def cleanup(self):
        """Закрытие соединения с БД"""
        if self._db:
            self._db.close()
            
    async def create_project(self, data: Dict[str, Any]) -> Project:
        """Создание нового проекта"""
        name = data["name"]
        description = data.get("description", "")
        metadata = data.get("metadata", {})
        
        # Сохраняем проект
        timestamp = time.time()
        cursor = self._db.execute(
            "INSERT INTO projects (name, description, created_at, updated_at, metadata) VALUES (?, ?, ?, ?, ?)",
            (name, description, timestamp, timestamp, json.dumps(metadata))
        )
        self._db.commit()
        
        return Project(
            id=cursor.lastrowid,
            name=name,
            description=description,
            created_at=timestamp,
            updated_at=timestamp,
            metadata=metadata
        )
        
    async def get_project(self, project_id: int) -> Optional[Project]:
        """Получение проекта по ID"""
        cursor = self._db.execute(
            "SELECT * FROM projects WHERE id = ?",
            (project_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
            
        return Project(
            id=row[0],
            name=row[1],
            description=row[2],
            created_at=row[3],
            updated_at=row[4],
            metadata=json.loads(row[5])
        )
        
    async def update_project(self, project_id: int, data: Dict[str, Any]) -> Optional[Project]:
        """Обновление проекта"""
        project = await self.get_project(project_id)
        if not project:
            return None
            
        # Обновляем только переданные поля
        name = data.get("name", project.name)
        description = data.get("description", project.description)
        metadata = {**project.metadata, **(data.get("metadata", {}))}
        
        timestamp = time.time()
        self._db.execute("""
            UPDATE projects 
            SET name = ?, description = ?, updated_at = ?, metadata = ?
            WHERE id = ?
        """, (name, description, timestamp, json.dumps(metadata), project_id))
        self._db.commit()
        
        return Project(
            id=project_id,
            name=name,
            description=description,
            created_at=project.created_at,
            updated_at=timestamp,
            metadata=metadata
        )
        
    async def delete_project(self, project_id: int) -> bool:
        """Удаление проекта"""
        cursor = self._db.execute(
            "DELETE FROM projects WHERE id = ?",
            (project_id,)
        )
        self._db.commit()
        return cursor.rowcount > 0
        
    async def search_projects(self, query: Dict[str, Any]) -> List[Project]:
        """
        Поиск проектов
        
        Поддерживаемые параметры:
        - name_query: поиск по названию
        - tags: список тегов
        - owner_id: ID владельца
        """
        sql = "SELECT * FROM projects"
        params = []
        where_clauses = []
        
        if "name_query" in query:
            where_clauses.append("name LIKE ?")
            params.append(f"%{query['name_query']}%")
            
        if "owner_id" in query:
            where_clauses.append("json_extract(metadata, '$.owner_id') = ?")
            params.append(query["owner_id"])
            
        if "tags" in query:
            tags = query["tags"]
            if isinstance(tags, str):
                tags = [tags]
            tags_conditions = []
            for tag in tags:
                tags_conditions.append(f"json_extract(metadata, '$.tags') LIKE '%{tag}%'")
            if tags_conditions:
                where_clauses.append(f"({' OR '.join(tags_conditions)})")
                
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
            
        cursor = self._db.execute(sql, params)
        projects = []
        
        for row in cursor.fetchall():
            projects.append(Project(
                id=row[0],
                name=row[1],
                description=row[2],
                created_at=row[3],
                updated_at=row[4],
                metadata=json.loads(row[5])
            ))
            
        return projects
        
    def get_tools(self) -> List[Dict[str, Any]]:
        """Возвращает инструменты для работы с проектами"""
        return [{
            "name": "manage_project",
            "description": "Управление проектами",
            "parameters": {
                "action": {
                    "type": "string",
                    "enum": ["create", "get", "update", "delete", "search"],
                    "description": "Действие"
                },
                "project_id": {
                    "type": "integer",
                    "description": "ID проекта (для get/update/delete)"
                },
                "data": {
                    "type": "object",
                    "description": "Данные проекта (для create/update)"
                },
                "search_params": {
                    "type": "object",
                    "description": "Параметры поиска (name_query, tags, owner_id)"
                }
            }
        }]
        
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Выполняет действия с проектами"""
        if tool_name != "manage_project":
            raise NotImplementedError(f"Unknown tool: {tool_name}")
            
        action = params["action"]
        
        if action == "create":
            return await self.create_project(params["data"])
        elif action == "get":
            return await self.get_project(params["project_id"])
        elif action == "update":
            return await self.update_project(params["project_id"], params["data"])
        elif action == "delete":
            return await self.delete_project(params["project_id"])
        elif action == "search":
            return await self.search_projects(params["search_params"])
        else:
            raise ValueError(f"Unknown action: {action}") 