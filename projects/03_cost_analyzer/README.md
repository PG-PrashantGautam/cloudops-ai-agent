# 03 — AWS FinOps Cost Anomaly Analyzer

## What It Does
Fetches daily unblended AWS spend grouped by `SERVICE` from **AWS Cost Explorer** (`us-east-1`), sorts services by highest spend, and uses `qwen2.5-coder:3b` to produce an executive FinOps report highlighting **Top Cost Drivers**, **Day-over-Day Anomalies**, and **AWS-Native Optimizations**.

## How It Works (Teaching Points)
1. **Clean Data Pre-Processing:** Filters out `$0.00` services and sorts daily spend descending before sending JSON to the LLM—this dramatically improves small-model accuracy.
2. **Actionable FinOps Output:** Prompted to recommend concrete AWS fixes (e.g., S3 Gateway Endpoints vs. NAT Gateway data processing, Spot instances, Savings Plans).

## Usage
```bash
# Offline demo (--mock simulates a sudden NAT Gateway & AWS Glue spend spike)
pg-ai "check aws cost anomalies for the last 7 days" --mock

# Live AWS Cost Explorer query (requires ce:GetCostAndUsage IAM permission)
python3 projects/03_cost_analyzer/cost_analyzer.py --days 14
```
