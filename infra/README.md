# Infrastructure

Terraform and deploy scripts for ShipScope's AWS infrastructure in us-east-2. A bootstrap stack holds the resources both environments share, and one module builds the staging and prod environments. The GitHub Actions pipeline deploys every merge to `main` to staging, then to prod once you approve it.

## Architecture

Each environment has its own copy of this request path:

```text
Browser ──HTTPS──► CloudFront  d….cloudfront.net
                     │
                     ├── * (default) ──Origin Access Control──► S3 bucket (private)
                     │     SPA function: /orders/42 → /index.html      index.html, assets/*, favicon.svg
                     │
                     └── /api/*   /admin/*   /static/*
                              │  VPC origin, HTTP
                              ▼
  ┌─────────────── VPC 10.x.0.0/16 ──────────────────────────────────────────────────┐
  │  private subnets   internal ALB :80          SG: CloudFront prefix list only     │
  │                          │                                                       │
  │  public subnets    Fargate task :8000        SG: from the ALB only               │
  │                    Gunicorn + Django         public IP, outbound only ───────────┼──► internet gateway
  │                          │ TLS                                                   │    (ECR, Secrets Manager,
  │  private subnets   RDS PostgreSQL 17 :5432   SG: from tasks only                 │     CloudWatch Logs)
  └──────────────────────────────────────────────────────────────────────────────────┘
```

CloudFront is the only part reachable from the internet. It serves the React build and the API on one HTTPS domain, so the browser never makes a cross-origin request:

| Path | Origin | Caching |
|---|---|---|
| `/api/*`, `/admin/*` | The load balancer, through a CloudFront VPC origin | None. Every HTTP method is allowed. Django receives the browser's `Host` header, and `CloudFront-Forwarded-Proto`, which tells it the browser used HTTPS. |
| `/static/*` | The load balancer | Cached. These are the Django admin's and DRF's files, which WhiteNoise serves with hashed names. |
| Everything else | The S3 bucket, through Origin Access Control | Cached. A CloudFront Function serves `index.html` for paths without a file extension, such as `/orders/42`, so the React app's client-side routes survive a reload. |

Every path redirects HTTP to HTTPS and adds AWS's managed security headers, including `Strict-Transport-Security`. The SPA fallback is a function on the S3 path rather than a custom error response, because custom error responses apply to every origin and would turn the API's 404s into the React page.

Security groups chain the hops. Each one admits only the hop before it:

| Security group | Inbound | Outbound |
|---|---|---|
| `shipscope-<environment>-alb` | Port 80 from CloudFront's origin-facing prefix list | Port 8000 to the tasks |
| `shipscope-<environment>-tasks` | Port 8000 from the load balancer | Port 443 to anywhere, for AWS APIs and later third-party APIs; port 5432 to the database |
| `shipscope-<environment>-database` | Port 5432 from the tasks | None |

The load balancer is internal and the database isn't publicly accessible. Both sit in private subnets whose route table has no internet route. The tasks run in public subnets with public IPs rather than behind a NAT gateway, which would cost about $33 a month per environment. Their security group admits only the load balancer, so the public IP only carries the tasks' own outbound calls.

### What each environment contains

| Part | Name | Details |
|---|---|---|
| Network | VPC `shipscope-<environment>` | Two Availability Zones, each with a public and a private `/24` subnet, and an internet gateway. No NAT gateway. |
| Database | RDS instance `shipscope-<environment>` | PostgreSQL 17, `db.t4g.micro`, 20 GB gp3, single-AZ, encrypted. Refuses connections without TLS. |
| Secrets | `shipscope/<environment>/django-secret-key`, `…/db-password`, `…/integrations` | Terraform generates the first two and never stores them in its state or shows them in a plan. `integrations` is for third-party API keys, which you set by hand. ECS injects secrets when a task starts. |
| API | ECS service `shipscope-<environment>-api` | One Fargate task with 0.25 vCPU and 0.5 GB, running Gunicorn with 2 workers. When a deployment's tasks keep failing, ECS rolls it back. ECS Exec is on. |
| Load balancer | `shipscope-<environment>-api` | Internal, HTTP on port 80. Health checks call `/api/health/` every 15 seconds. |
| Frontend | S3 bucket `shipscope-<environment>-frontend-…` and a CloudFront distribution | The bucket is private, and only the distribution can read it. |
| Logs | `/ecs/shipscope-<environment>` in CloudWatch Logs | One JSON object per line, from Django and Gunicorn |

