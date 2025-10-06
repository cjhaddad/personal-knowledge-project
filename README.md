# Personal Knowledge API

A backend service for intelligent document management and question-answering using Retrieval-Augmented Generation (RAG). Upload documents and ask questions about their content using natural language.

## Features

- Document upload (PDF, TXT, Markdown, HTML)
- Semantic search across documents
- Natural language question answering
- User authentication with JWT
- Vector-based document retrieval
- 10MB max file size

## Tech Stack

- **Backend**: FastAPI
- **Database**: PostgreSQL, Pinecone (vector storage)
- **AI**: OpenAI API
- **Deployment**: Docker

## Installation

### Prerequisites
- Docker and Docker Compose
- OpenAI API key
- Pinecone API key

### Setup

1. Clone the repository
2. Create a `.env` file in the project root:
```
OPENAI_API_KEY=your_openai_key
PINECONE_API_KEY=your_pinecone_key
PINECONE_ENVIRONMENT=your_pinecone_environment
SECRET_KEY=your_secret_key_for_jwt
```

3. Start the application:
```bash
docker-compose up --build
```

The API will be available at `http://localhost:8000`

## Usage

### API Documentation
Interactive API docs: `http://localhost:8000/docs`

### Basic Workflow

1. **Register/Login**
   - POST `/auth/register` - Create account
   - POST `/auth/login` - Get access token

2. **Upload Documents**
   - POST `/documents/upload` - Upload a document (requires authentication)

3. **Search**
   - POST `/search` - Search across documents

4. **Ask Questions**
   - POST `/ask` - Ask questions about your documents

### Database Access

Connect to PostgreSQL:
```bash
docker-compose exec db psql -U postgres -d knowledge_api
```

Common SQL queries:
```sql
\dt                    -- List tables
SELECT * FROM users;   -- View users
SELECT * FROM documents; -- View documents
```

## Development

Stop containers:
```bash
docker-compose down
```

View logs:
```bash
docker-compose logs -f
```