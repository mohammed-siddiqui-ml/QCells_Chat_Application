# GenAI Intelligent Chat-Based Knowledge Retrieval System

A production-ready GenAI-powered chat application that enables users to query and obtain accurate, context-aware responses from multiple structured and unstructured data sources through a unified conversational interface.

## Features

- **Conversational Interface**: Natural language chat interface for querying knowledge bases
- **Multi-Source Integration**: Integrates with Confluence, Jira, and onboarding materials
- **Context-Aware Responses**: Powered by advanced GenAI models (GPT-4)
- **Semantic Search**: Vector-based similarity search for relevant information retrieval
- **Real-time Data**: Scheduled synchronization ensures latest data availability
- **Admin Dashboard**: Configure data sources, monitor usage, and manage system
- **Role-Based Access**: Separate access levels for regular users and administrators

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL 15+
- **Cache**: Redis 7+
- **AI/ML**: LangChain, OpenAI GPT-4
- **Vector Store**: ChromaDB / Pinecone
- **Background Tasks**: Celery

### Frontend
- **Framework**: React 18 with TypeScript
- **UI Library**: Material-UI (MUI)
- **State Management**: Redux Toolkit
- **Build Tool**: Vite

### Infrastructure
- **Containerization**: Docker & Docker Compose
- **Reverse Proxy**: Nginx

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- Docker & Docker Compose
- PostgreSQL 15+
- Redis 7+

## Quick Start

### 1. Clone and Setup

```bash
cd /mnt/d/workspace/ChatApplication/project-code
cp backend/.env.example backend/.env
```

### 2. Configure Environment Variables

Edit `backend/.env` and set:
- `OPENAI_API_KEY`: Your OpenAI API key
- `SECRET_KEY`: Generate a secure secret key
- `CONFLUENCE_*`: Confluence credentials (if using)
- `JIRA_*`: Jira credentials (if using)

### 3. Start with Docker Compose

```bash
docker-compose up --build
```

Access the application:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

### 4. Manual Setup (Development)

#### Backend

```bash
cd backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --port 8000
```

#### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

## Project Structure

```
project-code/
├── backend/               # Python FastAPI backend
│   ├── app/
│   │   ├── api/          # API routes
│   │   ├── core/         # Core configuration
│   │   ├── models/       # Database models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Business logic
│   │   │   ├── genai/    # GenAI integration
│   │   │   ├── integrations/  # External API integrations
│   │   │   └── ingestion/     # Data ingestion pipeline
│   │   └── db/           # Database utilities
│   ├── alembic/          # Database migrations
│   └── tests/            # Test suite
├── frontend/             # React TypeScript frontend
│   ├── src/
│   │   ├── components/   # React components
│   │   ├── pages/        # Page components
│   │   ├── store/        # Redux store
│   │   ├── services/     # API services
│   │   └── types/        # TypeScript types
│   └── public/           # Static assets
└── docker-compose.yml    # Multi-container orchestration
```

## Development

### Backend Development

```bash
cd backend
source venv/bin/activate

# Run tests
pytest

# Format code
black app/
isort app/

# Lint code
flake8 app/
mypy app/

# Create migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head
```

### Frontend Development

```bash
cd frontend

# Run linter
npm run lint

# Format code
npm run format

# Type check
npm run type-check

# Build for production
npm run build
```

## API Documentation

Interactive API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Configuration

Key configuration options in `backend/.env`:

- `OPENAI_MODEL`: GPT model to use (default: gpt-4-turbo-preview)
- `VECTOR_DB_TYPE`: chromadb or pinecone
- `INGESTION_SCHEDULE_CRON`: Data refresh schedule
- `CHUNK_SIZE`: Text chunk size for embeddings
- `SIMILARITY_THRESHOLD`: Minimum similarity score for search results

## License

Proprietary - All rights reserved

## Support

For issues and questions, contact the development team.
