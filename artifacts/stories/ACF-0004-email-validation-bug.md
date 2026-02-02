---
id: ACF-0004
title: Fix email validation regex in user registration
type: Bug Fix
status: Done
owner: Developer Agent
story_points: 2
priority: High
---

# ACF-0004 - Fix email validation regex in user registration

## User Story

**As a** user registering an account
**I want** the system to properly validate my email address format
**So that** I receive confirmation emails and can successfully complete registration

## Bug Description

### Current Behavior (Bug)
The current email validation regex in `RegisterUserCommandValidator` allows invalid email formats:
- Accepts emails without TLD (e.g., "user@domain")
- Accepts emails with consecutive dots (e.g., "user..name@domain.com")
- Accepts emails starting with dots (e.g., ".user@domain.com")
- Fails to reject emails with spaces (e.g., "user name@domain.com")

### Expected Behavior
Email validation should:
- Require valid format: `local-part@domain.tld`
- Reject consecutive dots in local-part
- Reject leading/trailing dots in local-part
- Reject spaces anywhere in email
- Require minimum 2-character TLD
- Accept common valid formats (e.g., "user+tag@domain.com", "user.name@domain.co.uk")

### Impact
- 15 users reported registration issues in the past week
- Support tickets increased by 40% related to email delivery failures
- Invalid emails in database causing bounce-backs from email service provider

## Acceptance Criteria

### Scenario 1: Valid Email Acceptance
**Given** a user enters a valid email address "john.doe@example.com"
**When** the registration form is submitted
**Then** the email is accepted and validation passes

### Scenario 2: Missing TLD Rejection
**Given** a user enters "user@domain" (no TLD)
**When** the registration form is submitted
**Then** validation fails with message "Invalid email format"

### Scenario 3: Consecutive Dots Rejection
**Given** a user enters "user..name@domain.com"
**When** the registration form is submitted
**Then** validation fails with message "Invalid email format"

### Scenario 4: Plus Sign Acceptance
**Given** a user enters a valid email with plus sign "user+tag@example.com"
**When** the registration form is submitted
**Then** the email is accepted and validation passes

### Scenario 5: Edge Cases
**Given** various edge case emails:
- "user.name+tag@example.co.uk" (valid, accepted)
- "user@sub.domain.com" (valid, accepted)
- "user name@example.com" (invalid, rejected with spaces)
- "user@example.c" (invalid, rejected TLD too short)

## Definition of Done

- [x] Email validation regex updated in `RegisterUserCommandValidator`
- [x] Unit tests for email validation (>80% coverage, 20+ test cases)
- [x] Integration tests for registration endpoint with various email formats
- [x] Existing invalid emails in database identified and cleaned
- [x] Error messages updated to be user-friendly and specific
- [x] Validation logic documented in code comments
- [x] No regression in other validation rules (password, name, etc.)
- [x] Traceability: All commits reference `ACF-0004`
- [x] Code review approved
- [x] Deployed to production
- [x] Support team notified of the fix

## Technical Notes / Approach

### Current Implementation (Buggy)
```csharp
// Current regex (BUGGY)
RuleFor(x => x.Email)
    .NotEmpty()
    .EmailAddress(); // Built-in validator too permissive
```

### Fixed Implementation
Using a more robust validation approach:

```csharp
// Fixed implementation
RuleFor(x => x.Email)
    .NotEmpty().WithMessage("Email is required")
    .MaximumLength(254).WithMessage("Email too long")
    .Must(BeValidEmail).WithMessage("Invalid email format");

private static bool BeValidEmail(string email)
{
    if (string.IsNullOrWhiteSpace(email))
        return false;
    
    // RFC 5322 compliant regex (simplified practical version)
    var regex = new Regex(@"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$");
    
    if (!regex.IsMatch(email))
        return false;
    
    // Additional manual checks for edge cases
    var localPart = email.Split('@')[0];
    var domain = email.Split('@')[1];
    
    // Check for consecutive dots in local part
    if (localPart.Contains(".."))
        return false;
    
    // Check for leading/trailing dots in local part
    if (localPart.StartsWith(".") || localPart.EndsWith("."))
        return false;
    
    // Check for spaces anywhere
    if (email.Contains(" "))
        return false;
    
    // Minimum 2-char TLD
    var tld = domain.Substring(domain.LastIndexOf('.') + 1);
    if (tld.Length < 2)
        return false;
    
    return true;
}
```

