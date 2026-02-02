---
id: ACF-0003
title: Implement JWT-based user authentication
type: Feature
status: Done
owner: Developer Agent
story_points: 5
priority: High
---

# ACF-0003 - Implement JWT-based user authentication

## User Story

**As an** API consumer
**I want** to authenticate using JWT tokens
**So that** I can securely access protected resources without maintaining session state

## Background

The application needs a secure authentication mechanism for API consumers. JWT (JSON Web Token) provides a stateless, scalable solution that works well with microservices and mobile clients. This feature will implement a complete authentication flow including token generation, validation, and refresh capabilities.

## Acceptance Criteria

### Scenario 1: Successful Login
**Given** a registered user with valid credentials (email and password)
**When** the user submits a POST request to `/api/auth/login`
**Then** the system returns a JWT access token and refresh token
**And** the access token expires after 60 minutes
**And** the refresh token expires after 7 days

### Scenario 2: Invalid Credentials
**Given** a user submits invalid credentials
**When** the login request is processed
**Then** the system returns HTTP 401 with error message "Invalid credentials"
**And** no token is generated

### Scenario 3: Access Protected Resource
**Given** an authenticated user with a valid JWT access token
**When** the user requests a protected endpoint with the token in the Authorization header
**Then** the system validates the token and allows access to the resource

### Scenario 4: Expired Token
**Given** a user provides an expired JWT access token
**When** the user requests a protected endpoint
**Then** the system returns HTTP 401 with error message "Token expired"

### Scenario 5: Refresh Token Flow
**Given** a user has a valid refresh token
**When** the user submits a POST request to `/api/auth/refresh` with the refresh token
**Then** the system generates a new access token and refresh token pair
**And** the old refresh token is invalidated (rotation)

### Scenario 6: Logout
**Given** an authenticated user wants to logout
**When** the user submits a POST request to `/api/auth/logout`
**Then** the system invalidates the current refresh token
**And** the access token remains valid until expiration but cannot be refreshed

## Definition of Done

- [x] JWT authentication endpoints implemented (`/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout`)
- [x] Unit tests for token generation and validation (>80% coverage)
- [x] Integration tests for authentication flow
- [x] Password hashing using bcrypt (work factor 12)
- [x] Token validation middleware implemented
- [x] Swagger documentation updated with authentication requirements
- [x] Security review completed (OWASP compliance)
- [x] ADR-003 created documenting JWT implementation decisions
- [x] Traceability: All commits reference `ACF-0003`
- [x] Code review approved by 2 reviewers
- [x] Deployed to staging environment
- [x] No critical or high security vulnerabilities

## Technical Notes / Approach

### Architecture
Following Clean Architecture principles:
- **Domain Layer**: `JwtToken`, `RefreshToken` value objects
- **Application Layer**: 
  - `LoginCommand` with `LoginCommandHandler`
  - `RefreshTokenCommand` with `RefreshTokenCommandHandler`
  - `LogoutCommand` with `LogoutCommandHandler`
  - `IJwtService` interface
- **Infrastructure Layer**: `JwtService` implementation using `System.IdentityModel.Tokens.Jwt`
- **API Layer**: AuthController with proper validation

### Libraries & Dependencies
- `System.IdentityModel.Tokens.Jwt` (v7.x) - JWT token handling
- `BCrypt.Net-Next` (v4.x) - Password hashing
- `FluentValidation` (v11.x) - Input validation

### Token Configuration
```json
{
  "Jwt": {
    "Secret": "[32+ character secret from env]",
    "Issuer": "AI-Coding-Factory-API",
    "Audience": "AI-Coding-Factory-Clients",
    "AccessTokenExpiryMinutes": 60,
    "RefreshTokenExpiryDays": 7
  }
}
```

### Security Considerations
1. JWT secret stored in environment variables only
2. HTTPS enforcement in production
3. Refresh token rotation on each use
4. Token blacklist for logout scenario
5. Rate limiting on authentication endpoints (see ACF-0006)

### Database Changes
- New table: `RefreshTokens` (Id, UserId, Token, ExpiresAt, CreatedAt, RevokedAt)
- Index on Token column for fast lookups

### Testing Strategy
- Unit tests: Token generation, validation, password hashing
- Integration tests: Full login → access resource → refresh → logout flow
- Security tests: Token tampering, expired tokens, invalid signatures

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| JWT secret exposed in code/logs | Low | Critical | Secret stored only in env vars; validation scripts scan for secrets |
| Token theft via XSS | Medium | High | HttpOnly cookies for refresh tokens; short access token lifetime |
| Brute force password attacks | Medium | High | Rate limiting implemented (ACF-0006); account lockout after 5 attempts |
| Refresh token replay attacks | Low | High | Token rotation on use; one-time use only |
| Time synchronization issues | Low | Medium | Use server-side token validation; allow 5-min clock skew |

## Dependencies

- **Blocks**: ACF-0006 (Rate Limiting - authentication endpoints need rate limiting)
- **Depends on**: ACF-0001 (Platform Governance - security baseline)

## Traceability Expectations

- **Tests**: 
  - Unit tests in `tests/ProjectName.UnitTests/Application/Auth/`
  - Integration tests in `tests/ProjectName.IntegrationTests/Api/Auth/`
  - All tests include `[Trait("Story", "ACF-0003")]`
  - Test names follow pattern: `ACF0003_<Scenario>_<ExpectedBehavior>`

- **Commits**:
  - Format: `ACF-0003: <description>`
  - Examples: 
    - `ACF-0003: Add JWT token generation service`
    - `ACF-0003: Implement token validation middleware`
    - `ACF-0003: Add integration tests for auth flow`

- **Documentation**:
  - `docs/architecture/adr/ADR-003-jwt-authentication.md` created
  - `docs/api/openapi.md` updated with auth endpoints
  - Security considerations documented

- **Release Notes**:
  - "ACF-0003: Implemented JWT-based authentication with refresh token support"

## Notes

- Consider adding 2FA in future iteration (ACF-00XX)
- Monitor token refresh patterns for anomaly detection
- Evaluate OAuth2/OpenID Connect for enterprise SSO integration
