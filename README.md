# Patrol - AI-Powered Error Analysis System

**Patrol**은 실시간으로 들어오는 오류 로그를 분석하여 근본 원인을 파악하고 해결책을 제시하는 **순수 Python 기반 FaaS(Function as a Service)** 시스템입니다. AWS Lambda, Google Cloud Functions 등 서버리스 환경에 직접 배포 가능하도록 설계되었으며, OpenAI GPT와 GitHub API를 활용하여 정확한 오류 분석을 제공합니다.

## 🎯 핵심 기능

### 1. **실시간 오류 분석**
- Sink를 통해 오류 로그 이벤트를 실시간으로 수신
- SHA-256 기반 오류 해싱으로 중복 오류 자동 감지
- OpenAI GPT를 활용한 지능형 오류 분석

### 2. **비용 최적화**
- **In-Memory 캐싱**: 동일 오류는 캐시에서 즉시 조회
- **중복 제거**: 해시 기반 오류 지문화로 불필요한 LLM 호출 제거
- **MaxQueue 설정**: 캐시 크기 제한으로 메모리 효율화
- **LRU/FIFO 정책**: 자동 eviction으로 메모리 관리

### 3. **코드 기반 분석**
- GitHub API를 통한 실시간 코드 접근
- 오류 발생 위치의 소스 코드 자동 추출
- 코드 컨텍스트를 포함한 정확한 오류 분석

### 4. **Lambda 완전 이식 가능**
- 순수 함수형 Python 코드
- 외부 의존성 최소화
- 환경변수 기반 설정
- SQS, SNS, EventBridge 트리거 지원

## 📦 프로젝트 구조

```
patrol/
├── README.md                    # 이 파일
├── requirements.txt             # Python 의존성
├── types.py                     # 타입 정의
├── hashing.py                   # 오류 해싱 및 정규화
├── cache.py                     # In-Memory 캐시 (MaxQueue)
├── engine.py                    # 핵심 분석 엔진
├── openai_provider.py           # OpenAI LLM 통합
├── github_provider.py           # GitHub 코드 접근
├── lambda_handler.py            # Lambda 핸들러
└── test_engine.py               # 단위 테스트
```

## 🚀 빠른 시작

### 1. 설치

```bash
# 저장소 클론
git clone https://github.com/cheeze-lee/patrol.git
cd patrol

# Python 의존성 설치
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
# .env 파일 생성
cat > .env << EOF
# 캐시 설정
CACHE_MAX_SIZE=1000
CACHE_EVICTION_POLICY=LRU
CACHE_TTL=86400

# OpenAI 설정 (모델은 자유롭게 선택)
OPENAI_API_KEY=sk_your_api_key_here
OPENAI_MODEL=gpt-4

# GitHub 설정
GITHUB_TOKEN=ghp_your_token_here
EOF

# 환경변수 로드
export $(cat .env | xargs)
```

### 3. 로컬 테스트

```bash
# 단위 테스트 실행
python -m pytest test_engine.py -v

# Lambda 핸들러 로컬 테스트
python lambda_handler.py
```

### 4. Lambda로 배포

```bash
# 배포 패키지 생성
mkdir lambda-package
cp *.py lambda-package/
cp requirements.txt lambda-package/
cd lambda-package
pip install -r requirements.txt -t .
zip -r ../patrol-lambda.zip .

# AWS Lambda에 배포
aws lambda create-function \
  --function-name patrol-error-analyzer \
  --runtime python3.11 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-execution-role \
  --handler lambda_handler.handler \
  --zip-file fileb://patrol-lambda.zip \
  --timeout 60 \
  --memory-size 512 \
  --environment Variables={\
OPENAI_API_KEY=sk_...,\
OPENAI_MODEL=gpt-4,\
GITHUB_TOKEN=ghp_...,\
CACHE_MAX_SIZE=1000,\
CACHE_EVICTION_POLICY=LRU,\
CACHE_TTL=86400\
}
```

## 🔑 환경변수 상세 설명

### 캐시 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CACHE_MAX_SIZE` | 1000 | 캐시에 저장할 최대 오류 분석 결과 수 |
| `CACHE_EVICTION_POLICY` | LRU | 캐시 초과 시 제거 정책 (LRU: 최근 사용 제거, FIFO: 먼저 들어온 것 제거) |
| `CACHE_TTL` | 86400 | 캐시 항목 유효 기간 (초, 기본값: 24시간) |

### OpenAI 설정

