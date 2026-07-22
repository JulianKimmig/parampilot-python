# Security policy

## Supported candidate

The unreleased `0.1.0` candidate targets ParamPilot programmatic API major 2
and Python 3.10 through 3.14. Until a public release exists, no version has a
published security-support lifetime.

## Reporting a vulnerability

Use GitHub private vulnerability reporting for
`JulianKimmig/parampilot-python` once the public repository is available. If
private reporting is unavailable, contact the owner through an established
private channel. Do not disclose token material, exploit details, private
deployment addresses, or user data in a public issue.

Include the affected SDK/server versions, a minimal reproduction using fake
credentials and data, impact, and any proposed mitigation. Never mint or share
a real ParamPilot token solely for a report.

## Credential response

ParamPilot programmatic tokens are created and revoked in the ParamPilot UI.
If a token may have been exposed, revoke it immediately, create a replacement
only when needed, rotate every integration using it, and inspect the owning
deployment's audit information. The SDK never creates, persists, or displays
tokens and redacts authorization data from safe representations and errors.

## Release boundary

Public source is extracted from one clean private commit through a reviewed
allowlist into a tree with no inherited Git history. The extractor rejects
symlinks, credentials, private imports, absolute paths, non-registry
dependencies, unexpected files, and manifest drift. Publishing still requires
an owner-approved version, audited tree and immutable artifacts, scoped
credentials, and an explicit publication action.
