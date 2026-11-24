# EKS Internal Troubleshooting Runbooks

## 1. Promtail CrashLoopBackOff — YAML Unmarshal / Duplicate Key
- **Symptom:** Promtail pod in `observability` namespace enters `CrashLoopBackOff` with Exit Code 1 and logs `yaml: unmarshal errors: key "action" already set in map`.
- **Internal SOP:** Promtail config is managed via ConfigMap `promtail-config` in the `observability` namespace. Do NOT edit the pod directly.
- **Approved Fix:**
  1. Inspect the ConfigMap: `kubectl get cm promtail-config -n observability -o yaml`
  2. Remove the duplicate `action:` key inside `relabel_configs` or `pipeline_stages`.
  3. Apply the updated ConfigMap and trigger a clean rollout: `kubectl rollout restart daemonset/promtail -n observability`

## 2. AWS Load Balancer Controller / EBS CSI — IMDSv2 Hop Limit Failure
- **Symptom:** Pods fail to fetch IAM credentials from EC2 metadata (`169.254.169.254`) on AL2023 worker nodes.
- **Approved Fix:** Ensure the EKS node group Launch Template sets `HttpPutResponseHopLimit` to `2` (default `1` blocks containerized workloads from reaching IMDSv2).
