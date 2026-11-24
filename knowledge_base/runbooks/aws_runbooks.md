# AWS CloudWatch & IAM Incident Runbooks

## 1. Lambda Cross-Account AssumeRole AccessDenied
- **Symptom:** CloudWatch logs show `AccessDenied` when calling `sts:AssumeRole` from `lambda-payment-exec-role` to `cross-account-billing-reader`.
- **Internal SOP:** Cross-account roles are managed in the centralized `security-iam` Terraform repo. Do NOT attach inline policies manually in the AWS Console.
- **Approved Fix:**
  1. Verify the Trust Policy on `arn:aws:iam::987654321098:role/cross-account-billing-reader` explicitly trusts account `123456789012`.
  2. Raise a PR in `security-iam` adding `sts:AssumeRole` for that role ARN to `lambda-payment-exec-role` and loop in InfoSec for approval.
