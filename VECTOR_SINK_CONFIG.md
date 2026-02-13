# Vector Sink to Patrol Lambda Configuration Guide

이 가이드는 Vector의 Sink에서 OTEL 로그를 수집하여 Patrol Lambda로 전송하는 방법을 설명합니다.

## 아키텍처

```
┌──────────────────┐
│  Application     │
│  (with OTEL SDK) │
└────────┬─────────┘
         │
         │ OTEL Logs
         ▼
┌──────────────────────┐
│  Vector             │
│  (OTEL Receiver)    │
└────────┬─────────────┘
         │
         │ HTTP POST
         ▼
┌──────────────────────┐
│  AWS API Gateway    │
└────────┬─────────────┘
         │
         │ Lambda Invoke
         ▼
┌──────────────────────┐
│  Patrol Lambda       │
│  (Error Analyzer)    │
└────────┬─────────────┘
         │
         │ Analysis Result
         ▼
┌──────────────────────┐
│  CloudWatch Logs    │
│  (Results)          │
└──────────────────────┘
```

## 1. Vector 설정

### 1.1 Vector 설치

```bash
# macOS
brew install vector

# Linux
curl --proto '=https' --tlsv1.2 -sSfL https://sh.vector.dev | sh

# Docker
docker pull timberio/vector:latest
```

### 1.2 Vector 설정 파일 (vector.toml)

```toml
# OTEL Receiver - 애플리케이션에서 OTEL 로그 수신
[sources.otel_receiver]
type = "opentelemetry"
address = "0.0.0.0:4317"  # gRPC
protocol = "grpc"

# 또는 HTTP 프로토콜 사용
[sources.otel_http]
type = "opentelemetry"
address = "0.0.0.0:4318"  # HTTP
protocol = "http"

# 로그 필터링 (ERROR 레벨만)
[transforms.filter_errors]
type = "filter"
inputs = ["otel_receiver"]
condition = '.severity_text == "ERROR"'

# Patrol Lambda로 전송
[sinks.patrol_lambda]
type = "http"
inputs = ["filter_errors"]
uri = "https://YOUR_API_GATEWAY_URL/patrol"
method = "post"
encoding.codec = "json"

# 배치 설정
[sinks.patrol_lambda.buffer]
type = "memory"
max_events = 100
timeout_secs = 5

# 재시도 설정
[sinks.patrol_lambda.retry]
enabled = true
attempts = 3
backoff.type = "exponential"
backoff.base = 2
backoff.max_secs = 300
```

### 1.3 Vector 실행

```bash
# 설정 파일 검증
vector validate vector.toml

# Vector 시작
vector --config vector.toml

# 또는 Docker로 실행
docker run -v $(pwd)/vector.toml:/etc/vector/vector.toml timberio/vector:latest
```

## 2. AWS Lambda 설정

### 2.1 Lambda 함수 생성

```bash
# 배포 패키지 생성
mkdir lambda-package
cp *.py lambda-package/
cp requirements.txt lambda-package/
cd lambda-package
pip install -r requirements.txt -t .
zip -r ../patrol-lambda.zip .

# Lambda 함수 생성
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
GITHUB_TOKEN=ghp_...,\
CACHE_MAX_SIZE=1000,\
CACHE_EVICTION_POLICY=LRU,\
CACHE_TTL=86400\
}
```

### 2.2 API Gateway 설정

```bash
# REST API 생성
aws apigateway create-rest-api \
  --name patrol-api \
  --description "Patrol Error Analysis API"

# 리소스 생성
RESOURCE_ID=$(aws apigateway get-resources \
  --rest-api-id YOUR_API_ID \
  --query 'items[0].id' \
  --output text)

aws apigateway create-resource \
  --rest-api-id YOUR_API_ID \
  --parent-id $RESOURCE_ID \
  --path-part patrol

# POST 메서드 생성
aws apigateway put-method \
  --rest-api-id YOUR_API_ID \
  --resource-id YOUR_RESOURCE_ID \
  --http-method POST \
  --authorization-type NONE

# Lambda 통합
aws apigateway put-integration \
  --rest-api-id YOUR_API_ID \
  --resource-id YOUR_RESOURCE_ID \
  --http-method POST \
  --type AWS_PROXY \
  --integration-http-method POST \
  --uri arn:aws:apigateway:region:lambda:path/2015-03-31/functions/arn:aws:lambda:region:account-id:function:patrol-error-analyzer/invocations

# 배포
aws apigateway create-deployment \
  --rest-api-id YOUR_API_ID \
  --stage-name prod
```

