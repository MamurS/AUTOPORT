import os

IMPORTS = '''from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import selectinload, joinedload

'''

crud_files = ['crud/emergency_crud.py', 'crud/messaging_crud.py', 'crud/negotiations_crud.py', 
              'crud/notifications_crud.py', 'crud/ratings_crud.py', 'crud/preferences_crud.py']

for file_path in crud_files:
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            content = f.read()
        if 'from fastapi import' not in content:
            with open(file_path, 'w') as f:
                f.write(IMPORTS + content)
            print(f"Fixed {file_path}")