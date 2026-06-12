# Test Suite Documentation

## Overview

This directory contains comprehensive test coverage for the ChatApplication backend, with a focus on SQLAlchemy 2.0 database models.

## Directory Structure

```
tests/
├── conftest.py                    # Shared fixtures and configuration
├── README.md                      # This file
├── TEST_VALIDATION_CHECKLIST.md  # Validation checklist
├── unit/
│   └── models/
│       ├── test_user.py          # User model tests
│       ├── test_chat.py          # ChatSession & Message tests
│       ├── test_source.py        # DataSource & SyncLog tests
│       ├── test_document.py      # Document & DocumentChunk tests
│       └── test_relationships.py # Relationship tests
└── integration/
    └── models/
        └── test_model_integration.py  # Integration tests
```

## Test Coverage

### Models Tested (7 total)
1. **User** - Authentication and user management
2. **ChatSession** - Conversation sessions
3. **Message** - Chat messages with roles
4. **DataSource** - External data source integrations
5. **SyncLog** - Synchronization tracking
6. **Document** - Knowledge base documents
7. **DocumentChunk** - Document chunks with embeddings

### Test Categories
- **Unit Tests**: Fast, isolated model tests (SQLite compatible)
- **Integration Tests**: Database integration and index verification
- **Relationship Tests**: Bidirectional relationships and cascade behavior
- **Constraint Tests**: Unique constraints, foreign keys, not null
- **Enum Tests**: All enum types (UserRole, MessageRole, SourceType, SyncStatus)
- **JSONB Tests**: Complex JSON data storage
- **Vector Tests**: pgvector embeddings (PostgreSQL only)

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Or using the test runner (checks dependencies)
./run_model_tests.sh help
```

### Running Tests

```bash
# Run all tests
pytest tests/unit/models/ tests/integration/models/ -v

# Run with coverage
pytest tests/unit/models/ -v --cov=app/models --cov-report=term-missing

# Run specific test file
pytest tests/unit/models/test_user.py -v

# Run specific test function
pytest tests/unit/models/test_user.py::test_user_creation_with_all_fields -v

# Use the test runner script (recommended)
./run_model_tests.sh all
./run_model_tests.sh unit
./run_model_tests.sh quick
```

## Database Configuration

### SQLite (Default)
```bash
# Automatic - no configuration needed
pytest tests/unit/models/ -v
```

### PostgreSQL (Recommended for full testing)
```bash
# Set environment variable
export TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/chatapp_test"

# Run tests
pytest tests/unit/models/ tests/integration/models/ -v

# Or use the test runner
./run_model_tests.sh postgres
```

### Docker PostgreSQL Setup
```bash
# Start PostgreSQL with pgvector
cd infrastructure
docker-compose up -d postgres

# Wait for database to be ready
docker-compose exec postgres pg_isready

# Run tests
cd ../backend
export TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/chatapp_test"
pytest tests/ -v
```

## Test Markers

Tests are marked with pytest markers for selective execution:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.database` - Database interaction tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.asyncio` - Async test functions
- `@pytest.mark.requires_postgres` - PostgreSQL-specific (auto-skipped on SQLite)

### Running by Marker
```bash
# Run only unit tests
pytest -m unit

# Run only database tests
pytest -m database

# Run integration tests
pytest -m integration

# Exclude PostgreSQL tests
pytest -m "not requires_postgres"
```

## Test Fixtures

### Database Fixtures (`conftest.py`)

- **`engine`**: Async SQLAlchemy engine (session scope)
- **`db_session`**: Async database session with transaction rollback (function scope)
- **`clean_db`**: Clean database session for isolated tests
- **`sample_user_data`**: Sample user data dictionary
- **`sample_session_data`**: Sample chat session data
- **`sample_message_data`**: Sample message data
- **`sample_data_source_data`**: Sample data source configuration
- **`sample_document_data`**: Sample document data
- **`sample_embedding`**: 384-dimensional vector embedding

### Using Fixtures

```python
@pytest.mark.asyncio
async def test_example(clean_db, sample_user_data):
    session = clean_db
    user = User(**sample_user_data)
    session.add(user)
    await session.commit()
    assert user.id is not None
```

## Coverage Goals

- **Overall Coverage**: >90% of model code
- **Model Coverage**: 100% of each model class
- **Relationship Coverage**: All relationships tested
- **Constraint Coverage**: All constraints verified

### Viewing Coverage

```bash
# Terminal report
pytest --cov=app/models --cov-report=term-missing

# HTML report
pytest --cov=app/models --cov-report=html
open htmlcov/index.html

# XML report (for CI/CD)
pytest --cov=app/models --cov-report=xml
```

## Continuous Integration

### GitHub Actions Example

```yaml
- name: Run Model Tests
  run: |
    cd backend
    pytest tests/unit/models/ tests/integration/models/ \
      -v \
      --cov=app/models \
      --cov-report=xml \
      --cov-fail-under=80
```

## Troubleshooting

### Common Issues

**ImportError: No module named 'pytest'**
```bash
pip install -r requirements-dev.txt
```

**Database connection errors**
```bash
# Check database is running
pg_isready -h localhost -p 5432

# Verify connection string
echo $TEST_DATABASE_URL
```

**Async warnings**
```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio
```

**Vector embedding tests fail**
```bash
# Requires PostgreSQL with pgvector
# On SQLite, these tests are automatically skipped
```

## Best Practices

1. **Always use fixtures** for database sessions
2. **Use async/await** consistently
3. **Test isolation** - Each test should be independent
4. **Clear assertions** - Make test failures obvious
5. **Descriptive names** - Test names should explain what they test
6. **Document edge cases** - Comment unusual test scenarios

## Additional Resources

- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [Test Plan](../../../artifacts/tasks/task-009/testing.md)
