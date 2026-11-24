import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Allow importing from the root 'core' package regardless of where the script is run
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from core.llm_client import LLMClient

SYSTEM_PROMPT = """You are a Senior AWS CloudOps & Site Reliability Engineer.
Analyze the provided AWS CloudWatch Logs and deliver a concise, actionable incident report.

STRUCTURE YOUR RESPONSE AS:
1. **Root Cause:** Exact technical reason for the failure (cite specific error codes, ARNs, or services from the logs).
2. **Affected Component:** The IAM role, Lambda function, RDS instance, or service experiencing the issue.
3. **Remediation:** Exact AWS CLI command, IAM policy snippet, or configuration fix to resolve it.

Keep it strictly technical and concise. Do not hallucinate details not present in the logs.
"""

MOCK_LOGS = """
[2026-11-20T08:12:04Z] INFO  Starting payment-processor Lambda invocation (RequestId: 9a8f1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c)
[2026-11-20T08:12:05Z] ERROR botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling the AssumeRole operation: User: arn:aws:sts::123456789012:assumed-role/lambda-payment-exec-role/payment-processor is not authorized to perform: sts:AssumeRole on resource: arn:aws:iam::987654321098:role/cross-account-billing-reader
[2026-11-20T08:12:05Z] ERROR Failed to fetch cross-account ledger data. Retrying (1/3)...
[2026-11-20T08:12:07Z] ERROR botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling the AssumeRole operation: User: arn:aws:sts::123456789012:assumed-role/lambda-payment-exec-role/payment-processor is not authorized to perform: sts:AssumeRole on resource: arn:aws:iam::987654321098:role/cross-account-billing-reader
[2026-11-20T08:12:07Z] CRITICAL Transaction batch aborted after max retries. Exiting with status 1.
""".strip()


def fetch_cloudwatch_logs(
    log_group: str,
    hours: int = 24,
    filter_pattern: str = "ERROR",
    limit: int = 50,
    region: str = None,
) -> str:
    """Fetch filtered log events from AWS CloudWatch Logs."""
    aws_region = region or os.getenv("AWS_REGION", "us-east-1")
    client = boto3.client("logs", region_name=aws_region)

    start_time_ms = int(
        (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1000
    )

    print(
        f"[🔍] Querying CloudWatch Log Group '{log_group}' "
        f"(Region: {aws_region} | Last {hours}h | Filter: '{filter_pattern}')..."
    )

    try:
        kwargs = {
            "logGroupName": log_group,
            "startTime": start_time_ms,
            "limit": limit,
        }
        if filter_pattern:
            kwargs["filterPattern"] = filter_pattern

        response = client.filter_log_events(**kwargs)
        events = response.get("events", [])

        if not events:
            return ""

        formatted_lines = []
        for event in events:
            ts = datetime.fromtimestamp(
                event["timestamp"] / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            msg = event["message"].strip()
            formatted_lines.append(f"[{ts}] {msg}")

        return "\n".join(formatted_lines)

    except NoCredentialsError:
        print("[❌] AWS credentials not found. Run 'aws configure' or use --mock.")
        sys.exit(1)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            print(f"[❌] Log group '{log_group}' not found in region '{aws_region}'.")
        elif error_code == "AccessDeniedException":
            print(
                "[❌] IAM Access Denied. Ensure your IAM user has 'logs:FilterLogEvents' permission."
            )
        else:
            print(f"[❌] AWS CloudWatch Error: {e}")
        sys.exit(1)


def analyze_logs(log_data: str, provider: str = None):
    """Send raw logs to the unified LLM client for root cause analysis."""
    if len(log_data) > 6000:
        log_data = "...[older logs truncated]...\n" + log_data[-6000:]

    client = LLMClient(provider=provider, role="specialist")
    print(f"[🧠] Analyzing logs | Provider: {client.provider} | Model: {client.model}")

    analysis = client.generate(
        prompt=f"Analyze these AWS CloudWatch logs:\n\n{log_data}",
        system_prompt=SYSTEM_PROMPT,
        temperature=0.1,
    )

    print("\n--- 🤖 AI CloudWatch Log Analysis ---")
    print(analysis)
    print("-------------------------------------\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI-Powered AWS CloudWatch Log Analyzer"
    )
    parser.add_argument(
        "--log-group", "-g", help="AWS CloudWatch Log Group name (e.g., /aws/lambda/my-fn)"
    )
    parser.add_argument(
        "--hours", type=int, default=24, help="Lookback window in hours (default: 24)"
    )
    parser.add_argument(
        "--filter", default="ERROR", help="CloudWatch filter pattern (default: ERROR)"
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="Max log events to fetch (default: 50)"
    )
    parser.add_argument(
        "--region", default=None, help="AWS region override (defaults to AWS_REGION)"
    )
    parser.add_argument(
        "--mock", action="store_true", help="Use built-in mock error logs for offline testing"
    )
    parser.add_argument(
        "--provider", choices=["ollama", "bedrock"], default=None, help="Override LLM provider"
    )
    args = parser.parse_args()

    if args.mock:
        print("[ℹ️] Running in MOCK mode with sample AWS CloudWatch error logs...")
        logs_text = MOCK_LOGS
    else:
        log_group = args.log_group or input("Enter CloudWatch Log Group name: ").strip()
        if not log_group:
            print("Error: Provide --log-group or use --mock.")
            sys.exit(1)
        logs_text = fetch_cloudwatch_logs(
            log_group=log_group,
            hours=args.hours,
            filter_pattern=args.filter,
            limit=args.limit,
            region=args.region,
        )
        if not logs_text:
            print(
                f"[✅] No log events matched filter '{args.filter}' in the last {args.hours} hours."
            )
            sys.exit(0)

    analyze_logs(logs_text, provider=args.provider)
