# Execution sandbox design and acceptance

**Status: Phase 1 API/worker container hardening is configured and verified in GitHub CI (image build, Compose validation and constrained container runtime checks). API/worker application startup and worker claim/recovery under these restrictions still require staging verification. Per-execution sandboxing and artifact gateway are not implemented.**

This document defines the execution-isolation boundary for the internal Agency OS. It does not claim that Docker Compose process separation, PostgreSQL RLS, or an Anthropic Managed Agents environment is itself a per-execution sandbox.

## Goals

- Keep the Agency OS control plane authoritative for identity, workspace scope, authorization, execution state, approvals, budgets, artifacts and audit.
- Run untrusted agent-generated code, tools and file processing outside the API process and outside the ordinary worker's trust boundary.
- Give every execution only the minimum data, credentials, filesystem and network access required by its approved task.
- Make execution bounded, observable, cancellable and recoverable; persist lifecycle and results in the OS.
- Default to synthetic/public data until the relevant provider and sandbox controls have been verified.

## Explicit non-goals

- Do not add a second Claude Agent SDK runtime for redundancy.
- Do not introduce local inference or local AI.
- Do not give agents direct database credentials, Docker socket access, host filesystem access or unrestricted network access.
- Do not introduce Kubernetes without a demonstrated operational requirement.
- Do not treat a prompt or skill instruction as a security boundary.

## Current verified boundary

The consolidated candidate separates API and worker processes in Docker Compose and uses distinct PostgreSQL API, worker and migration roles. The worker verifies its production database role and RLS posture at startup. The Tool Gateway applies OS-issued machine/session scope, capability checks, input/output protection, schema validation, idempotency, durable invocation records and audit. These controls are valuable but do not isolate arbitrary code per execution.

The application image now declares a dedicated UID/GID 10001 runtime user. The API and ordinary worker Compose services are configured for non-root execution, read-only root filesystems, a bounded noexec/nosuid/nodev `/tmp` tmpfs, all Linux capabilities dropped, no-new-privileges, PID limits, memory limits and CPU limits. Static contract tests cover these settings. GitHub CI successfully validates the Compose configuration, builds the image and runs it with the configured restrictions; it verifies effective UID 10001, `NoNewPrivs`, zero effective Linux capabilities, a read-only root mount and the bounded noexec/nosuid/nodev `/tmp` tmpfs. Application startup/health, migrations and worker claim/recovery/graceful shutdown under these restrictions still require staging verification. The ordinary worker remains a long-running process, not a disposable per-execution container. Managed Agents environment sandboxing and egress remain unverified; an environment identifier is not evidence of a verified sandbox.

**Therefore: per-execution sandboxing is currently an implementation gap. Do not run untrusted generated code, arbitrary shell commands, or hostile file-processing workloads in the API or ordinary worker.**

## Target architecture

1. **Control plane (Agency OS):** authenticates the requester; resolves organization/workspace; checks data classification, client policy, capability grant, runtime eligibility and approval; creates a durable execution record and outbox event.
2. **Execution broker:** claims an authorized execution using a lease, creates a short-lived sandbox from an approved immutable image, injects only short-lived scoped credentials, and records the sandbox/provider reference.
3. **Isolated execution boundary:** runs one bounded execution as a non-root identity with no host/Docker socket, no ambient provider credentials, no privileged mode, no host network and no arbitrary mounts. The default filesystem is read-only; only an explicitly scoped scratch/artifact mount is writable.
4. **Network policy:** default-deny egress. Allow only explicit destination/port rules required by the task. Block loopback-to-host, link-local, private, metadata and control-plane destinations unless a specific internal service is explicitly brokered. Enforce policy at the network layer, not only with URL validation.
5. **Artifact gateway:** transfers bounded outputs through an authenticated OS endpoint. The sandbox does not write directly to business tables or shared object storage. The gateway checks workspace ownership, file type, size, malware policy, classification, retention and audit before persistence.
6. **Lifecycle controller:** enforces wall-clock timeout, CPU, memory, process, file-size, concurrency and cost ceilings; supports cancellation, heartbeat/lease expiry, cleanup and reconciliation after crashes.
7. **Provider adapter:** Claude Managed Agents remains a separate hosted execution option for supported tasks. Its provider environment must independently pass the same data, network, retention and tenant-isolation acceptance review. The Agency OS retains canonical state and authorization.

## Isolation layers

- **Identity:** one execution identity, scoped to one workspace and one approved capability set; no reuse across clients.
- **Filesystem:** immutable image, read-only root, isolated scratch, explicit artifact transfer, no host mounts or Docker socket.
- **Process/container:** non-root UID/GID, no privileged mode, all Linux capabilities dropped, no-new-privileges, seccomp/AppArmor or equivalent runtime profile, PID limit and resource quotas.
- **Network:** default-deny egress, DNS and IP policy enforcement, metadata/private-range blocking, explicit allowlists, request-level SSRF defenses and audit.
- **Secrets:** short-lived per-execution credentials, injected only when required, never placed in prompts or logs, revoked on completion/timeout.
- **Data:** minimized task payload; workspace-scoped retrieval; no shared mutable cache; output revalidated before crossing back into the control plane.
- **Lifecycle:** durable execution/attempt/lease records; idempotent cleanup; orphan reconciliation; retention and deletion for scratch and artifacts.

