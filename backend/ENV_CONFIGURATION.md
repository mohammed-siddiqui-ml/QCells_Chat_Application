# Environment Configuration Guide

This document provides detailed information about environment configuration files for the GenAI Knowledge Retrieval System.

## Available Configuration Files

### 1. `.env.example`
- **Purpose**: Template file with all available configuration options
- **Usage**: Reference for all environment variables with detailed documentation
- **Contains**: 50+ environment variables organized by category
- **When to use**: As a starting point for creating environment-specific configurations

### 2. `.env.local`
- **Purpose**: Local development environment configuration
- **Usage**: Development and testing on local machines
- **Features**:
  - Debug mode enabled
  - Verbose logging
  - Relaxed security settings
  - Ollama enabled for local LLM testing
  - Lower performance thresholds
  - Rate limiting disabled
- **When to use**: Daily development work, debugging, local testing

### 3. `.env.staging`
- **Purpose**: Staging/QA environment configuration
- **Usage**: Pre-production testing and quality assurance
- **Features**:
  - Production-like settings
  - Moderate security
  - Full logging enabled
  - Integration with staging external services
  - Sentry error tracking
- **When to use**: QA testing, integration testing, UAT

### 4. `.env.production`
- **Purpose**: Production environment configuration
- **Usage**: Live production deployment
- **Features**:
  - Maximum security settings
  - Optimized performance
  - SSL/TLS enforced
  - Comprehensive monitoring
  - Strict rate limiting
  - Error tracking with sampling
- **When to use**: Production deployments only

## Configuration Categories

### Application Settings
- Application name, version, and environment
- Debug mode and log level

### Server Configuration
- Host, port, and worker processes
- Request timeout settings

### Database Configuration (PostgreSQL)
- Connection URL with credentials
- Connection pool settings
- Timeout and performance tuning

### Redis Configuration
- Connection URL and database indices
- Pool size and timeout settings

### Elasticsearch Configuration (Optional)
- Connection details and authentication
- Index configuration
- SSL settings

### Security & Authentication
- JWT secret key and algorithm
- Token expiration settings
- Password hashing configuration

### OAuth2 Configuration
- OAuth2 provider settings
- Client credentials
- Endpoints and scopes

### LLM Configuration
- **OpenAI**: API keys, models, and parameters
- **Ollama**: Local LLM alternative configuration

### Vector Database Configuration
- ChromaDB or Pinecone settings
- Embedding dimensions and collection names

### External API Integrations
- **Confluence**: URL, credentials, and ingestion settings
- **Jira**: URL, credentials, and project configuration

### Data Ingestion Settings
- Scheduled ingestion cron expressions
- Batch sizes and retry logic

### Rate Limiting
- Per-minute limits for different user types
- Burst capacity configuration

### CORS Settings
- Allowed origins and methods
- Credential handling

### Logging Configuration
- Log format (JSON/text)
- File paths and rotation settings

### Monitoring & Observability
- Prometheus metrics
- Health check endpoints
- Sentry error tracking

### Celery (Background Tasks)
- Broker and result backend URLs
- Task limits and concurrency

### Performance Tuning
- Chunk sizes for text processing
- Search thresholds and limits
- Cache TTL settings

### Feature Flags
- Enable/disable specific features
- A/B testing capabilities

## Setup Instructions

### For Local Development

1. Copy the local development template:
   ```bash
   cp .env.local .env
   ```

2. Update the following required variables:
   ```bash
   OPENAI_API_KEY=your-api-key  # Or enable Ollama
   ```

3. Start development:
   ```bash
   uvicorn app.main:app --reload
   ```

### For Staging/Production

1. Copy the appropriate template:
   ```bash
   # For staging
   cp .env.staging .env

   # For production
   cp .env.production .env
   ```

2. **CRITICAL**: Update ALL security-sensitive variables (see Security Best Practices section)

3. Update service URLs to match your infrastructure

4. Verify configuration:
   ```bash
   python -c "from app.core.config import settings; print(settings.ENVIRONMENT)"
   ```

## Security Best Practices

### Secret Management
- **Never commit `.env` files** to version control
- Use secrets management systems in production:
  - AWS Secrets Manager
  - HashiCorp Vault
  - Azure Key Vault
  - Google Secret Manager