### Alternative: FluentValidation Email Validation
Consider using `FluentValidation.Validators.EmailValidator` with stricter mode:

```csharp
RuleFor(x => x.Email)
    .NotEmpty()
    .EmailAddress(EmailValidationMode.Net4xRegex); // Stricter regex
```

### Testing Strategy
Comprehensive test cases covering:

**Valid Emails (should pass):**
- simple@example.com
- very.common@example.com
- disposable.style.stripe.with+symbol@example.com
- other.email-with-hyphen@example.com
- user.name+tag+sorting@example.com
- x@example.com (one-letter local-part)
- user@localserver (no TLD - might be valid in intranet)
- user@example.co.uk (multiple subdomains)

**Invalid Emails (should fail):**
- plainaddress (no @ symbol)
- @missinglocalpart.com (no local part)
- user@.missingtld. (invalid domain)
- user@domain (no TLD)
- user..name@example.com (consecutive dots)
- .user@example.com (leading dot)
- user.@example.com (trailing dot)
- user name@example.com (spaces)
- user@example.c (TLD too short)
- user@example.com. (trailing dot in domain)
- user@.example.com (leading dot in domain)
- (empty string)
- user@example@example.com (multiple @)

### Database Cleanup
```sql
-- Identify potentially invalid emails
SELECT Email, CreatedAt 
FROM Users 
WHERE Email NOT LIKE '%@%.%' 
   OR Email LIKE '%..%'
   OR Email LIKE '% %';

-- Update or flag for manual review
UPDATE Users 
SET EmailStatus = 'Invalid - Needs Review'
WHERE Email NOT LIKE '%@%.%' 
   OR Email LIKE '%..%'
   OR Email LIKE '% %';
```

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Regex rejects valid emails | Low | High | Comprehensive test suite with 20+ valid email formats; manual QA testing with real email addresses |
| Database migration fails | Very Low | Medium | Use soft flag (EmailStatus) instead of hard deletion; backup before migration |
| Regression in other validators | Low | Medium | Full regression test of registration endpoint; validate all other fields still work |

## Dependencies

- **Blocks**: None
- **Depends on**: ACF-0003 (JWT Authentication - registration endpoint needs to work for auth flow)
- **Related**: ACF-0006 (Rate Limiting - registration endpoint will need rate limiting)

## Traceability Expectations

- **Tests**:
  - Unit tests in `tests/ProjectName.UnitTests/Application/Validators/EmailValidationTests.cs`
  - Integration tests in `tests/ProjectName.IntegrationTests/Api/Auth/RegistrationTests.cs`
  - All tests include `[Trait("Story", "ACF-0004")]`
  - Test names follow pattern: `ACF0004_<EmailType>_<ExpectedResult>`
  - Example: `ACF0004_ValidEmailWithPlusSign_Accepted`, `ACF0004_EmailWithConsecutiveDots_Rejected`

- **Commits**:
  - Format: `ACF-0004: <description>`
  - Examples:
    - `ACF-0004: Fix email regex to reject consecutive dots`
    - `ACF-0004: Add comprehensive email validation unit tests`
    - `ACF-0004: Identify and flag invalid emails in database`

- **Documentation**:
  - Code comments explain regex and validation rules
  - API documentation updated with validation rules
  - Runbook updated with email validation requirements

- **Release Notes**:
  - "ACF-0004: Fixed email validation to properly reject malformed addresses (affecting 15+ users)"

## Notes

- Consider implementing email verification workflow in future iteration to catch typos
- Monitor support tickets after deployment to confirm fix effectiveness
- Evaluate using a validation library like `EmailValidation` NuGet package for more robust handling
- Document regex pattern in team wiki for future reference

## Root Cause Analysis

The bug originated from using the default `EmailAddress` validator which uses a permissive .NET regex. This was discovered during user registration testing when multiple invalid emails were accepted.

**Lesson Learned**: Always validate with real-world data and edge cases, not just happy path scenarios.
