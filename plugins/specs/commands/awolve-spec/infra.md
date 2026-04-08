---
description: Enrich design.md with detailed infrastructure specifications
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion]
argument-hint: [project/feature-name]
---

# /awolve-spec infra

Review an existing `design.md` and add a detailed `## Infrastructure` section covering all infrastructure changes the feature requires. Uses SIGL description headers as a reasoning framework (see `handbook-context/engineering/architecture/sigl-spec.md`).

## When to use

Run this after `/awolve-spec design` when the feature touches cloud infrastructure, new services, networking, deployment, or system topology. Skip it for pure application-code changes with no infra footprint.

## Instructions

### 1. Resolve project and feature

The user's argument "$ARGUMENTS" may contain a project name, feature name, or both.

Find the feature folder. It must have a `design.md` — if it doesn't, tell the user to run `/awolve-spec design` first.

### 2. Read context

Read the existing `design.md` in the feature folder.

Check if the project has a SIGL file in the repo root:

```bash
find . -maxdepth 1 -name "*.sigl.yaml" -o -name "*.sigl.yml" 2>/dev/null
```

If a SIGL file exists, read it to understand the current system topology.

### 3. Identify infrastructure changes

Walk through `design.md` and identify every infrastructure change — explicit or implied:
- New services or compute resources
- New datastores (databases, blob storage, caches, queues)
- New event/messaging components
- Networking changes (new endpoints, VNet changes, DNS)
- Deployment changes
- New external service integrations

### 4. Apply SIGL description headers

For each identified component, answer the relevant SIGL headers. This is the core of the command — be precise and unambiguous so an implementing agent makes correct decisions without guessing.

**For every new service/compute:**
- `host-type` — VM, container, serverless, managed service, PaaS?
- `resource-profile` — CPU/memory/GPU expectations
- `network-position` — VNet, subnet, public/private
- `deployment-method` — CI/CD, manual, ARM template, docker push?
- `scaling-behavior` — auto/manual, triggers, limits
- `failure-mode` — what happens when it's down, blast radius

**For every new datastore:**
- `access-pattern` — read-heavy, write-heavy, bursty, steady
- `size-estimate` — current size and growth rate
- `backup-strategy` — frequency, tested restore
- `data-classification` — PII, financial, public, internal
- `retention` — how long data is kept

**For every new event/messaging component:**
- `delivery-guarantee` — at-most-once, at-least-once, exactly-once
- `ordering` — ordered, per-key, best-effort
- `dead-letter` — where failed messages go
- `consumer-model` — competing, fan-out, single

**For every connection crossing a trust boundary:**
- `protocol` — HTTPS, gRPC, AMQP, WebSocket
- `auth-mechanism` — managed identity, API key, mTLS
- `failure-handling` — retry, circuit break, degrade

**For the system as a whole:**
- Which cloud, region, resource group
- How is it managed (Terraform, Bicep, manual)
- Any compliance or residency constraints

Not every header applies to every component. Use what's relevant, skip what isn't.

### 5. Add Infrastructure section to design.md

Add a `## Infrastructure` section to the existing `design.md`. Structure it by component:

```markdown
## Infrastructure

### [Component Name]

**Host type:** Azure Container App, consumption plan
**Resource profile:** 0.5 vCPU, 1GB memory per instance
**Network position:** Internal VNet, private endpoint
**Deployment:** GitHub Actions → ACR → Container App revision
**Scaling:** Auto-scale 0-5 based on HTTP concurrency (50 concurrent)
**Failure mode:** Requests queue in load balancer, 30s timeout, no data loss

### [Database Name]

**Type:** Azure PostgreSQL Flexible Server, General Purpose D2s_v3
**Access pattern:** Read-heavy (10:1 read/write), steady load
**Size estimate:** ~5GB year one, ~500MB/month growth
**Backup:** Azure automated, 7-day retention, geo-redundant
**Data classification:** Internal, no PII
**Retention:** Indefinite for active records, archive after 2 years

### Networking

[Any VNet, DNS, endpoint, or NSG changes]

### Management

**Cloud:** Azure
**Region:** Sweden Central
**Resource group:** [name]
**IaC:** Terraform (existing modules in `/infra`)
```

### 6. Push

The PostToolUse hook handles the push automatically after editing design.md.

### 7. Stop

Tell the user:

```
Infrastructure section added to: {path to design.md}

Next step: run `/awolve-spec plan` to create the implementation plan, or get the design reviewed first.
```