### Credential Rotation
- Rotate secrets regularly (every 90 days minimum)
- Update API tokens when team members leave
- Monitor for leaked credentials using tools like GitGuardian

### Environment Isolation
- Use separate credentials for each environment
- Never reuse production credentials in staging/development
- Restrict production access to authorized personnel only

### Access Control
- Limit who can view/modify production configurations
- Use role-based access control (RBAC)
- Audit configuration changes

## Required Variables by Component

### Minimal Setup (Local Development)
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/genai_kb
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=dev-secret-key
OPENAI_API_KEY=sk-your-key  # OR enable OLLAMA_ENABLED=true
```

### Full Production Setup
All 50+ variables should be configured, including:
- All database connections
- All API credentials
- OAuth2 configuration
- Monitoring tools
- External service integrations

## Environment Variable Validation

The application validates required environment variables on startup. Missing critical variables will cause startup failures with clear error messages.

### To validate your configuration:
```bash
python -m app.core.config
```

## Troubleshooting

### Common Issues

**1. Database connection fails**
- Check `DATABASE_URL` format
- Verify database credentials
- Ensure PostgreSQL is running
- Check network connectivity

**2. Redis connection fails**
- Verify `REDIS_URL` is correct
- Ensure Redis is running
- Check Redis password if configured

**3. OpenAI API errors**
- Validate `OPENAI_API_KEY` is correct
- Check API quota and billing
- Verify model names are valid

**4. External API authentication fails**
- Regenerate API tokens (Confluence, Jira)
- Verify token permissions
- Check URL formats include protocol (https://)

**5. Environment not loading**
- Ensure `.env` file is in the correct directory
- Check file permissions
- Verify no syntax errors in `.env` file

## Variable Reference Table

| Category | Count | Required | Optional |
|----------|-------|----------|----------|
| Application | 5 | 5 | 0 |
| Server | 4 | 2 | 2 |
| Database | 6 | 2 | 4 |
| Redis | 5 | 1 | 4 |
| Elasticsearch | 5 | 0 | 5 |
| Security | 5 | 2 | 3 |
| Admin | 2 | 2 | 0 |
| OAuth2 | 7 | 0 | 7 |
| OpenAI | 6 | 1 | 5 |
| Ollama | 5 | 0 | 5 |
| Vector DB | 7 | 1 | 6 |
| Confluence | 6 | 0 | 6 |
| Jira | 6 | 0 | 6 |
| Ingestion | 5 | 0 | 5 |
| Rate Limiting | 5 | 0 | 5 |
| CORS | 4 | 1 | 3 |
| Logging | 6 | 2 | 4 |
| Monitoring | 8 | 0 | 8 |
| Celery | 6 | 2 | 4 |
| Performance | 6 | 0 | 6 |
| Features | 6 | 0 | 6 |
| **Total** | **110** | **21** | **89** |

## Migration from Old Configuration

If you have an existing `.env` file, compare it against `.env.example` to identify:
- New variables added
- Deprecated variables
- Changed default values

## Support

For configuration assistance:
1. Check this documentation
2. Review `.env.example` comments
3. Consult application logs
4. Contact DevOps team for production issues

## Changelog

### v1.0.0 (Current)
- Initial comprehensive configuration
- Support for 110+ environment variables
- Multi-environment templates (local, staging, production)
- Full documentation with security guidelines
   cp .env.production .env
   ```

2. **CRITICAL**: Update ALL security-sensitive variables:
   - `SECRET_KEY`
   - `ADMIN_PASSWORD`
   - `DATABASE_URL` (credentials)
   - `REDIS_URL` (password)
   - `OPENAI_API_KEY`
   - `CONFLUENCE_API_TOKEN`
   - `JIRA_API_TOKEN`
   - `OAUTH2_CLIENT_SECRET`
   - `ELASTICSEARCH_PASSWORD`
   - `PINECONE_API_KEY`
   - `SENTRY_DSN`

3. Update service URLs to match your infrastructure

4. Verify configuration:
   ```bash
   python -c "from app.core.config import settings; print(settings.ENVIRONMENT)"
   ```

## Security Best Practices

### Secret Management
- **Never commit `.env` files** to version control
- Use secrets management systems in production:
  - AWS Secrets Manager
  - HashiCorp Vault
  - Azure Key Vault
  - Google Secret Manager
