import os
import magic
from typing import  List
from PyPDF2 import PdfReader
from bs4 import BeautifulSoup
from fastapi import HTTPException
import tempfile

# Allowed file types
ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.md', '.html', '.htm'}
ALLOWED_MIME_TYPES = {
    'application/pdf',
    'text/plain',
    'text/markdown',
    'text/x-markdown',
    'text/html',
    'application/xhtml+xml'
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def validate_file_type(filename: str, content: bytes) -> str:
    """Validate file type and return MIME type"""
    # Check file extension
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Supported types: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Check MIME type using python-magic
    try:
        mime_type = magic.from_buffer(content, mime=True)
        if mime_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"File MIME type not allowed: {mime_type}"
            )
        return mime_type
    except Exception:
        # Fallback to extension-based detection
        if file_ext == '.pdf':
            return 'application/pdf'
        elif file_ext in ['.txt', '.md']:
            return 'text/plain'
        elif file_ext in ['.html', '.htm']:
            return 'text/html'
        else:
            raise HTTPException(status_code=400, detail="Could not determine file type")

def validate_file_size(content: bytes) -> int:
    """Validate file size"""
    file_size = len(content)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
        )
    return file_size

async def extract_text_from_file(content: bytes, mime_type: str, filename: str) -> str:
    """Extract text content from uploaded file"""
    try:
        if mime_type == 'application/pdf':
            return await extract_text_from_pdf(content)
        elif mime_type in ['text/plain', 'text/markdown']:
            return content.decode('utf-8')
        elif mime_type in ['text/html', 'application/xhtml+xml']:
            return extract_text_from_html(content)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type for text extraction")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File encoding not supported. Please use UTF-8.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

async def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF file"""
    try:
        # Create temporary file for PyPDF2
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        try:
            # Extract text using PyPDF2
            with open(tmp_file_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                text_content = []

                for page_num, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    if page_text.strip():
                        text_content.append(f"--- Page {page_num + 1} ---\n{page_text}")

                if not text_content:
                    raise HTTPException(
                        status_code=400,
                        detail="No text content found in PDF"
                    )

                return "\n\n".join(text_content)
        finally:
            # Clean up temporary file
            os.unlink(tmp_file_path)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error extracting text from PDF: {str(e)}"
        )

def extract_text_from_html(content: bytes) -> str:
    """Extract text from HTML file"""
    try:
        html_content = content.decode('utf-8')
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text and clean it up
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)

        if not text.strip():
            raise HTTPException(
                status_code=400,
                detail="No text content found in HTML file"
            )

        return text
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="HTML file encoding not supported. Please use UTF-8."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error extracting text from HTML: {str(e)}"
        )

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks for vector storage"""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at sentence boundaries
        if end < len(text):
            # Look for sentence endings near the chunk boundary
            for i in range(end - 100, min(end + 100, len(text))):
                if text[i] in '.!?\n':
                    end = i + 1
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start position with overlap
        start = end - overlap
        if start >= len(text):
            break

    return chunks