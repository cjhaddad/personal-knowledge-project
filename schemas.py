from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class TokenRefresh(BaseModel):
    refresh_token: str

class TokenData(BaseModel):
    email: Optional[str] = None

class DocumentResponse(BaseModel):
    id: int
    title: str
    filename: str
    file_size: int
    mime_type: str
    processed: bool
    created_at: datetime

    class Config:
        orm_mode = True

class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int