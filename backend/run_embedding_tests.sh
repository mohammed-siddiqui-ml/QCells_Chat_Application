#!/bin/bash
# Fresh subprocess to avoid NumPy reload issues
cd /mnt/d/workspace/ChatApplication/project-code/backend
source venv/bin/activate
exec python -m pytest tests/test_services/test_embedding_service.py -v --cov=app.services.genai.embedding_service --cov-report=term-missing --tb=short
