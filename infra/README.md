# Infrastructure

Terraform for ShipScope's AWS infrastructure in us-east-2: a bootstrap stack with the resources both environments share, and a staging and a prod environment built from one module.

## Layout

| Path | Contents | Applied by |
|---|---|---|
| `bootstrap/` | The Terraform state bucket, GitHub's OIDC provider, the CI roles, the permissions boundary for workload roles, and the ECR repository | You, with your own credentials, so the pipeline can't change the roles it runs as |
| `modules/environment/` | Everything one environment needs | Nobody directly: the environment roots call it |
| `environments/staging/`, `environments/prod/` | One root per environment, each with its own settings and state file | The pipeline, with that environment's deploy role |

Every root sets the AWS provider's default tags: `Project`, `Environment` (`shared`, `staging`, or `prod`), and `ManagedBy`. Each root commits its `.terraform.lock.hcl`, so your machine and CI install the same provider builds.

## Signing in

Your AWS access uses `aws login`, which gives the CLI short-lived credentials from a console sign-in, with no access keys:

```bash
aws login --profile shipscope
export AWS_PROFILE=shipscope
```

Terraform and the AWS CLI both read `AWS_PROFILE`. A session lasts up to 12 hours; when commands fail with `ExpiredToken`, sign in again. Also sign in again after changing the profile's region, because a session can only refresh through the region it was created in.

## Checks

Run these from the repository root. None of them need AWS credentials.

| Check | Command |
|---|---|
| Format | `terraform fmt -recursive infra`. The pre-commit hook formats staged `.tf` files. |
| Validate | `terraform -chdir=infra/bootstrap init -backend=false && terraform -chdir=infra/bootstrap validate`, and the same for `infra/environments/staging` and `infra/environments/prod` |
| Lint | tflint, from its container image (below) |

Each root downloads its own copy of the AWS provider, about 840 MB. To share one copy between them, create a cache folder with `mkdir -p ~/.terraform.d/plugin-cache` and add `export TF_PLUGIN_CACHE_DIR="$HOME/.terraform.d/plugin-cache"` to your shell profile.

The first command downloads the plugins that `.tflint.hcl` lists into a Docker volume; rerun it only when that list changes. The second lints every directory under `infra/`:

```bash
docker run --rm -v "$PWD/infra:/data" -v shipscope-tflint:/root/.tflint.d \
  ghcr.io/terraform-linters/tflint:v0.64.0 --init --config=/data/.tflint.hcl
docker run --rm -v "$PWD/infra:/data" -v shipscope-tflint:/root/.tflint.d \
  ghcr.io/terraform-linters/tflint:v0.64.0 --recursive --config=/data/.tflint.hcl
```
