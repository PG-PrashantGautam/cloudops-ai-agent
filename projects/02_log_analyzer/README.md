# 02 — AWS CloudWatch Log Analyzer

## What It Does
Queries AWS CloudWatch Logs using `boto3` (`filter_log_events`), trims oversized log payloads to protect the local LLM's context window, and generates a structured **Root Cause -> Affected Component -> Remediation** incident report.

## How It Works (Teaching Points)
1. **Targeted Filtering:** Pulls only matching events (default filter: `ERROR`) over a configurable lookback window (`--hours 24`).
2. **Context-Window Guardrail:** Caps raw log text at the latest 6,000 characters so `qwen2.5-coder:3b` never gets overwhelmed by noisy stack traces.
3. **Graceful AWS Error Handling:** Explicitly catches `NoCredentialsError`, `ResourceNotFoundException`, and `AccessDeniedException`.

## Usage
```bash
# Offline demo (--mock simulates a cross-account STS AssumeRole AccessDenied error)
pg-ai "check cloudwatch error logs for payment lambda" --mock

# Live AWS CloudWatch query
python3 projects/02_log_analyzer/log_analyzer.py --log-group /aws/lambda/my-function --hours 12 --filter ERROR
```
