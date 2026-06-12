# Quick Start Guide

## Prerequisites Check

Before starting, ensure you have:
- [ ] Python 3.11 or higher (`python3 --version`)
- [ ] Node.js 18 or higher (`node --version`)
- [ ] Docker and Docker Compose (`docker --version`)
- [ ] PostgreSQL 15+ (or use Docker)
- [ ] Redis 7+ (or use Docker)

## Option 1: Docker Compose (Recommended for Quick Start)

This is the fastest way to get the entire application running.

```bash
# 1. Navigate to project directory
cd /mnt/d/workspace/ChatApplication/project-code

# 2. Configure environment variables
cp backend/.env.example backend/.env
# Edit backend/.env and add your OpenAI API key and other credentials

# 3. Start all services
docker-compose up --build

# 4. Access the application
# - Frontend: http://localhost:3000
# - Backend API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

## Option 2: Manual Setup (For Development)

### Backend Setup

```bash
# 1. Navigate to backend directory
cd /mnt/d/workspace/ChatApplication/project-code/backend

# 2. Create virtual environment
python3.11 -m venv venv

# 3. Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 4. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 5. Configure environment
cp .env.example .env
# Edit .env and add your credentials:
# - OPENAI_API_KEY
# - SECRET_KEY (generate with: openssl rand -hex 32)
# - DATABASE_URL (if using local PostgreSQL)
# - REDIS_URL (if using local Redis)

# 6. Run database migrations (ensure PostgreSQL is running)
alembic upgrade head

# 7. Start the backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
# 1. Open a new terminal and navigate to frontend directory
cd /mnt/d/workspace/ChatApplication/project-code/frontend

# 2. Install dependencies
npm install

# 3. Configure environment (optional)
cp .env.example .env

# 4. Start the development server
npm run dev

# 5. Access the application at http://localhost:3000
```

## Environment Variables Setup

### Required Backend Variables

Edit `backend/.env`:

```env
# OpenAI (REQUIRED)
OPENAI_API_KEY=sk-your-openai-api-key-here

# Security (REQUIRED)
SECRET_KEY=your-secret-key-here  # Generate: openssl rand -hex 32

# Database (if not using Docker)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/genai_kb

# Redis (if not using Docker)
REDIS_URL=redis://localhost:6379/0
```

### Optional Integration Variables

```env
# Confluence
CONFLUENCE_URL=https://your-domain.atlassian.net/wiki
CONFLUENCE_USERNAME=your-email@example.com
CONFLUENCE_API_TOKEN=your-confluence-api-token

# Jira
JIRA_URL=https://your-domain.atlassian.net
JIRA_USERNAME=your-email@example.com
JIRA_API_TOKEN=your-jira-api-token
```

## Verification Steps

### 1. Check Backend Health

```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy","environment":"development"}
```

### 2. Check API Documentation

Open in browser: http://localhost:8000/docs

### 3. Check Frontend

Open in browser: http://localhost:3000

## Common Issues and Solutions

### Issue: ModuleNotFoundError
**Solution**: Ensure virtual environment is activated and dependencies are installed:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Issue: Database connection error
**Solution**: Ensure PostgreSQL is running and credentials in `.env` are correct:
```bash
# If using Docker
docker-compose up postgres

# If using local PostgreSQL
sudo service postgresql start  # Linux
brew services start postgresql  # macOS
```

### Issue: Redis connection error
**Solution**: Ensure Redis is running:
```bash
# If using Docker
docker-compose up redis

# If using local Redis
redis-server
```

### Issue: Port already in use
**Solution**: Change the port in configuration or kill the process using the port:
```bash
# Find process using port 8000
lsof -i :8000
# Kill the process
kill -9 <PID>
```

## Next Steps

1. ✅ Environment is now running
2. 📝 Review the task breakdown in the artifacts folder
3. 🚀 Start implementing features according to the tasks
4. 🧪 Write tests for implemented features
5. 📚 Update documentation as needed

## Useful Commands

### Backend

```bash
# Run tests
pytest

# Format code
black app/

# Lint code
flake8 app/

# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

### Frontend

```bash
# Run linter
npm run lint

# Format code
npm run format

# Type check
npm run type-check

# Build for production
npm run build
```

## Support

For issues or questions, refer to:
- Setup log: `/mnt/d/workspace/ChatApplication/artifacts/setup/setup-log.md`
- README: `/mnt/d/workspace/ChatApplication/project-code/README.md`
- API Documentation: http://localhost:8000/docs (when running)
