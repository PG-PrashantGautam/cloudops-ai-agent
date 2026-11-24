# InfoSec AWS IAM Guardrails & Compliance Standards

## 1. Amazon S3 Bucket Access Guardrails
- **Scope:** Any IAM policy granting read or write access to an S3 bucket (`s3:GetObject`, `s3:PutObject`, `s3:ListBucket`).
- **Mandatory Rules:**
  1. Never grant `s3:*` or `s3:DeleteBucket`.
  2. Separate bucket-level actions (`s3:ListBucket` on `arn:aws:s3:::<bucket>`) from object-level actions (`s3:GetObject`, `s3:PutObject` on `arn:aws:s3:::<bucket>/*`).
  3. Always include a `Condition` block enforcing HTTPS/TLS (`"Bool": {"aws:SecureTransport": "true"}`) on S3 object access statements.

## 2. General AWS IAM & Region Restrictions
- **Scope:** All IAM policies for production workloads.
- **Mandatory Rules:**
  1. Never allow `iam:PassRole` with `"Resource": "*"`.
  2. Where applicable, restrict operations to approved regions (`ap-south-1`, `us-east-1`) using `"StringEquals": {"aws:RequestedRegion": ["ap-south-1", "us-east-1"]}`.