A container is a useful first isolation layer, not a universal hostile-code boundary. Evaluate rootless containers plus seccomp/AppArmor first. Consider gVisor or microVM isolation only if the threat model, workload type or independent review demonstrates the need. Do not expose a Docker socket to the application or sandbox. If a privileged broker is required, isolate it as a separate minimal service with a narrow authenticated API and no general-purpose command endpoint.

## Implementation sequence

### Phase 0 — evidence and threat model
- Inventory every execution path, worker handler, provider callback, tool and file-processing entry point.
- Classify workloads as trusted deterministic OS code, provider-hosted agent work, or untrusted code/file processing.
- Confirm whether each workload needs shell/code execution at all. Prefer typed OS tools and provider-hosted execution where appropriate.
- Inspect actual Managed Agents environment configuration and provider-side network/retention controls with synthetic data.
- Document the threat model, trust boundaries, allowed data classes and prohibited workload classes.

### Phase 1 — harden existing API and worker containers
- [x] Declare dedicated non-root UID/GID 10001 in the application image.
- [x] Configure API and worker read-only root filesystems, bounded writable tmpfs, dropped Linux capabilities, no-new-privileges, PID/CPU/memory limits.
- [x] Keep API and worker roles distinct; no host paths or container runtime sockets are mounted.
- [x] Verify Compose configuration, Docker image build, effective UID, read-only root mount, zero effective capabilities, no-new-privileges and bounded tmpfs in GitHub CI.
- [ ] Verify API startup/health, migration compatibility, worker claims, shutdown and log handling under these restrictions in staging.
- These are defense-in-depth controls for the service containers, not a substitute for per-execution isolation.

### Phase 2 — isolated execution broker
- Add a typed execution profile registry; no caller-supplied image, command, mount or network policy.
- Create short-lived sandbox instances from pinned, scanned images.
- Pass a signed, expiring execution capability rather than database credentials.
- Enforce quotas and default-deny egress at the runtime/network layer.
- Persist creation, start, heartbeat, result, timeout, cancellation, cleanup and reconciliation state.
- Ensure provider calls and sandbox operations occur outside DB transactions; use idempotency and an outbox.

### Phase 3 — artifact and data boundary
- Add authenticated upload/download through the artifact gateway.
- Enforce workspace scope, content limits, safe file handling, malware scanning, classification and retention.
- Ensure caches, temporary files, logs, traces and provider payloads cannot cross workspace boundaries.
- Add deletion and recovery tests across scratch, artifacts and provider-side references.

### Phase 4 — adversarial verification
- Attempt cross-workspace access through APIs, database roles, cache keys, artifact IDs and execution references.
- Test prompt injection in retrieved documents and tool outputs; prove it cannot grant new capabilities.
- Test SSRF, DNS rebinding, redirects, private/link-local/metadata access, IPv4/IPv6 and alternate encodings.
- Test path traversal, symlinks, archive bombs, oversized files, malicious file types and output spoofing.
- Test resource exhaustion, fork/process storms, timeout, cancellation, worker crash, lease expiry, duplicate events and orphan cleanup.
- Verify no secrets appear in prompts, logs, traces, artifacts or test failure output.

## Required tests and release gates

A sandbox release is not accepted until all of the following have automated or recorded evidence:

- The sandbox runs as non-root and cannot gain privilege.
- The root filesystem is read-only; only the designated scratch path is writable.
- No host filesystem, Docker socket, host PID/network namespace or privileged device is accessible.
- CPU, memory, PID, disk, file-size, wall-time and concurrency limits are enforced.
- Default-deny egress is proven with positive allowlist and negative private/metadata/loopback tests, including DNS rebinding and redirect cases.
- An execution cannot read another workspace's inputs, credentials, outputs, cache entries or artifacts.
- The sandbox has no database credentials and cannot write core business tables.
- Cancellation and timeout revoke credentials and remove the sandbox and scratch data.
- Crashes and duplicate events reconcile without duplicate business side effects or orphaned credentials.
- Artifact transfer is workspace-authorized, bounded, audited and subject to retention/deletion.
- The full backend suite, isolated PostgreSQL 16 suite, container security scan and synthetic end-to-end tests pass on the exact candidate commit.
- Managed Agents provider environment controls are separately verified; do not infer them from local container tests.

## Operational policy

Until Phase 2 and its release gates are complete, only trusted application code and explicitly approved provider-hosted operations may execute. No arbitrary generated code, shell, user-supplied executable or untrusted document parser may run inside the API or ordinary worker. Keep client data disabled for unverified execution routes. Any move to production or real client data requires a separate founder go/no-go after evidence review.