The environments differ only in the values their roots pass to the module:

| Setting | Staging | Prod |
|---|---|---|
| VPC address range | `10.10.0.0/16` | `10.20.0.0/16` |
| Deletion protection on the database and the load balancer | Off | On |
| Database backups | Kept 1 day, no final snapshot | Kept 7 days, with a final snapshot before deletion |
| Deleted secrets | Deleted at once | Recoverable for 7 days |
| Log retention | 14 days | 30 days |

## Layout

| Path | Contents | Applied by |
|---|---|---|
| `bootstrap/` | The Terraform state bucket, GitHub's OIDC provider, the CI roles, the permissions boundary for workload roles, and the ECR repository | You, with your own credentials, so the pipeline can't change the roles it runs as |
| `modules/environment/` | Everything one environment needs | Nobody directly: the environment roots call it |
| `environments/staging/`, `environments/prod/` | One root per environment, each with its own settings and state file | The pipeline, with that environment's deploy role, or you |
| `scripts/` | The deploy scripts, which read what they need from Terraform outputs | Run by the pipeline, or by you |

Every root sets the AWS provider's default tags: `Project`, `Environment` (`shared`, `staging`, or `prod`), and `ManagedBy`. Each root commits its `.terraform.lock.hcl`, so your machine and CI install the same provider builds.

## Signing in

Besides Terraform, you need the AWS CLI 2.32 or later, for `aws login`, and jq, which the deploy scripts use. A shell in a running task also needs the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html).

Your AWS access uses `aws login`, which gives the CLI short-lived credentials from a console sign-in, with no access keys:

```bash
aws login --profile shipscope
export AWS_PROFILE=shipscope
```

Terraform and the AWS CLI both read `AWS_PROFILE`. A session lasts up to 12 hours. When commands fail with `ExpiredToken`, sign in again. Also sign in again after changing the profile's region, because a session can only refresh through the region it was created in.

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