| 변수 | 필수 | 설명 |
|------|------|------|
| `OPENAI_API_KEY` | ✅ | [OpenAI API 키](https://platform.openai.com/api-keys) |
| `OPENAI_MODEL` | ❌ | 사용할 모델명 (예: gpt-4, gpt-3.5-turbo) |

### GitHub 설정

| 변수 | 필수 | 설명 |
|------|------|------|
| `GITHUB_TOKEN` | ✅ | [GitHub Personal Access Token](https://github.com/settings/tokens) (repo 권한 필요) |

## 💡 사용 예제

### 1. 오류 로그 분석 (직접 호출)

```python
from types import ErrorLog, ErrorLogEvent
from engine import ErrorAnalysisEngine
from cache import InMemoryCache
from openai_provider import OpenAILLMProvider
from github_provider import GitHubRepositoryCodeProvider

# 엔진 초기화
cache = InMemoryCache(max_size=1000, eviction_policy='LRU')
llm = OpenAILLMProvider()
code_provider = GitHubRepositoryCodeProvider()
engine = ErrorAnalysisEngine(cache, llm, code_provider)

# 오류 로그 생성
error_log = ErrorLog(
    message='TypeError: Cannot read property of undefined',
    code='ERR_UNDEFINED_PROPERTY',
    file_path='src/handlers/user.ts',
    line_number=45,
    stack_trace='at getUserById (src/handlers/user.ts:45:15)',
)

event = ErrorLogEvent(
    event_id='error-123',
    timestamp=int(__import__('time').time() * 1000),
    error_log=error_log,
    repository_url='https://github.com/your-org/your-repo',
)

# 오류 분석
result = engine.process_error_log(event)

print(f"Root Cause: {result.root_cause}")
print(f"Suggested Fix: {result.suggested_fix}")
print(f"Confidence: {result.confidence_score}%")
```

### 2. Lambda 핸들러 (SQS 이벤트)

```python
from lambda_handler import handler

# SQS 이벤트
event = {
    'Records': [
        {
            'body': json.dumps({
                'eventId': 'error-456',
                'timestamp': int(time.time() * 1000),
                'errorLog': {
                    'message': 'Database connection timeout',
                    'filePath': 'src/db/connection.ts',
                },
                'repositoryUrl': 'https://github.com/your-org/your-repo',
            }),
        },
    ],
}

response = handler(event, None)
print(json.dumps(response, indent=2))
```

### 3. 배치 처리

```python
# 여러 오류 로그 한 번에 처리
events = [
    ErrorLogEvent(...),
    ErrorLogEvent(...),
    ErrorLogEvent(...),
]

results = engine.process_error_batch(events)

for result in results:
    if result:
        print(f"Analyzed: {result.error_hash[:8]}...")
```

## 📊 성능 특성

### 캐시 효율성

| 시나리오 | 캐시 히트율 | 평균 응답 시간 |
|---------|-----------|-------------|
| 동일 오류 반복 | 95%+ | 50ms |
| 유사 오류 | 60-80% | 2-3초 |
| 새로운 오류 | 0% | 5-10초 |

### 비용 절감

```
월 1,000,000 요청 기준:

캐시 없음:
- LLM 호출: 1,000,000회
- 비용: $10,000/월

캐시 적용 (80% 히트율):
- LLM 호출: 200,000회
- 비용: $2,000/월

절감액: $8,000/월 (80% 절감)
```

## 🧪 테스트

```bash
# 모든 테스트 실행
python -m pytest test_engine.py -v

# 특정 테스트 실행
python -m pytest test_engine.py::TestHashing::test_hash_consistency -v

# 커버리지 확인
python -m pytest test_engine.py --cov=. --cov-report=html
```

## 🔒 보안 고려사항

### 1. API 키 관리
- 환경변수로만 관리 (코드에 하드코딩 금지)
- AWS Secrets Manager 또는 HashiCorp Vault 사용 권장
- 정기적인 키 로테이션 (월 1회 이상)

### 2. GitHub 토큰 권한
```bash
# 필요한 권한
- repo (private repository access)
- read:user (user information)

# 불필요한 권한 제거
- admin (repository administration)
- workflow (GitHub Actions)
```

### 3. 데이터 보안
- 분석 결과는 24시간 후 자동 삭제
- 민감 정보(API 키, 토큰)는 로그에서 제외
- HTTPS를 통한 모든 외부 통신

## 📈 모니터링 및 로깅

### CloudWatch 로그 확인

```bash
# 최근 로그 확인
aws logs tail /aws/lambda/patrol-error-analyzer --follow

# 캐시 히트율 확인
aws logs filter-log-events \
  --log-group-name /aws/lambda/patrol-error-analyzer \
  --filter-pattern "Cache hit"

# 오류 검색
aws logs filter-log-events \
  --log-group-name /aws/lambda/patrol-error-analyzer \
  --filter-pattern "ERROR"
```

### Lambda 메트릭

```bash
# 호출 횟수
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=patrol-error-analyzer

# 평균 실행 시간
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=patrol-error-analyzer

# 에러율
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=patrol-error-analyzer
```

## 🤝 기여 가이드

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 라이선스

MIT License - 자세한 내용은 [LICENSE](LICENSE) 파일 참고

## 📞 지원 및 문의

- **Issues**: [GitHub Issues](https://github.com/cheeze-lee/patrol/issues)
- **Discussions**: [GitHub Discussions](https://github.com/cheeze-lee/patrol/discussions)

## 🗺️ 로드맵

### v1.1 (예정)
- [ ] Webhook 발송 기능 (Slack, Discord, Teams)
- [ ] 오류 분석 히스토리 및 통계
- [ ] 다중 언어 지원 (Go, Java, Rust)

### v1.2 (예정)
- [ ] 실시간 대시보드
- [ ] 팀 협업 기능
- [ ] 커스텀 분석 규칙

### v2.0 (예정)
- [ ] 머신러닝 기반 오류 예측
- [ ] 자동 패치 생성
- [ ] IDE 플러그인

## 📚 추가 자료

- [AWS Lambda 개발자 가이드](https://docs.aws.amazon.com/lambda/)
- [OpenAI API 문서](https://platform.openai.com/docs/)
- [GitHub API 문서](https://docs.github.com/en/rest)

---

**Patrol**과 함께 오류 분석을 자동화하고 개발 생산성을 높이세요! 🚀
