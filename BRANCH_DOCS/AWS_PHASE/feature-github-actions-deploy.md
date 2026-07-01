# BRANCH: feature/github-actions-deploy

---

## Branch Metadata

```
Branch Name        →  feature/github-actions-deploy
Task ID            →  P-014
Workstream         →  CI/CD
Author             →  Anoushka Vyas
Reviewer           →  Devam
Start Date         →  Day 6, Week 2
Target Merge Date  →  Day 7, Week 2
Actual Merge Date  →  [Fill on completion]
Status             →  Ready for Review
```

---

## Objective

**What does this branch do?**
Adds `.github/workflows/deploy.yml` — the GitHub Actions pipeline that builds the production Docker image (P-010) on every push to `develop-aws` or `main`, pushes it to ECR tagged with the git SHA + `latest`, then renders and deploys both ECS task definitions (`deploy/taskdef-api.json`, `deploy/taskdef-worker.json`) to the `baggage-api` and `baggage-worker` services on the `baggage-claim-cluster`.

**Why is it needed?**
🚫 No Docker on office laptops — GitHub Actions is the only place an image can be built (P-010 rule). Without this pipeline there is no path from a merged PR to a running container, so P-016 (first image push) and P-017 (first ECS deploy) are both blocked on this branch existing first.

---

## Technical Approach

**Files Created:**

| File | Purpose |
|---|---|
| `.github/workflows/deploy.yml` | 3-job pipeline: `build-and-push` (shared) → `deploy-api` + `deploy-worker` (parallel, depend on build) |

**Files Modified:**
None. This branch only adds the workflow file — `deploy/taskdef-api.json` and `deploy/taskdef-worker.json` already exist from P-010 and are consumed as-is.

**Key Design Decisions:**

```
1. ONE BUILD JOB, TWO DEPLOY JOBS
   The API and worker run off the identical image (P-010) — only the ECS
   task definition's `command` field differs. Building once and fanning out
   to two deploy jobs avoids double image builds and guarantees both
   services always run the exact same SHA.

2. IMAGE TAGGED WITH BOTH git SHA AND 'latest'
   SHA tag gives every deploy a traceable, immutable reference (shows up in
   `aws ecs describe-tasks` and CloudWatch). 'latest' is kept for convenience
   (manual pulls, debugging) but task defs always deploy the SHA tag, never
   'latest' — so a stale local `docker pull latest` can never diverge from
   what's actually running.

3. aws-actions/amazon-ecs-render-task-definition + ...-deploy-task-definition
   Standard AWS-maintained actions instead of hand-rolled aws-cli calls.
   render-task-definition swaps in the freshly-built image URI without
   touching any other field (env vars, secrets refs, roles); deploy-task-
   definition registers the new revision and calls UpdateService.

4. wait-for-service-stability: true
   Pipeline blocks until ECS reports the new tasks are RUNNING and passing
   health checks, so a bad deploy fails the GH Actions run instead of
   silently leaving the old (or a crash-looping) task set live.

5. deploy-api / deploy-worker RUN IN PARALLEL (not sequential)
   Both `needs: build-and-push` only — not each other. They're independent
   services; no reason to serialize and double the pipeline's wall-clock time.
```

**Future Swap Path:**

```
Access keys → OIDC (Phase 2 hardening, per Git & Coding Standards sheet):
1. Replace aws-access-key-id/aws-secret-access-key inputs on
   configure-aws-credentials with role-to-assume + OIDC provider ARN
2. No other step changes — role just needs the same ECR/ECS permissions
```

---

## Dependencies

```
Depends On (Task IDs)      →  P-010 (Dockerfile + taskdef-*.json templates must exist)
External Libraries         →  aws-actions/configure-aws-credentials@v4,
                              aws-actions/amazon-ecr-login@v2,
                              aws-actions/amazon-ecs-render-task-definition@v1,
                              aws-actions/amazon-ecs-deploy-task-definition@v2
Environment Variables      →  None new in the app — pipeline-only: AWS_REGION,
                              ECR_REPOSITORY, ECS_CLUSTER (hardcoded in workflow env block)
GH Secrets Required        →  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
AWS Resources Required     →  ECR repo abc-baggage-claim, ECS cluster baggage-claim-cluster,
                              services baggage-api + baggage-worker — ALL pre-created by
                              admin under P-013 (not yet done as of this branch)
IAM Permissions Required   →  ecr:GetAuthorizationToken/BatchCheckLayerAvailability/
                              PutImage/InitiateLayerUpload/UploadLayerPart/CompleteLayerUpload,
                              ecs:RegisterTaskDefinition/UpdateService/DescribeServices,
                              iam:PassRole on the task + execution roles
```

---

## Testing

**How to Test (Manual):**

```
1. Push a trivial commit to develop-aws (e.g. a comment-only change)
2. Watch the Actions tab → "Deploy to AWS" workflow run
3. build-and-push job should go green → image visible in ECR with the
   commit SHA as tag (aws ecr list-images --repository-name abc-baggage-claim)
4. deploy-api / deploy-worker jobs will only go green once P-013 (admin)
   has created the ECS cluster + services — until then they're EXPECTED
   to fail at the "Deploy task definition" step with a ClusterNotFoundException
   or ServiceNotFoundException. That's not a bug in this branch.
```

**Acceptance Criteria (per tracker):**

```
✅ Test push triggers GH Actions
✅ Image appears in ECR with git SHA tag
⏳ deploy-api / deploy-worker jobs — cannot go fully green until P-016/P-017
   (ECR repo + ECS services exist). Verified the workflow YAML is valid
   (actionlint / GitHub's own syntax check on push) and that build-and-push
   completes end-to-end.
```

---

## PR Checklist

```
[x] PR title includes Task ID — [P-014] ci(deploy): add GitHub Actions ECR/ECS pipeline
[x] PR description filled out on GitHub (What changed / How to test / Task)
[x] Base branch set to develop-aws (NOT develop, NOT main)
[x] Reviewer assigned — Devam
[ ] GitHub Actions green                                    ← build-and-push only, until P-016/P-017
[ ] Squash merged to develop-aws                             ← after approval
[ ] Feature branch deleted after merge (local + remote)      ← after merge
[ ] Tracker updated: Status=Done, Actual Hours, Completion Date, PR Link
[x] No hardcoded credentials — AWS keys read from GH Secrets only
[x] Branch doc committed to BRANCH_DOCS/AWS_PHASE/ before merge
```

---

## Notes / Blockers

```
Known Issues    →  None in the workflow itself.

Blockers        →  deploy-api / deploy-worker jobs will fail until P-013
                   (admin ticket: ECR repo, ECS cluster, 2 services, IAM
                   roles) is at least partially complete. This is expected
                   and tracked — not a defect in this branch. build-and-push
                   is fully testable today since it only needs the ECR repo.

Links           →  AWS_Phase_Tracker.xlsx (row P-014 — Workstream Overview + Task Tracker)
                   deploy/taskdef-api.json, deploy/taskdef-worker.json (P-010, consumed as-is)
                   BRANCH_DOCS/AWS_PHASE/chore-aws-repo-bootstrap.md (P-001)
                   BRANCH_DOCS/AWS_PHASE/admin-coordination-w2.md (P-013 — unblocks full deploy)
```

---

*Branch opened: Day 6, Week 2 — Anoushka Vyas*
*Merged to develop-aws: [Day 7, Week 2 — fill on merge]*