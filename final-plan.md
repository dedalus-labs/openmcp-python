# Final Plan: OpenMCP Remote Authentication & Execution Architecture

## Overview

This plan captures the agreed architecture for running generalizable MCP resource
servers on AWS (Lambda, ECS/Fargate, EC2) while keeping credentials secure and
the developer experience consistent across marketplace and first-party
deployments.

The goals are:

1. **OAuth 2.1 + DPoP for every client** – no shortcuts, even for headless agents.
2. **Connection handles everywhere** – tokens describe exactly which connector a
   call may use (kind, fingerprint, auth type).
3. **Org secrets stay in AWS vaults** – resource servers fetch them through AWS
   Secrets Manager/KMS; no `.env` dependence in production.
4. **User secrets never reach marketplace boxes** – encrypted blobs are forwarded
   straight to the Dedalus execution backend, which unwraps them inside KMS/CloudHSM.
5. **Drivers + connectors make support for new services trivial** – Supabase,
   Notion, GitHub, etc. just register connector metadata and drivers.

## Components

### Authorization Server (Go, already built)
- OAuth 2.1 Authorization Code + PKCE + DPoP.
- Issues JWT access tokens with `ddls:connections`, fingerprints, and
  `ddls:execution_backend` metadata.
- Supports public clients (device flow/headless) and confidential clients.

### Resource Server (Python OpenMCP runtime)
- Uses the typed connector framework (`EnvironmentCredentialLoader` or custom
  loaders) to describe connections.
- For each request:
  1. Validates DPoP, checks token audience, extracts connection handle.
  2. Fetches connector metadata from vault (RDS/DynamoDB) – includes auth type,
     fingerprint, and pointer to secrets in AWS Secrets Manager.
  3. Routes depending on auth type:
     - **Org credential:** decrypt secret via AWS KMS/CloudHSM, instantiate driver
       in-process (`SupabaseDriver`, `HttpApiDriver`, etc.).
     - **User credential:** forward `_mcp_user_credential` to execution backend
       without ever unsealing it.

### Execution Backend (Dedalus-operated, AWS hosted)
- Possesses the private key (stored in AWS CloudHSM/KMS) that matches the public
  key published in the AS metadata.
- Receives encrypted user credential + tool call, unwraps the payload, executes
  upstream request, returns result.
- Central place for auditing, rate limiting, and zero-trust enforcement.

### Credential Sources
- **Local dev / STDIO transport:** optional `.env` loader (fallback for quick
  testing).
- **AWS production:** loaders backed by Secrets Manager, Parameter Store, or
  direct KMS decrypts. No secrets in environment variables.

## Request Flow

1. Client performs OAuth 2.1 + DPoP, obtains JWT bound to connection handles.
2. Client sends MCP request (Streamable HTTP or STDIO) with DPoP proof.
3. Resource server validates proof, consults connection handle metadata.
4. If auth type == org:
   - Retrieve secret from Secrets Manager.
   - Driver produces in-process client using decrypted secret.
   - Execute tool logic locally.
5. If auth type == user:
   - Obtain `_mcp_user_credential` encrypted for execution backend.
   - Forward to backend; receive result.
   - Return result to client.

## Diagram

```
┌─────────────┐      OAuth 2.1 / DPoP       ┌────────────────────────┐
│   Client    │ ───────────────────────────▶│ Authorization Server    │
└─────┬───────┘                             └────────┬───────────────┘
      │ JWT (aud, ddls:connections, backend)         │
      ▼                                              │
┌──────────────┐ 4a SecretsMgr/KMS  ┌──────────────┐ │
│ Resource     │──────────────────▶│ Org secrets   │ │
│ Server (AWS) │◀──────────────────│ (AWS)         │ │
└────┬─────────┘                   └──────────────┘ │
     │4b Forward encrypted user cred                │
     ▼                                              │
┌──────────────────┐  KMS/CloudHSM   ┌──────────────┐│
│ Execution Backend│ ──────────────▶ │ Upstream APIs││
│ (Dedalus, AWS)   │ ◀────────────── │ (Notion etc.)││
└──────────────────┘                └──────────────┘│
                 ▲                                  │
                 └────────── Result ────────────────┘
```

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Execution backend compromise | Private keys in CloudHSM/KMS; audit & alerts | 
| Token tampering or replay | DPoP proofs, handle fingerprints, short-lived JWTs |
| SecretsManager downtime | Local cache + exponential backoff |
| Driver misuse | Typed connectors/clients; explicit auth types enforce behavior |

The architecture is a direct extension of the conversation plan: no unproven
assumptions, and all components map to AWS primitives (Secrets Manager, KMS,
CloudHSM, Lambda/ECS). The `.env` loader remains purely for local testing.

