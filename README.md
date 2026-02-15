# Patrol - AI-Powered Error Analysis System

English | [한국어](README.ko.md)

Patrol is a pure-Python, serverless-friendly error analysis system. It ingests error logs (including OTEL logs), deduplicates them via hashing + caching, pulls relevant code from a target GitHub repository, and asks an OpenAI model to produce a root-cause analysis and suggested fix.

## Key Features

- Real-time error analysis from sinks (OTEL/Vector) and common AWS event sources (SQS/SNS/EventBridge/direct)
- Target repository setup
  - Per-event: `repositoryUrl`
  - Fallback: `DEFAULT_REPOSITORY_URL`
- Code-aware analysis
  - Extracts file/line from `filePath` and `stackTrace`
  - Fetches code snippets from GitHub and analyzes logs + code together
  - If `errorLog.context` contains `git.commit.sha` or `vcs.ref.head.revision`, Patrol will try fetching code at that ref
- Cost optimization
  - SHA-256 error fingerprinting for dedupe
  - In-memory cache with TTL and LRU/FIFO eviction

## Project Layout

```
patrol/
├── README.md                    # English (default)
├── README.ko.md                 # 한국어
├── requirements.txt             # Python dependencies
├── patrol_types.py              # Type definitions
├── hashing.py                   # Error hashing + normalization
├── cache.py                     # In-memory cache
├── engine.py                    # Analysis engine
├── openai_provider.py           # OpenAI provider
├── github_provider.py           # GitHub code provider
├── otel_parser.py               # OTEL log parser
├── lambda_handler.py            # AWS Lambda handler
├── test_engine.py               # Unit tests (unittest)
└── test_otel_parser.py          # OTEL parser tests (unittest)
```

## Quick Start

### 1. Install

```bash
git clone https://github.com/cheeze-lee/patrol.git
cd patrol

pip install -r requirements.txt
```

### 2. Environment Variables

```bash
cat > .env << ENV_EOF
# Cache
CACHE_MAX_SIZE=1000
CACHE_EVICTION_POLICY=LRU
CACHE_TTL=86400

# OpenAI
OPENAI_API_KEY=sk_your_api_key_here
OPENAI_MODEL=gpt-4
OPENAI_ORG_ID=org_your_org_id_here
OPENAI_BASE_URL=https://api.openai.com/v1

# GitHub (required for private repos, recommended for public repos)
GITHUB_TOKEN=ghp_your_token_here

# Target repo fallback (optional)
DEFAULT_REPOSITORY_URL=https://github.com/your-org/your-repo

# Multi-service repo routing (optional)
# Map OTEL `service.name` -> repository URL
REPOSITORY_URL_MAP={"service-a":"https://github.com/your-org/repo-a","service-b":"https://github.com/your-org/repo-b"}

# Code context extraction (optional)
CODE_CONTEXT_LINES=20
MAX_CODE_LOCATIONS=4
MAX_REPOSITORY_CONTEXT_CHARS=12000
ENV_EOF

export $(cat .env | xargs)
```

### 3. Run Tests (Local)

```bash
python3 test_engine.py
python3 test_otel_parser.py
```

### 4. Local Lambda Handler Test

```bash
python3 lambda_handler.py
```

## Environment Variables Reference

### Cache

| Name | Default | Notes |
|------|---------|-------|
| `CACHE_MAX_SIZE` | `1000` | Max number of cached analysis results |
| `CACHE_EVICTION_POLICY` | `LRU` | `LRU` or `FIFO` |
| `CACHE_TTL` | `86400` | Seconds |

### OpenAI

| Name | Required | Notes |
|------|----------|-------|
| `OPENAI_API_KEY` | Yes | API key for OpenAI |
| `OPENAI_MODEL` | No | Defaults to `gpt-4` |
| `OPENAI_ORG_ID` | No | Organization id (optional) |
| `OPENAI_BASE_URL` | No | Custom base URL (optional) |

### GitHub

| Name | Required | Notes |
|------|----------|-------|
| `GITHUB_TOKEN` | Private repos only | Recommended even for public repos due to rate limits |

### Target Repo / Code Context

| Name | Default | Notes |
|------|---------|-------|
| `DEFAULT_REPOSITORY_URL` | (none) | Used when the incoming event does not include `repositoryUrl` |
| `REPOSITORY_URL_MAP` | (none) | JSON object mapping OTEL `service.name` to a repository URL |
| `CODE_CONTEXT_LINES` | `20` | Lines of context before/after the failing line |
| `MAX_CODE_LOCATIONS` | `4` | Max file locations extracted from log/stack |
| `MAX_REPOSITORY_CONTEXT_CHARS` | `12000` | Hard cap on context size passed to the LLM |

## Usage Example (Direct Call)

```python
from patrol_types import ErrorLog, ErrorLogEvent
from engine import ErrorAnalysisEngine

engine = ErrorAnalysisEngine()

error_log = ErrorLog(
    message="TypeError: Cannot read property of undefined",
    code="TypeError",
    file_path="src/handlers/user.ts",
    line_number=45,
    stack_trace="at getUserById (src/handlers/user.ts:45:15)",
)

event = ErrorLogEvent(
    event_id="error-123",
    timestamp=0,
    error_log=error_log,
    repository_url="https://github.com/your-org/your-repo",
)

result = engine.process_error_log(event)

print(result.root_cause)
print(result.suggested_fix)
print(result.confidence_score)
```

## Sink Integration (OTEL / Vector)

- Vector sink config guide: [VECTOR_SINK_CONFIG.md](VECTOR_SINK_CONFIG.md) (Korean)
- If you can, include the repository URL in OTEL resource attributes as `git.repository.url`.
- If you cannot, set `DEFAULT_REPOSITORY_URL` and omit `repositoryUrl` from events.
- For multi-service sinks, set `REPOSITORY_URL_MAP` to route by OTEL `service.name`.
