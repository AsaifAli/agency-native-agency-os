# Authentik OIDC setup for Agency OS

## Responsibility boundary

Authentik is the identity provider: passwords, recovery, MFA and OIDC authentication. Agency OS remains authoritative for local user activation, organization memberships, workspace permissions, Founder Authority, approvals and audit. An Authentik login never creates a user, membership, role or founder grant automatically.

## Authentik application/provider

1. Create an OAuth2/OpenID Connect provider in Authentik.
2. Use a **confidential** client and Authorization Code flow.
3. Configure PKCE with `S256` enabled/required if supported by the Authentik version.
4. Redirect URI (exact match): `https://<API_HOST>/v1/auth/callback`.
5. Scopes: `openid`, `profile`, `email`.
6. **Important for Authentik 2025.10 and newer:** its default email scope returns `email_verified: false` unless you explicitly configure an appropriate verified-email mapping. Create a custom OIDC email scope mapping that returns the user's stored verification attribute, for example:

   ```python
   return {
       "email": request.user.email,
       "email_verified": request.user.attributes.get("email_verified", False),
   }
   ```

   Set that attribute to `True` only after a real email verification process; clear it whenever the address changes. Attach the custom mapping to the provider instead of the default email mapping. Do not blindly assert all emails are verified.
7. Configure an authentication flow/policy that requires MFA for founder/admin identities. Prefer WebAuthn/passkeys. Confirm the policy is actually applied to this application/provider.
8. Create a custom OIDC scope mapping (for example, `agency_os_assurance`) that returns the agreed `acr` value only for the flow that has enforced MFA:

   ```python
   return {"acr": "urn:agency-os:aal2"}
   ```

   Attach the mapping to the provider and enable inclusion of custom claims in the ID token. This claim is trustworthy only if the application/provider authentication flow always requires the agreed MFA policy; never emit it unconditionally on a weaker flow.
9. Use the issuer URL shown by the provider. It commonly ends in `/`; preserve that exact issuer value.
9. Do not map Authentik groups directly to Agency OS owner/admin roles. Local memberships and Founder Authority are provisioned separately.

## Agency OS environment

Set these values through the deployment secret manager, not Git:

- `OIDC_ISSUER`: exact provider issuer URL.
- `OIDC_CLIENT_ID`: confidential client ID.
- `OIDC_CLIENT_SECRET`: client secret.
- `OIDC_STATE_SECRET`: independent random secret of at least 256 bits (64+ random characters); used to sign short-lived OIDC state/session data.
- `OIDC_REDIRECT_URI`: exact callback URL registered in Authentik.
- `OIDC_FRONTEND_URL`: canonical HTTPS console URL after successful login.
- `OIDC_REQUIRED_ACR`: exact assurance value emitted by Authentik after its mandatory MFA flow (example: `urn:agency-os:aal2`).
- `JWT_SECRET`: independent random secret of at least 256 bits.
- `CORS_ORIGINS`: exact console origin(s), never `*`.

Production startup fails closed if OIDC values are missing or redirect/frontend URLs are not HTTPS. Do not use example values.

## User provisioning and first login

1. Create the user, organization, membership, workspace and Founder Authority using the trusted bootstrap/provisioning process.
2. The Authentik email must be verified and match the pre-provisioned active Agency OS user.
3. First successful login binds the OIDC issuer + subject to that existing user. The mapping is unique and audited.
4. Later logins must match the same issuer, subject and email. Deactivated users or users without memberships are denied.

## Browser/session behavior

- Authentik's authorization state, nonce and PKCE verifier are stored in a short-lived AES-GCM-encrypted HttpOnly cookie; they are not exposed as readable client-side session data. OAuth access/ID tokens are not persisted in the browser session.
- Agency OS issues a short-lived HttpOnly session cookie after callback.
- Unsafe cookie-authenticated API calls require an allowlisted `Origin` and a matching double-submit CSRF token. The CSRF token is returned by `/v1/auth/csrf` and held in frontend memory only.
- The API and console should be deployed under the same site (for example, `console.example.com` and `api.example.com`). Production session cookies use `SameSite=None; Secure` to support credentialed cross-origin requests; browser third-party-cookie restrictions make unrelated-site deployments unsuitable. Prefer a same-site reverse proxy/BFF if possible.
- Logout clears browser cookies. The current JWT is short-lived (30 minutes); server-side token revocation/session ledger is a remaining hardening item.

## Verification still required

- Live OIDC login/callback with the actual Authentik tenant and HTTPS domains.
- Verify Authlib's ID-token signature, issuer, audience, expiry and nonce validation against the configured discovery/JWKS endpoints.
- Verify the live Authentik policy actually enforces MFA before emitting the configured `acr`; Agency OS now rejects callbacks without the exact `OIDC_REQUIRED_ACR` claim.
- Verify browser cookies and CSRF behavior in Safari and other target browsers with the actual console/API topology.
- Rotate any secrets previously used while the repository was public.
