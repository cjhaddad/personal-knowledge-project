from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List
from dotenv import load_dotenv
import os

from database import get_db
from models import User, Document, DocumentChunk
from schemas import UserCreate, UserLogin, UserResponse, Token, TokenRefresh, DocumentResponse, DocumentListResponse, SearchRequest, SearchResponse, QuestionRequest, QuestionResponse
from document_processor import validate_file_type, validate_file_size, extract_text_from_file, chunk_text
from vector_store import vector_store
from rag_service import rag_service
from auth import (
    get_password_hash,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

load_dotenv()

app = FastAPI(
    title="Personal Knowledge API",
    description="A backend service for intelligent document management and question-answering",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"message": "Welcome to Personal Knowledge API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/auth/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user

@app.post("/auth/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = authenticate_user(db, user.email, user.password)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )

    # Create refresh token
    refresh_token = create_refresh_token(db, db_user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@app.post("/auth/refresh", response_model=Token)
def refresh_access_token(token_data: TokenRefresh, db: Session = Depends(get_db)):
    user = verify_refresh_token(db, token_data.refresh_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Revoke old refresh token (security: one-time use)
    revoke_refresh_token(db, token_data.refresh_token)

    # Create new access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )

    # Create new refresh token (token rotation)
    new_refresh_token = create_refresh_token(db, user.id)

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }

@app.post("/auth/logout")
def logout(token_data: TokenRefresh, db: Session = Depends(get_db)):
    success = revoke_refresh_token(db, token_data.refresh_token)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid refresh token"
        )
    return {"message": "Successfully logged out"}

@app.post("/auth/logout-all")
def logout_all(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    revoke_all_user_tokens(db, current_user.id)
    return {"message": "Successfully logged out from all devices"}

@app.get("/auth/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# Document endpoints
@app.post("/documents/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Read file content
    content = await file.read()

    # Validate file
    mime_type = validate_file_type(file.filename, content)
    file_size = validate_file_size(content)

    # Extract text content
    text_content = await extract_text_from_file(content, mime_type, file.filename)

    # Create document record
    db_document = Document(
        title=os.path.splitext(file.filename)[0],  # Remove extension for title
        filename=file.filename,
        file_path="",  # We're not storing files, just text content
        content=text_content,
        file_size=file_size,
        mime_type=mime_type,
        owner_id=current_user.id,
        processed=False
    )

    db.add(db_document)
    db.commit()
    db.refresh(db_document)

    # Create text chunks for vector storage
    chunks = chunk_text(text_content)

    # Create all chunks in database first
    chunk_objects = []
    for i, chunk_content in enumerate(chunks):
        chunk = DocumentChunk(
            content=chunk_content,
            chunk_index=i,
            document_id=db_document.id
        )
        chunk_objects.append(chunk)
        db.add(chunk)

    db.commit()  # Commit all chunks at once

    # Refresh all chunks to get their IDs
    for chunk in chunk_objects:
        db.refresh(chunk)

    # Prepare data for batch embedding processing
    chunk_data = []
    for chunk in chunk_objects:
        chunk_data.append({
            "chunk_id": chunk.id,
            "text": chunk.content,
            "document_id": db_document.id,
            "user_id": current_user.id
        })

    # Create vector embeddings in batch
    await vector_store.store_chunk_embeddings_batch(chunk_data)

    # Mark document as processed
    db_document.processed = True
    db.commit()
    db.refresh(db_document)

    return db_document

@app.get("/documents", response_model=DocumentListResponse)
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    documents = db.query(Document).filter(Document.owner_id == current_user.id).all()
    return {
        "documents": documents,
        "total": len(documents)
    }

@app.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.owner_id == current_user.id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return document

@app.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.owner_id == current_user.id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete vector embeddings
    await vector_store.delete_document_embeddings(document_id, current_user.id)

    # Delete associated chunks
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()

    # Delete document
    db.delete(document)
    db.commit()

    return {"message": "Document deleted successfully"}

@app.post("/search", response_model=SearchResponse)
async def search_documents(
    search_request: SearchRequest,
    current_user: User = Depends(get_current_user)
):
    # Perform vector search
    results = await vector_store.search_similar_chunks(
        query=search_request.query,
        user_id=current_user.id,
        top_k=search_request.top_k,
        document_ids=search_request.document_ids
    )

    return {
        "results": results,
        "query": search_request.query,
        "total": len(results)
    }

@app.post("/ask", response_model=QuestionResponse)
async def ask_question(
    question_request: QuestionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Generate answer using RAG
    result = await rag_service.generate_answer(
        question=question_request.question,
        user_id=current_user.id,
        db=db,
        document_ids=question_request.document_ids
    )

    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)