Workload roles, such as an environment's ECS task roles, must use the path `/shipscope-workloads/<environment>/` and carry the boundary. That's the only kind of role a deploy role can create or change, so the pipeline can't give any role, including its own, more rights than the boundary allows. Only you apply this stack, with your own credentials. Both deploy roles are in one AWS account, though, so the staging role could still change prod's resources; only separate accounts would isolate the environments completely.

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
5. Connect GitHub, as described next.
6. Create each environment by hand the first time ([Deploying by hand](#deploying-by-hand)). The pipeline can create one too, but a first creation, which takes about 25 minutes, is where mistakes show up, and they're quicker to fix from your machine.

### Connecting GitHub

The pipeline reads these GitHub variables. None of them is a credential, so GitHub stores no secrets for AWS.

| Variable | Set on | Value |
|---|---|---|
| `AWS_REGION` | The repository | `us-east-2` |
| `AWS_ACCOUNT_ID` | The repository | The AWS account's ID. Signing in fails for any other account. |
| `ECR_REPOSITORY` | The repository | `shipscope-backend` |
| `ECR_PUSH_ROLE_ARN` | The repository | `terraform -chdir=infra/bootstrap output -raw ecr_push_role_arn` |
| `AWS_DEPLOY_ROLE_ARN` | The `staging` and `prod` environments, each with its own role | The environment's entry in `terraform -chdir=infra/bootstrap output deploy_role_arns` |

For example:

```bash
gh variable set AWS_DEPLOY_ROLE_ARN --env prod \
  --body "$(terraform -chdir=infra/bootstrap output -json deploy_role_arns | jq -r .prod)"
```

Both GitHub environments accept deployments from `main` only. `prod` also requires your review, and administrators can't bypass it, so every prod deploy waits for your approval.

## Releases

Every push to `main`, in practice every merged pull request, runs the pipeline in `.github/workflows/pipeline.yml`:

```text
lint ─┬─ test-backend  ─┬─ build-backend  ─┬─ deploy-staging ── deploy-prod
      └─ test-frontend ─┴─ build-frontend ─┘                    (after your approval)
```

The pipeline builds the backend image and the frontend once, and both environments get the same builds:

- `build-backend` pushes the image to ECR, tagged `git-<commit SHA>`, and passes it on by digest, so prod runs exactly the image staging ran. Tags are immutable, so a tag always means the image first pushed with it, and a re-run of the job reuses that image.
- `build-frontend` builds `frontend/dist`. The app calls the API on its own origin, so the build contains nothing specific to one environment.

Each deploy job runs `.github/workflows/deploy.yml`. It signs in to AWS as its environment's deploy role through GitHub's OIDC provider, then:

1. `terraform plan -out` and `apply` with `backend_image=<repository URL>@sha256:<digest>` register a task definition revision for the image. Nothing restarts yet: the service ignores new revisions until step 3.
2. `scripts/run-migrations.sh` runs `manage.py migrate` as a one-off task on the new revision, prints the task's output, and fails unless it exits 0. The job's log then lists each migration the release applied, such as `Applying accounts.0001_initial... OK`, or says `No migrations to apply.`
3. `scripts/roll-out-backend.sh` switches the service to the new revision and waits until ECS reports the deployment `SUCCESSFUL`. If the new tasks keep failing, the circuit breaker rolls the service back to the previous revision, and the job fails.
4. `scripts/publish-frontend.sh` uploads the build and invalidates CloudFront's cache.
5. `scripts/smoke-test.sh` checks the API, the database, and the page through CloudFront.

A deploy takes about 4 minutes. The job summary lists the URL, the image digest, and the task definition revision, and the repository's environments list each deployment. `deploy-prod` starts only once you approve it on the run page. Each environment runs one deploy at a time and never cancels one halfway. While one runs, a newer run's deploy waits and replaces any older one that's still waiting.

### Changing the schema

Migrations run before the new code takes traffic, but the old tasks keep serving until the rollout finishes, and a rollback runs the old code against the newer schema. So every migration must work with the release before it. Change the schema in two steps, expand and then contract:

1. **Expand:** add what the new code needs in a way the old code doesn't notice. Add a column as nullable, or give a new NOT NULL column a default in the database with `db_default=`. A plain `default=` isn't enough: Django applies it in Python and drops the column's default right after adding the column, so the old tasks' inserts fail with `null value in column … violates not-null constraint`.
2. **Contract:** drop a column or table in a later release, once no deployed release uses it. Renaming a column takes both steps: add the new column and copy the data into it, then drop the old one in a later release.

`backend/config/tests/test_migrations.py` runs [django-migration-linter](https://github.com/3YOURMIND/django-migration-linter) over every migration, as part of `test-backend`. It fails on operations that break the previous release, such as a NOT NULL column without a database default, a dropped or renamed column, or a changed column type. A deliberate contract step fails it too, because the linter can't tell it from a mistake: add that migration's name to `IGNORED_MIGRATIONS` in the test, with a comment saying why. Don't use the linter's `IgnoreMigration()` operation in the migration instead. The production image installs no development packages, so `migrate` would fail with `ModuleNotFoundError` when staging deploys.

## Deploying by hand

You can run the same release from your machine, for example if GitHub Actions is down. Sign in first, and run `terraform -chdir=infra/environments/<environment> init` once, because the scripts read Terraform outputs. The steps below deploy staging; for prod, replace `staging` with `prod`.

1. Build the backend image and push it to ECR, tagged `git-<commit SHA>`. `docker build` uses the files on disk, so start from a clean working tree. If the pipeline already pushed this commit, the tag exists and ECR refuses a second push, so run only the first two commands and the last one, which looks up the digest.

   ```bash
   repository=$(terraform -chdir=infra/bootstrap output -raw ecr_repository_url)
   tag=git-$(git rev-parse HEAD)
   aws ecr get-login-password | docker login --username AWS --password-stdin "${repository%%/*}"
   docker build --pull --platform linux/amd64 --provenance=false --sbom=false \
     --target runtime -t "$repository:$tag" backend
   docker push "$repository:$tag"
   digest=$(aws ecr describe-images --repository-name shipscope-backend --image-ids imageTag="$tag" \
     --query 'imageDetails[0].imageDigest' --output text)
   ```

2. `terraform -chdir=infra/environments/staging apply -var "backend_image=$repository@$digest"` registers a task definition revision for the image.
3. `infra/scripts/run-migrations.sh staging` runs the migrations on it.
4. `infra/scripts/roll-out-backend.sh staging` switches the service to it.
5. `(cd frontend && npm ci && npm run build)`, then `infra/scripts/publish-frontend.sh staging frontend/dist`.
6. `infra/scripts/smoke-test.sh staging`.

Terraform needs the image for every plan. To plan without changing it, pass the one that's running: `-var "backend_image=$(infra/scripts/deployed-image.sh staging)"`.

`run-migrations.sh` passes further arguments to `manage.py migrate`. `infra/scripts/run-migrations.sh staging --plan` lists what would run without changing anything, and `infra/scripts/run-migrations.sh staging <app label> <migration>` migrates one app forward or back to that migration. The task runs on the newest revision Terraform registered. After a release failed at its migrations, that revision holds the code that failed, so to run the code the service still runs, set `TASK_DEFINITION` to the service's revision:

```bash
TASK_DEFINITION=$(aws ecs describe-services --cluster shipscope-staging --services shipscope-staging-api \
  --query 'services[0].taskDefinition' --output text) infra/scripts/run-migrations.sh staging --plan
```

## Rolling back

Re-running a finished deploy job redeploys that run's image, frontend build, and Terraform configuration. To roll prod back to an earlier release:

1. Find the pipeline run that deployed it, in the deployment history of the repository's `prod` environment on GitHub, or with `gh run list --workflow pipeline.yml --branch main --event push`.
2. Re-run that run's `deploy-prod / deploy` job: on the run page, click the re-run icon next to the job. Or, with the job's `databaseId`:

   ```bash
   gh run view <run ID> --json jobs --jq '.jobs[] | {name, databaseId}'
   gh run rerun <run ID> --job <databaseId of deploy-prod / deploy>
   ```

3. Approve it on the run page, like any prod deploy.

To go forward again, re-run the newest run's `deploy-prod / deploy` job the same way. For staging, re-run `deploy-staging / deploy`. GitHub then also re-runs `deploy-prod / deploy`, which depends on it. That job waits for your approval: approve it to roll prod back too, or reject it to leave prod as it is.

- GitHub can re-run a run for up to 30 days after it started. For an older release, deploy its commit by hand. ECR keeps only the 30 newest images, and GitHub keeps the frontend build for 90 days.
- The re-run applies the old commit's Terraform configuration, so it also reverts any infrastructure change made since. Check `git diff <old commit> <new commit> -- infra/` first.
- A rollback doesn't undo migrations: the old code runs against the newer schema, which is why migrations must work with the previous release ([Changing the schema](#changing-the-schema)).

In an emergency, you can switch the backend alone back to an older task definition revision in about 2 minutes. Terraform keeps every revision registered:

```bash
aws ecs list-task-definitions --family-prefix shipscope-prod-api --sort DESC --max-items 5
infra/scripts/roll-out-backend.sh prod <task definition ARN>
```

That leaves the frontend as it is, and Terraform's state still records the newest revision, so a local `plan` shows a task definition change until the next release. The next release moves forward as usual.

## Parking staging

Staging costs about as much as prod, but you only need it while you're changing the project. To save about $45 a month, destroy it when you stop working, and let the next release recreate it:

```bash
terraform -chdir=infra/environments/staging destroy -var "backend_image=$(infra/scripts/deployed-image.sh staging)"
```

`destroy` lists what it will delete and asks for confirmation. It deletes the whole environment, including the database, its data, and the logs; staging keeps no final snapshot. It takes a while, mostly because CloudFront has to disable the distribution before deleting it. The task definition revisions (which cost nothing), the images in ECR, and the state file remain.

The last step, deleting the VPC, can fail with `DependencyViolation`. CloudFront creates a security group in the VPC for the VPC origin, `CloudFront-VPCOrigins-Service-SG`, and removes it on its own some time after the VPC origin is deleted, possibly hours later. By then everything that costs money is gone, and an empty VPC is free, so you can leave it: run the same `destroy` again later, or let the next release recreate staging in that VPC. Don't delete the security group yourself; AWS manages it.

To bring staging back, merge a pull request, or run the pipeline on `main` without one: `gh workflow run pipeline.yml --ref main`, or **Run workflow** on the pipeline's Actions page. The staging deploy then creates the whole environment, which takes about 25 minutes instead of 4. Staging's secrets are deleted at once rather than after a recovery window, so their names are free again. `deploy-prod` still waits for your approval. For a run of the commit prod already runs, approving changes nothing, while rejecting it marks the run as failed.

Every new distribution gets a new domain, so staging's URL changes each time. The newest deploy's job summary shows the current one, and so do the repository's `staging` environment on GitHub and `terraform -chdir=infra/environments/staging output -raw cloudfront_domain`. Anything that stores the URL, such as a Google OAuth redirect URI, has to be updated each time, unless the environments get a custom domain.

Prod can't be parked this way: deletion protection stops `destroy` at the database and the load balancer, on purpose.

## Logs and a shell in a task

To follow an environment's logs:

```bash
aws logs tail /ecs/shipscope-staging --follow
```

For a shell in the running task, through ECS Exec:

```bash
task=$(aws ecs list-tasks --cluster shipscope-staging --service-name shipscope-staging-api --query 'taskArns[0]' --output text)
aws ecs execute-command --cluster shipscope-staging --task "$task" --container api --interactive --command /bin/sh
```

Management commands work the same way, for example `--command "python manage.py createsuperuser"`. Don't put a password in the task definition instead: anyone who can read the task definition can read its environment.

## Costs

Monthly prices in us-east-2, checked in September 2026:

| Item | Per environment, per month |
|---|---|
| Application Load Balancer: $0.0225 an hour, plus capacity units, which are tiny at this traffic | ~$17 |
| RDS `db.t4g.micro`, single-AZ: $0.016 an hour | $11.68 |
| RDS storage, 20 GB gp3 | $2.30 |
| Fargate task, 0.25 vCPU and 0.5 GB | $9.01 |
| The task's public IPv4 address: $0.005 an hour | $3.65 |
| Secrets Manager, 3 secrets | $1.20 |
| CloudWatch Logs, S3, and data transfer | ~$1 |
| CloudFront, within its always-free monthly allowance of 1 TB, 10 million requests, and 2 million function invocations | $0 |
| **One environment** | **≈ $45** |

Both environments running all month cost about $90. With staging parked outside work sessions, the total is about $45 for prod plus about 6 cents per hour staging is up. The shared resources, ECR images and the state bucket, add well under $1 a month, and GitHub Actions is free for public repositories.

What the design avoids paying for, per environment: a NAT gateway (about $33 a month, plus $0.045 per GB), the two public IPv4 addresses an internet-facing load balancer would need ($7.30 a month), and Multi-AZ RDS (another $11.68 a month, plus the storage again).

To see actual costs, use Cost Explorer, grouped by the `Environment` tag. The `Project` and `Environment` tags have to be activated as cost allocation tags in the Billing console first. A monthly budget in AWS Budgets, set up by hand rather than in Terraform, sends email alerts.

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

## Troubleshooting

### Signing in and Terraform

| Symptom | Cause | Fix |
|---|---|---|
| `ExpiredToken` or `The security token included in the request is expired` on your machine | An `aws login` session lasts up to 12 hours | `aws login --profile shipscope` |
| After a change to the profile's region, every command fails with `CreateOAuth2Token … The provided authorization grant is invalid, expired, revoked, or malformed` | A session refreshes its credentials through the region it was created in, and the CLI now sends the refresh to the new one | Sign in again. Until then, setting `AWS_REGION` to the old region makes refreshes work. |
| Terraform finds no credentials, although the AWS CLI works | Profiles that reach an `aws login` session through `source_profile` don't work in Terraform yet | Use the login profile directly, or add a profile with `credential_process = aws configure export-credentials --profile shipscope --format process` |
| A local `plan` wants to replace the task definition | The `backend_image` you passed isn't the deployed one | `-var "backend_image=$(infra/scripts/deployed-image.sh <environment>)"` |
| `Error acquiring the state lock` | Another command holds the lock, or a cancelled or killed run left its lock file | Wait for the other command to finish. To release a stale lock, run `terraform force-unlock <lock ID>` in that root, with the ID from the error. |
| After an interrupted apply, the next one fails because a resource already exists | Terraform records a resource only after creating it, so anything created before the interruption is missing from the state | Compare `terraform state list` with what exists in AWS, `terraform import` each missing resource, then `plan` |
| After an import of the database, the plan sets `password_wo_version` | An import doesn't record the version of a write-only value | Apply it. RDS takes its password from the secret, so it gets the password the tasks already use. |
| `RulesPerSecurityGroupLimitExceeded` | CloudFront's prefix list counts as 55 of a security group's 60 inbound rules | Keep the prefix-list rule as the load balancer group's only inbound rule |
| `Your account must be verified before you can add new CloudFront resources` | AWS blocks some new accounts from CloudFront until they're verified | Open an "Account and billing" case with AWS Support. It can take days. |
| Parking staging ends with `DependencyViolation` while deleting the VPC | CloudFront's own security group for the VPC origin, `CloudFront-VPCOrigins-Service-SG`, is still in the VPC. CloudFront removes it some time after the VPC origin is deleted. | Nothing that costs money is left. Run the `destroy` again later, or leave the VPC for the next release to reuse ([Parking staging](#parking-staging)). |
| Recreating staging fails with `You can't create this secret because a secret with this name is already scheduled for deletion` | A deleted secret keeps its name during its recovery window. Staging's window is 0 days, so something changed that. | `aws secretsmanager delete-secret --force-delete-without-recovery --secret-id <name>` frees the name |

### Pipeline

| Symptom | Cause | Fix |
|---|---|---|
| `Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity` | The job's token doesn't match the role's trust policy. The subject must use the repository's immutable format with numeric IDs, a job in a GitHub environment sends `…:environment:<name>` instead of its branch, and the job needs the `id-token: write` permission. | Compare the trust policy with the prefix that `gh api repos/ValentinCasanova/shipscope/actions/oidc/customization/sub` prints |
| `deploy-prod` sits at "Waiting for review" | Prod deploys need your approval | Approve it on the run page. When several runs wait, approve the newest and cancel the rest. |
| `Run migrations` fails with `InconsistentMigrationHistory: Migration admin.0001_initial is applied before its dependency accounts.0001_initial` | The database applied Django's built-in migrations before the custom user model existed, and missed the one-time reset, or was restored from a backup older than it. Migrations run before the rollout, so the service keeps running the previous release. | Check that the database holds no users, groups, or admin log entries you need. Then unapply `auth`, which also drops the `admin` tables, with code from before the custom user model, and re-run the failed deploy job. After a failed release, the service's own revision has that code: `TASK_DEFINITION=$(aws ecs describe-services --cluster shipscope-<environment> --services shipscope-<environment>-api --query 'services[0].taskDefinition' --output text) infra/scripts/run-migrations.sh <environment> auth zero` |
| `Run migrations` fails with `ModuleNotFoundError: No module named 'django_migration_linter'` | A migration uses the linter's `IgnoreMigration()`, and the production image installs no development packages. CI passed, because the tests run with them. | Remove the operation, and add the migration's name to `IGNORED_MIGRATIONS` in `backend/config/tests/test_migrations.py` instead ([Changing the schema](#changing-the-schema)) |
| A rolled-back deployment counts as a success | Something waits with `aws ecs wait services-stable`, which succeeds once the rolled-back service is stable again | Wait with `roll-out-backend.sh`, which checks the deployment's own status |
| `tflint --init` fails with a GitHub API rate limit error | tflint downloads plugins through GitHub's API, which limits anonymous requests from shared runner addresses | Pass `GITHUB_TOKEN` to the step, as `pipeline.yml` does |
| Pushing an image fails with `ImageTagAlreadyExistsException` | Tags are immutable, so ECR rejects any push to an existing tag, even with identical content | Use the digest of the image that's already there ([Deploying by hand](#deploying-by-hand), step 1) |
| zizmor suggests `uses: $/.github/workflows/deploy.yml`, and with that change actionlint fails: `reusable workflow call "$/…" is not following the format …` | GitHub added the `$/` syntax in July 2026, after actionlint 1.7.12 was released | Keep `./`. GitHub resolves it from the commit the run is for, and the SHA-pinning requirement accepts it. Switch once actionlint supports `$/`. |

### The running app

| Symptom | Cause | Fix |
|---|---|---|
| CloudFront returns 502 or 504 for `/api/*` | The VPC origin is still being created, which takes up to 15 minutes, or the load balancer's security group lacks the prefix-list rule, or no target is healthy | Check `aws cloudfront get-vpc-origin`, the target group's health, and the security group rules |
| Targets are unhealthy, and Django logs `Invalid HTTP_HOST header: '10.10.x.x:8000'` | Health checks send the task's IP as the `Host` header, and the task's IP lookup didn't add it to the allowed hosts | Look for the lookup's warning in the task's first log lines. `ECS_CONTAINER_METADATA_URI_V4` only exists on ECS. |
| Healthy tasks get replaced over and over while the database is unreachable | The health check timeout isn't longer than Django's 5-second database `connect_timeout` | Keep the 10-second timeout in `modules/environment/alb.tf` |
| The task logs `connection timeout expired` when connecting to the database | The database's security group doesn't admit the tasks' group, or the tasks' group can't send to port 5432 | Check the security group chain in [Architecture](#architecture) |
| A task stops with `ResourceInitializationError: unable to pull secrets or registry auth` | The execution role can't read a secret, or the task has no public IP and so no route to Secrets Manager or ECR, or the task definition names a JSON key the secret doesn't have | Check the execution role's policy, the service's `assign_public_ip`, and the secret's keys |
| Signing in to the Django admin fails with `Origin checking failed - https://….cloudfront.net does not match any trusted origins` | Django thinks the request came over HTTP: the path's origin request policy doesn't forward `CloudFront-Forwarded-Proto`, or `DJANGO_BEHIND_CLOUDFRONT` isn't set | Use `Managed-AllViewerAndCloudFrontHeaders-2022-06` on `/api/*` and `/admin/*`, and set the variable |
| API errors come back as 200 with the React page | The distribution has custom error responses, which apply to every origin | Remove them. The SPA routing function handles the app's routes. |
| `/admin` without a trailing slash shows the React app | The `/admin/*` path needs the slash, so the S3 path served the request | Use `/admin/` |
| Staging's URL changed | Recreating staging creates a new distribution, and every distribution gets its own domain | Expected after [parking](#parking-staging). The newest deploy's job summary shows the current URL. |