## 3. 애플리케이션 OTEL 설정

### 3.1 Node.js 애플리케이션

```javascript
const { NodeSDK } = require('@opentelemetry/sdk-node');
const { getNodeAutoInstrumentations } = require('@opentelemetry/auto-instrumentations-node');
const { OTLPLogExporter } = require('@opentelemetry/exporter-logs-otlp-http');
const { BatchLogRecordProcessor } = require('@opentelemetry/sdk-logs');
const { logs } = require('@opentelemetry/api-logs');

const sdk = new NodeSDK({
  instrumentations: [getNodeAutoInstrumentations()],
  logRecordProcessors: [
    new BatchLogRecordProcessor(
      new OTLPLogExporter({
        url: 'http://localhost:4318/v1/logs',  // Vector HTTP endpoint
      })
    ),
  ],
});

sdk.start();

// 로그 사용
const logger = logs.getLogger('my-app');
logger.emit({
  severityNumber: 17,  // ERROR
  severityText: 'ERROR',
  body: 'An error occurred',
  attributes: {
    'exception.type': 'TypeError',
    'exception.message': 'Cannot read property',
    'code.filepath': 'src/handler.ts',
    'code.lineno': 45,
  },
});
```

### 3.2 Python 애플리케이션

```python
from opentelemetry import logs
from opentelemetry.sdk.logs import LoggerProvider
from opentelemetry.sdk.logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http.log_exporter import OTLPLogExporter

# OTEL 로거 설정
otlp_exporter = OTLPLogExporter(
    endpoint="http://localhost:4318/v1/logs"
)

logger_provider = LoggerProvider()
logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(otlp_exporter)
)
logs.set_logger_provider(logger_provider)

# 로거 사용
logger = logs.get_logger(__name__)

try:
    # 어떤 작업 수행
    result = risky_operation()
except Exception as e:
    logger.emit({
        "severity_number": 17,  # ERROR
        "severity_text": "ERROR",
        "body": str(e),
        "attributes": {
            "exception.type": type(e).__name__,
            "exception.message": str(e),
            "exception.stacktrace": traceback.format_exc(),
            "code.filepath": __file__,
            "code.lineno": 45,
        },
    })
```

### 3.3 Java 애플리케이션

```java
import io.opentelemetry.api.logs.Logger;
import io.opentelemetry.api.logs.LoggerProvider;
import io.opentelemetry.sdk.logs.SdkLoggerProvider;
import io.opentelemetry.sdk.logs.export.BatchLogRecordProcessor;
import io.opentelemetry.exporter.otlp.logs.OtlpGrpcLogExporter;

// OTEL 로거 설정
OtlpGrpcLogExporter logExporter = OtlpGrpcLogExporter.builder()
    .setEndpoint("http://localhost:4317")
    .build();

SdkLoggerProvider loggerProvider = SdkLoggerProvider.builder()
    .addLogRecordProcessor(new BatchLogRecordProcessor(logExporter))
    .build();

Logger logger = loggerProvider.get("my-app");

try {
    // 어떤 작업 수행
    riskyOperation();
} catch (Exception e) {
    logger.emit(LogRecordBuilder.builder()
        .setSeverity(SeverityNumber.ERROR)
        .setBody("An error occurred")
        .setAttribute("exception.type", e.getClass().getName())
        .setAttribute("exception.message", e.getMessage())
        .setAttribute("exception.stacktrace", getStackTrace(e))
        .build());
}
```

## 4. 모니터링 및 디버깅

### 4.1 Vector 로그 확인

