# 04 — Kubernetes / Amazon EKS Troubleshooter

## What It Does
Diagnoses Kubernetes and Amazon EKS resources using **read-only `kubectl` commands**, featuring a **Fuzzy Pod Matcher** and **Status-Based Conditional Branching** so it only fetches the diagnostics relevant to the actual failure state.

## How It Works (Teaching Points)
1. **Fuzzy Pod Matching:** Users can type `"promtail"` instead of `"promtail-klx8l"`; the script resolves the exact pod hash dynamically.
2. **Status-Based Conditional Branching:**
   * **`Pending`:** Skips logs (none exist yet) and checks `kubectl get nodes -o wide` for capacity/scheduling issues.
   * **`CrashLoopBackOff` / `OOMKilled` / `Error`:** Pulls both `--previous` crash logs and current container logs.
   * **`Running`:** Pulls recent logs plus `svc,endpoints` to catch networking/selector mismatches.
3. **Namespace Warnings & Trimming:** Always includes the last 10 `Warning` events in the namespace and trims verbose `describe` output to keep the prompt fast and focused.

## Usage
```bash
# Offline demo (--mock simulates a Promtail CrashLoopBackOff YAML error)
pg-ai "check promtail pod in observability" --mock

# Live cluster troubleshooting
pg-ai "check promtail pod in observability"
python3 projects/04_eks_troubleshooter/eks_troubleshooter.py -n observability -t pod --name promtail
```
