# Quick Start Guide - SQLAlchemy Model Tests

**Task**: task-009 - Database Schema Testing
**5-Minute Setup & Execution**

---

## TL;DR - Run Tests Now

```bash
# 1. Install dependencies
cd project-code/backend
pip install -r requirements-dev.txt

# 2. Run all tests
./run_model_tests.sh all

# 3. View coverage
open htmlcov/index.html
```

**Expected Result**: ✅ All tests passing, >90% coverage, <10 seconds

---

## Quick Commands

### Basic Testing
```bash
# All tests with coverage
./run_model_tests.sh all

# Quick check (no coverage)
./run_model_tests.sh quick

# Only unit tests
./run_model_tests.sh unit

# Verbose output
./run_model_tests.sh verbose
```

### Specific Tests
```bash
# User model only
./run_model_tests.sh user

# Chat models only
./run_model_tests.sh chat

# Document models only
./run_model_tests.sh document

# Relationships only
./run_model_tests.sh relationships
```

### Using pytest Directly
```bash
# All model tests
pytest tests/unit/models/ tests/integration/models/ -v

# Specific file
pytest tests/unit/models/test_user.py -v

# Specific test
pytest tests/unit/models/test_user.py::test_user_creation_with_all_fields -v

# With coverage
pytest tests/unit/models/ -v --cov=app/models --cov-report=term-missing

# Stop on first failure
pytest tests/unit/models/ -v -x
```

---

## Database Options

### SQLite (Default - No Setup)
```bash
# Just run tests - SQLite is automatic
pytest tests/unit/models/ -v
```

### PostgreSQL (Recommended)
```bash
# 1. Start PostgreSQL
cd infrastructure
docker-compose up -d postgres

# 2. Set environment variable
export TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/chatapp_test"

# 3. Run tests
cd ../backend
./run_model_tests.sh postgres
```

---

## What Gets Tested

### 7 Models
- ✅ User (authentication, roles)
- ✅ ChatSession (conversations)
- ✅ Message (chat messages)
- ✅ DataSource (integrations)
- ✅ SyncLog (sync tracking)
- ✅ Document (knowledge base)
- ✅ DocumentChunk (with vectors)

### 4 Enums
- ✅ UserRole (admin, user, anonymous)
- ✅ MessageRole (user, assistant, system)
- ✅ SourceType (confluence, jira, github, onboarding)
- ✅ SyncStatus (pending, syncing, success, failed)

### Key Features
- ✅ Relationships & Cascades
- ✅ JSONB fields
- ✅ Unique constraints
- ✅ Foreign keys
- ✅ Soft deletes
- ✅ Timestamps
- ✅ Vector embeddings (PostgreSQL)
- ✅ Async operations

---

## Test Results (Expected)

```
==================== test session starts ====================
collected 25+ items

tests/unit/models/test_user.py::test_user_creation ✓
tests/unit/models/test_user.py::test_email_unique ✓
tests/unit/models/test_user.py::test_user_role_enum ✓
tests/unit/models/test_user.py::test_user_defaults ✓

tests/unit/models/test_chat.py::test_session_with_user ✓
tests/unit/models/test_chat.py::test_anonymous_session ✓
tests/unit/models/test_chat.py::test_metadata_jsonb ✓
tests/unit/models/test_chat.py::test_cascade_delete ✓
tests/unit/models/test_chat.py::test_message_roles ✓

... (16+ more tests)

==================== 25 passed in 8.42s ====================

---------- coverage: platform linux, python 3.12.3 ----------
Name                              Stmts   Miss  Cover
-----------------------------------------------------
app/models/__init__.py                4      0   100%
app/models/chat.py                   45      2    96%
app/models/document.py               42      1    98%
app/models/source.py                 50      2    96%
app/models/user.py                   35      1    97%
-----------------------------------------------------
TOTAL                               176      6    97%
```

---

## Troubleshooting

### Tests Won't Run
```bash
# Check pytest installed
python3 -c "import pytest; print('OK')"

# Install dependencies
pip install -r requirements-dev.txt
```

### Database Errors
```bash
# Check database running
pg_isready -h localhost -p 5432

# Reset to SQLite
unset TEST_DATABASE_URL
pytest tests/unit/models/ -v
```

### Import Errors
```bash
# Check working directory
pwd  # Should be in backend/

# Check PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

---

## Coverage Reports

### View HTML Report
```bash
pytest tests/unit/models/ --cov=app/models --cov-report=html
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Terminal Report
```bash
pytest tests/unit/models/ --cov=app/models --cov-report=term-missing
```

### Check Coverage Threshold
```bash
pytest tests/unit/models/ --cov=app/models --cov-fail-under=80
```

---

## Next Steps After Tests Pass

1. ✅ **Review Coverage** - Ensure >90% coverage
2. ✅ **Check HTML Report** - Look for untested code paths
3. ✅ **Add to CI/CD** - Integrate into pipeline
4. ✅ **Set Pre-commit Hook** - Run tests before commits
5. ✅ **Monitor Performance** - Tests should be <30 seconds

---

## Need Help?

- 📖 **Full Docs**: See `tests/README.md`
- ✅ **Validation**: See `tests/TEST_VALIDATION_CHECKLIST.md`
- 📊 **Status**: See `tests/EXECUTION_STATUS.md`
- 📋 **Test Plan**: See `artifacts/tasks/task-009/testing.md`

---

**Quick Start Complete!** 🎉

Now run: `./run_model_tests.sh all`
