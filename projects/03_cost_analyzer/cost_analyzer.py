import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Allow importing from the root 'core' package regardless of where the script is run
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from core.llm_client import LLMClient

SYSTEM_PROMPT = """You are a Principal AWS FinOps Architect.
Analyze the provided AWS daily service cost breakdown and deliver a concise, executive-ready FinOps report.

STRUCTURE YOUR RESPONSE AS:
1. **Top Cost Drivers:** Top 3 services by total spend with exact dollar amounts.
2. **Detected Anomalies:** Any sudden day-over-day spikes or unusual spend patterns (cite exact dates and % increase).
3. **Actionable Optimizations:** Concrete, AWS-native cost-reduction recommendations (e.g., S3 Gateway Endpoints vs. NAT Gateway, Spot instances, Rightsizing, Savings Plans, Log retention).

Keep the report sharp, data-driven, and strictly grounded in the numbers provided.
"""

MOCK_COST_DATA = {
    "period": "2026-11-13 to 2026-11-20",
    "currency": "USD",
    "daily_breakdown": [
        {
            "date": "2026-11-17",
            "services": {
                "Amazon Elastic Compute Cloud - Compute": 42.50,
                "Amazon Relational Database Service": 28.10,
                "EC2 - Other (NAT Gateway Data Processing)": 6.20,
                "Amazon Simple Storage Service": 4.80,
                "AWS Glue": 12.00,
            },
        },
        {
            "date": "2026-11-18",
            "services": {
                "Amazon Elastic Compute Cloud - Compute": 43.10,
                "Amazon Relational Database Service": 28.15,
                "EC2 - Other (NAT Gateway Data Processing)": 6.45,
                "Amazon Simple Storage Service": 4.90,
                "AWS Glue": 11.80,
            },
        },
        {
            "date": "2026-11-19",
            "services": {
                "Amazon Elastic Compute Cloud - Compute": 44.00,
                "Amazon Relational Database Service": 28.10,
                "EC2 - Other (NAT Gateway Data Processing)": 64.90,
                "Amazon Simple Storage Service": 5.10,
                "AWS Glue": 48.50,
            },
        },
    ],
}


def fetch_aws_costs(days: int = 7) -> dict:
    """Fetch daily unblended AWS costs grouped by SERVICE via Cost Explorer."""
    client = boto3.client("ce", region_name="us-east-1")

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)

    print(
        f"[💰] Querying AWS Cost Explorer ({start_date} to {end_date} | Granularity: DAILY)..."
    )

    try:
        response = client.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d"),
            },
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        daily_breakdown = []
        for day in response.get("ResultsByTime", []):
            date_str = day["TimePeriod"]["Start"]
            services = {}
            for group in day.get("Groups", []):
                svc_name = group["Keys"][0]
                amount = round(float(group["Metrics"]["UnblendedCost"]["Amount"]), 4)
                if amount > 0.0:
                    services[svc_name] = amount

            sorted_services = dict(
                sorted(services.items(), key=lambda x: x[1], reverse=True)
            )
            daily_breakdown.append({"date": date_str, "services": sorted_services})

        return {
            "period": f"{start_date} to {end_date}",
            "currency": "USD",
            "daily_breakdown": daily_breakdown,
        }

    except NoCredentialsError:
        print("[❌] AWS credentials not found. Run 'aws configure' or use --mock.")
        sys.exit(1)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "AccessDeniedException":
            print(
                "[❌] IAM Access Denied. Ensure your IAM user has 'ce:GetCostAndUsage' permission."
            )
        else:
            print(f"[❌] AWS Cost Explorer Error: {e}")
        sys.exit(1)


def analyze_costs(cost_data: dict, provider: str = None):
    """Send structured cost data to the unified LLM client for FinOps analysis."""
    client = LLMClient(provider=provider, role="specialist")
    print(f"[🧠] Analyzing spend | Provider: {client.provider} | Model: {client.model}")

    prompt = (
        "Analyze the following AWS daily cost breakdown (in USD) for anomalies and "
        f"optimization opportunities:\n\n{json.dumps(cost_data, indent=2)}"
    )

    report = client.generate(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        temperature=0.1,
    )

    print("\n--- 📊 AI FinOps Cost Anomaly Report ---")
    print(report)
    print("----------------------------------------\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI-Powered AWS FinOps Cost Anomaly Detector")
    parser.add_argument(
        "--days", type=int, default=7, help="Number of past days to analyze (default: 7)"
    )
    parser.add_argument(
        "--mock", action="store_true", help="Use built-in mock cost data for offline/free testing"
    )
    parser.add_argument(
        "--provider", choices=["ollama", "bedrock"], default=None, help="Override LLM provider"
    )
    args = parser.parse_args()

    if args.mock:
        print("[ℹ️] Running in MOCK mode with sample AWS daily spend data...")
        data = MOCK_COST_DATA
    else:
        data = fetch_aws_costs(days=args.days)
        if not any(day["services"] for day in data["daily_breakdown"]):
            print(f"[✅] No non-zero AWS spend recorded in the last {args.days} days.")
            sys.exit(0)

    analyze_costs(data, provider=args.provider)
