# 01 — Least-Privilege AWS IAM Policy Generator

## What It Does
Converts plain-English permission requests into **valid, least-privilege AWS IAM Policy JSON**, then runs a built-in **Security Linter** to catch dangerous wildcards (`*` or `service:*`) and missing required fields (`Version`, `Statement`).

## How It Works (Teaching Points)
1. **Strict Prompting (`temperature=0.0`):** Forces `qwen2.5-coder:3b` to output raw JSON without markdown backticks.
2. **Defensive Parsing:** `clean_json_response()` strips accidental wrapper text before `json.loads()` validates syntax.
3. **Deterministic Security Linter:** Never trust an LLM blindly—Python code explicitly audits every `Statement` for wildcard `Action` or `Resource` values.

## Usage
```bash
# Via global PG-AI router
pg-ai "create an IAM policy to read and write objects in s3 bucket pg-ai-backups"

# Standalone (with file export)
python3 projects/01_iam_generator/iam_generator.py "read-only access to dynamodb table orders" -o policy.json
```
