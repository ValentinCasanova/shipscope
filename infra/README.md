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

## Bootstrap stack

`bootstrap/` holds the resources both environments share:

| Resource | Name | Details |
|---|---|---|
| State bucket | `shipscope-tfstate-<random suffix>` | Versioned, with old versions kept for 90 days. Encrypted, public access blocked, and requests without TLS denied. Terraform refuses to destroy it. |
| GitHub OIDC provider | `token.actions.githubusercontent.com` | Accepts tokens whose audience is `sts.amazonaws.com` |
| Build role | `shipscope-ecr-push` | Trusts workflow runs for pushes to `main`. Can push and pull backend images, nothing else. |
| Deploy roles | `shipscope-staging-deploy`, `shipscope-prod-deploy` | Each trusts only jobs that run in the GitHub environment of the same name. `PowerUserAccess`, plus IAM rights over that environment's workload roles |
| Permissions boundary | `shipscope-workload-boundary` | The most a workload role can ever do: pull backend images, write to the `/ecs/shipscope-*` log groups, read `shipscope/*` secrets, and open ECS Exec sessions |
| ECR repository | `shipscope-backend` | Immutable tags and scanning on push. Keeps the 30 newest images and expires untagged ones after 7 days. |

The CI roles live under the IAM path `/shipscope-ci/`, and sessions last up to 2 hours. A trust policy matches the full OIDC subject, such as `repo:ValentinCasanova@129884225/shipscope@1368534118:environment:prod`. `gh api repos/ValentinCasanova/shipscope/actions/oidc/customization/sub` prints the part before `:environment`.

Workload roles, such as an environment's ECS task roles, must use the path `/shipscope-workloads/<environment>/` and carry the boundary. That's the only kind of role a deploy role can create or change, so the pipeline can't give any role, including its own, more rights than the boundary allows. Only you apply this stack, with your own credentials.

Each stack keeps its state in the bucket under its own key: `bootstrap/terraform.tfstate`, `environments/staging/terraform.tfstate`, and `environments/prod/terraform.tfstate`. The backend blocks lock a state with a lock file next to it while a command runs.

To change the stack, sign in and run:

```bash
terraform -chdir=infra/bootstrap init
terraform -chdir=infra/bootstrap plan
terraform -chdir=infra/bootstrap apply
```

`terraform -chdir=infra/bootstrap output` prints the role ARNs and the repository URL that GitHub needs.

To create the stack in a new account, the state has to start locally, because the bucket doesn't exist yet:

1. Move `bootstrap/backend.tf` out of the folder, then run `init` and `apply` as above. The state is written to `bootstrap/terraform.tfstate`, which git ignores.
2. Put the backend file back, with the new bucket name from `terraform -chdir=infra/bootstrap output -raw state_bucket`.
3. Run `terraform -chdir=infra/bootstrap init -migrate-state` and answer `yes` to copy the state into the bucket. Delete `bootstrap/terraform.tfstate` and `bootstrap/terraform.tfstate.backup`.
4. Put the same bucket name in each environment's `backend.tf`.

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