```bash
# Vector 로그 확인
tail -f /var/log/vector.log

# 또는 Docker 로그
docker logs -f vector-container
```

### 4.2 Lambda 로그 확인

```bash
# CloudWatch 로그 확인
aws logs tail /aws/lambda/patrol-error-analyzer --follow

# 특정 필터로 검색
aws logs filter-log-events \
  --log-group-name /aws/lambda/patrol-error-analyzer \
  --filter-pattern "OTEL"
```

### 4.3 API Gateway 로그 확인

```bash
# API Gateway 실행 로그 활성화
aws apigateway update-stage \
  --rest-api-id YOUR_API_ID \
  --stage-name prod \
  --patch-operations op=replace,path=/*/*/logging/loglevel,value=INFO
```

## 5. 성능 최적화

### 5.1 Vector 배치 설정

```toml
# 배치 크기 및 타임아웃 조정
[sinks.patrol_lambda.buffer]
type = "memory"
max_events = 100      # 한 번에 최대 100개 로그
timeout_secs = 5      # 또는 5초마다 전송
```

### 5.2 Lambda 동시성 설정

```bash
# 예약된 동시성 설정
aws lambda put-provisioned-concurrency-config \
  --function-name patrol-error-analyzer \
  --provisioned-concurrent-executions 10
```

### 5.3 캐시 최적화

```bash
# Lambda 환경변수 조정
aws lambda update-function-configuration \
  --function-name patrol-error-analyzer \
  --environment Variables={\
CACHE_MAX_SIZE=5000,\
CACHE_EVICTION_POLICY=LRU,\
CACHE_TTL=86400\
}
```

## 6. 트러블슈팅

### 문제: Vector에서 Lambda로 연결 실패

```bash
# API Gateway URL 확인
aws apigateway get-stage \
  --rest-api-id YOUR_API_ID \
  --stage-name prod

# Vector 설정에서 올바른 URL 사용
# https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/patrol
```

### 문제: OTEL 로그가 수신되지 않음

```bash
# Vector 리시버 상태 확인
curl http://localhost:8686/health

# 애플리케이션에서 OTEL 로그 전송 확인
curl -X POST http://localhost:4318/v1/logs \
  -H "Content-Type: application/json" \
  -d '{"resourceLogs": [...]}'
```

### 문제: Lambda 타임아웃

```bash
# Lambda 타임아웃 증가
aws lambda update-function-configuration \
  --function-name patrol-error-analyzer \
  --timeout 120
```

## 7. 비용 최적화

### 7.1 Vector 필터링

```toml
# 필요한 로그만 전송
[transforms.filter_errors]
type = "filter"
inputs = ["otel_receiver"]
condition = '.severity_text == "ERROR" || .severity_text == "FATAL"'
```

### 7.2 샘플링

```toml
# 일부 로그만 샘플링
[transforms.sample]
type = "sample"
inputs = ["filter_errors"]
rate = 100  # 100개 중 1개만 전송
```

### 7.3 집계

```toml
# 유사한 로그 집계
[transforms.aggregate]
type = "aggregate"
inputs = ["filter_errors"]
interval_ms = 5000
group_by = ["attributes.exception.type"]
```

## 8. 완전한 예제

### 8.1 Docker Compose로 로컬 테스트

```yaml
version: '3'

services:
  vector:
    image: timberio/vector:latest
    ports:
      - "4317:4317"  # gRPC
      - "4318:4318"  # HTTP
    volumes:
      - ./vector.toml:/etc/vector/vector.toml
    environment:
      - VECTOR_LOG=debug

  app:
    build: .
    depends_on:
      - vector
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://vector:4318
```

### 8.2 로컬 테스트

```bash
# Vector 시작
docker-compose up vector

# 다른 터미널에서 테스트 로그 전송
curl -X POST http://localhost:4318/v1/logs \
  -H "Content-Type: application/json" \
  -d @test_otel_log.json
```

---

이 가이드를 따르면 Vector에서 OTEL 로그를 수집하여 Patrol Lambda로 전송하고 자동으로 오류를 분석할 수 있습니다.
