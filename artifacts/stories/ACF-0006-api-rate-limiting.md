---
id: ACF-0006
title: Add rate limiting to public API endpoints
type: Security Enhancement
status: Proposed
owner: Security Agent
story_points: 5
priority: High
---

# ACF-0006 - Add rate limiting to public API endpoints

## User Story

**As a** system administrator
**I want** to implement rate limiting on public API endpoints
**So that** the application is protected from abuse, DDoS attacks, and resource exhaustion

## Security Context

### Threat Model
The public API endpoints are vulnerable to several attack vectors:
1. **Brute Force Attacks** - Unlimited login attempts enable credential stuffing
2. **DDoS Attacks** - Unrestricted request volume can overwhelm the API
3. **Resource Exhaustion** - Expensive queries can be repeated indefinitely
4. **Scraping/Data Harvesting** - Bots can enumerate data without restrictions
5. **Cost Attacks** - API abuse can inflate infrastructure costs (CPU, bandwidth, DB)

### Current Vulnerabilities
- No rate limiting on `/api/auth/login` (brute force risk)
- No rate limiting on `/api/orders` endpoints (data scraping risk)
- No rate limiting on `/api/users` endpoints (enumeration risk)
- Failed requests consume same resources as successful ones
- No client identification or blacklisting capability

### Compliance Requirements
- **OWASP API Security Top 10**: API4:2019 - Lack of Resources & Rate Limiting
- **PCI DSS**: Requirement 6.5.10 - Broken authentication (brute force protection)
- **GDPR**: Article 32 - Security of processing (technical measures)
- **SOC 2**: CC6.1 - Security infrastructure and software

### Business Impact
Without rate limiting:
- **Availability**: API can be taken offline by simple script attacks
- **Security**: Credentials can be brute-forced at scale
- **Performance**: Legitimate users experience degraded service
- **Cost**: Infrastructure costs unpredictable due to abuse
- **Reputation**: Security incidents damage customer trust

## Acceptance Criteria

### Scenario 1: IP-Based Rate Limiting (Anonymous Users)
**Given** an unauthenticated user making requests from a single IP address
**When** the user exceeds 100 requests per minute
**Then** subsequent requests return HTTP 429 (Too Many Requests)
**And** the response includes `Retry-After` header with seconds until next window

### Scenario 2: User-Based Rate Limiting (Authenticated Users)
**Given** an authenticated user with a valid JWT token
**When** the user exceeds 1000 requests per minute per user ID
**Then** subsequent requests return HTTP 429
**And** rate limits are tracked per-user, not per-IP

### Scenario 3: Endpoint-Specific Limits
**Given** different API endpoints with varying sensitivity
**When** accessing high-risk endpoints (`/api/auth/login`)
**Then** stricter limits apply: 5 attempts per minute per IP
**And** normal endpoints maintain 100 req/min limit

### Scenario 4: Rate Limit Headers
**Given** any API request (successful or limited)
**When** the response is returned
**Then** headers include:
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Remaining requests in window
- `X-RateLimit-Reset`: Unix timestamp when limit resets

### Scenario 5: Distributed Rate Limiting
**Given** the application running on multiple server instances
**When** rate limits are enforced
**Then** limits apply across all instances (shared state via Redis)
**And** a user cannot bypass limits by hitting different servers

### Scenario 6: Whitelist/Blacklist Support
**Given** specific IP addresses or API keys
**When** whitelisted: unlimited requests allowed
**And** when blacklisted: immediate HTTP 429 (no retry)
**And** configuration can be updated without deployment

## Definition of Done

- [ ] Rate limiting middleware implemented and registered in pipeline
- [ ] IP-based rate limiting for anonymous users (100 req/min)
- [ ] User-based rate limiting for authenticated users (1000 req/min)
- [ ] Endpoint-specific limits configured (auth: 5 req/min, general: 100 req/min)
- [ ] Distributed rate limiting with Redis backend
- [ ] Rate limit headers included in all responses (`X-RateLimit-*`)
- [ ] HTTP 429 responses with `Retry-After` header
- [ ] Whitelist/Blacklist configuration support
- [ ] Unit tests for rate limiting logic (>80% coverage)
- [ ] Integration tests for distributed rate limiting
- [ ] Performance tests verify <5ms overhead per request
- [ ] Security review completed (OWASP compliance)
- [ ] ADR-006 created documenting rate limiting strategy
- [ ] Runbook updated with rate limit tuning procedures
- [ ] Traceability: All commits reference `ACF-0006`
- [ ] Monitoring dashboards for rate limit hits/alerts
- [ ] Code review approved by Security team
- [ ] Staged rollout (5% → 25% → 100% traffic)

## Technical Notes / Approach

### Rate Limiting Strategy

**Multi-Tier Approach:**
1. **Global Limits** - Prevent total API overload (10,000 req/min per instance)
2. **IP-Based Limits** - Stop simple distributed attacks (100 req/min per IP)
3. **User-Based Limits** - Prevent authenticated abuse (1000 req/min per user)
4. **Endpoint-Specific Limits** - Protect sensitive operations:
   - `/api/auth/login`: 5 req/min per IP (brute force protection)
   - `/api/auth/refresh`: 10 req/min per user
   - `/api/users/registration`: 3 req/min per IP
   - `/api/orders/**`: 100 req/min per user
   - `/api/admin/**`: 50 req/min per admin user

### Implementation Options

**Option A: AspNetCoreRateLimit Package (Recommended)**
```csharp
// NuGet: AspNetCoreRateLimit

// Configuration in appsettings.json
{
  "IpRateLimiting": {
    "EnableEndpointRateLimiting": true,
    "StackBlockedRequests": false,
    "RealIpHeader": "X-Real-IP",
    "ClientIdHeader": "X-ClientId",
    "HttpStatusCode": 429,
    "GeneralRules": [
      {
        "Endpoint": "*",
        "Period": "1m",
        "Limit": 100
      },
      {
        "Endpoint": "post:/api/auth/login",
        "Period": "1m",
        "Limit": 5
      }
    ]
  },
  "ClientRateLimiting": {
    "ClientIdHeader": "Authorization",
    "ClientIdParser": "jwt_sub",
    "GeneralRules": [
      {
        "Endpoint": "*",
        "Period": "1m",
        "Limit": 1000
      }
    ]
  }
}
```

**Option B: Custom Middleware with Redis**
```csharp
public class RateLimitingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly IConnectionMultiplexer _redis;
    private readonly ILogger<RateLimitingMiddleware> _logger;

    public async Task InvokeAsync(HttpContext context)
    {
        var clientId = GetClientIdentifier(context);
        var endpoint = context.Request.Path;
        var limit = GetRateLimit(endpoint);
        
        var key = $"rate_limit:{clientId}:{endpoint}";
        var current = await _redis.GetDatabase().StringIncrementAsync(key);
        
        if (current == 1)
        {
            await _redis.GetDatabase().KeyExpireAsync(key, TimeSpan.FromMinutes(1));
        }
        
        if (current > limit)
        {
            context.Response.StatusCode = 429;
            context.Response.Headers.Add("Retry-After", "60");
            await context.Response.WriteAsync("Rate limit exceeded");
            return;
        }
        
        await _next(context);
    }
}
```

### Recommended Implementation

**Step 1: Install Package**
```bash
dotnet add package AspNetCoreRateLimit --version 5.0.0
dotnet add package Microsoft.Extensions.Caching.StackExchangeRedis
```

**Step 2: Configure Rate Limiting**
```csharp
// Program.cs
builder.Services.AddMemoryCache();
builder.Services.Configure<IpRateLimitOptions>(options =>
{
    options.EnableEndpointRateLimiting = true;
    options.StackBlockedRequests = false;
    options.RealIpHeader = "X-Real-IP";
    options.ClientIdHeader = "X-ClientId";
    options.HttpStatusCode = 429;
    options.IpWhitelist = new List<string> { "127.0.0.1", "::1" };
    options.GeneralRules = new List<RateLimitRule>
    {
        // Global IP-based limit
        new RateLimitRule
        {
            Endpoint = "*",
            Limit = 100,
            Period = "1m"
        },
        // Auth endpoints - strict limits
        new RateLimitRule
        {
            Endpoint = "post:/api/auth/login",
            Limit = 5,
            Period = "1m"
        },
        new RateLimitRule
        {
            Endpoint = "post:/api/auth/refresh",
            Limit = 10,
            Period = "1m"
        },
        // Registration - very strict
        new RateLimitRule
        {
            Endpoint = "post:/api/users",
            Limit = 3,
            Period = "1m"
        }
    };
});

builder.Services.AddSingleton<IRateLimitConfiguration, RateLimitConfiguration>();

// Distributed storage with Redis
builder.Services.AddSingleton<IConnectionMultiplexer>(sp =>
    ConnectionMultiplexer.Connect(builder.Configuration.GetConnectionString("Redis")));

builder.Services.AddSingleton<IClientPolicyStore, DistributedCacheClientPolicyStore>();
builder.Services.AddSingleton<IRateLimitCounterStore, DistributedCacheRateLimitCounterStore>();
builder.Services.AddSingleton<IIpPolicyStore, DistributedCacheIpPolicyStore>();
```

**Step 3: Add Middleware**
```csharp
// Program.cs - Configure middleware pipeline
app.UseIpRateLimiting();
app.UseClientRateLimiting();

app.MapControllers();
```

**Step 4: Custom Rate Limit Store (Redis-backed)**
```csharp
public class DistributedCacheRateLimitCounterStore : IRateLimitCounterStore
{
    private readonly IConnectionMultiplexer _redis;
    private readonly ILogger<DistributedCacheRateLimitCounterStore> _logger;

    public DistributedCacheRateLimitCounterStore(
        IConnectionMultiplexer redis,
        ILogger<DistributedCacheRateLimitCounterStore> logger)
    {
        _redis = redis;
        _logger = logger;
    }

    public async Task<bool> ExistsAsync(string id, CancellationToken cancellationToken = default)
    {
        return await _redis.GetDatabase().KeyExistsAsync(id);
    }

    public async Task<RateLimitCounter?> GetAsync(string id, CancellationToken cancellationToken = default)
    {
        var value = await _redis.GetDatabase().StringGetAsync(id);
        if (value.IsNullOrEmpty) return null;
        
        return JsonSerializer.Deserialize<RateLimitCounter>(value!);
    }

    public async Task RemoveAsync(string id, CancellationToken cancellationToken = default)
    {
        await _redis.GetDatabase().KeyDeleteAsync(id);
    }

    public async Task SetAsync(string id, RateLimitCounter? entry, TimeSpan? expirationTime = null, 
        CancellationToken cancellationToken = default)
    {
        if (entry == null) return;

        var value = JsonSerializer.Serialize(entry);
        await _redis.GetDatabase().StringSetAsync(id, value, expirationTime);
    }
}
```

**Step 5: Custom Client Identifier (JWT-based)**
```csharp
public class JwtClientIdParser : IClientIdParser
{
    public string ParseClientId(HttpContext context)
    {
        var authHeader = context.Request.Headers["Authorization"].FirstOrDefault();
        if (string.IsNullOrEmpty(authHeader) || !authHeader.StartsWith("Bearer "))
        {
            return context.Connection.RemoteIpAddress?.ToString() ?? "unknown";
        }

        var token = authHeader.Substring("Bearer ".Length);
        var handler = new JwtSecurityTokenHandler();
        
        try
        {
            var jwtToken = handler.ReadJwtToken(token);
            var userId = jwtToken.Claims.FirstOrDefault(c => c.Type == ClaimTypes.NameIdentifier)?.Value;
            return userId ?? context.Connection.RemoteIpAddress?.ToString() ?? "unknown";
        }
        catch
        {
            return context.Connection.RemoteIpAddress?.ToString() ?? "unknown";
        }
    }
}
```

### Testing Strategy

**Unit Tests:**
```csharp
public class RateLimitingTests
{
    [Fact]
    [Trait("Story", "ACF-0006")]
    public async Task ACF0006_ExceedIpLimit_Returns429()
    {
        // Arrange
        var client = _factory.CreateClient();
        
        // Act - Make 101 requests
        for (int i = 0; i < 100; i++)
        {
            await client.GetAsync("/api/orders");
        }
        
        var response = await client.GetAsync("/api/orders");
        
        // Assert
        Assert.Equal(429, (int)response.StatusCode);
        Assert.True(response.Headers.Contains("Retry-After"));
    }

    [Fact]
    [Trait("Story", "ACF-0006")]
    public async Task ACF0006_RateLimitHeaders_PresentInAllResponses()
    {
        // Arrange
        var client = _factory.CreateClient();
        
        // Act
        var response = await client.GetAsync("/api/orders");
        
        // Assert
        Assert.True(response.Headers.Contains("X-RateLimit-Limit"));
        Assert.True(response.Headers.Contains("X-RateLimit-Remaining"));
        Assert.True(response.Headers.Contains("X-RateLimit-Reset"));
    }
}
```

**Load Testing:**
```bash
# Using k6 for load testing
k6 run --vus 100 --duration 60s rate-limit-test.js

// rate-limit-test.js
import http from 'k6/http';
import { check } from 'k6';

export default function () {
    const res = http.get('https://api.example.com/api/orders');
    
    check(res, {
        'status is 200 or 429': (r) => r.status === 200 || r.status === 429,
        'rate limit headers present': (r) => 
            r.headers['X-RateLimit-Limit'] !== undefined,
    });
}
```

### Monitoring & Alerting

**Metrics to Track:**
- Rate limit hits per endpoint (counter)
- Rate limit latency (histogram)
- Blocked requests by IP/user (top 10)
- Redis cache hit/miss ratio

**Alerts:**
- High rate of 429s (>100/min) - potential DDoS
- Redis connection failures - rate limiting degraded
- Single IP hitting limits repeatedly - possible attack

**Dashboard Query (Prometheus):**
```promql
# Rate limit hits
rate(ratelimit_hits_total[5m])

# Blocked requests by status
rate(ratelimit_blocked_total[5m])

# Redis operations
rate(redis_operations_total{operation="rate_limit_check"}[5m])
```

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| False positives (legitimate users blocked) | Medium | High | High limits (1000/min for auth users); whitelist for known good IPs; monitoring with quick response |
| Redis single point of failure | Medium | High | Redis Sentinel/Cluster for HA; fallback to in-memory cache if Redis unavailable |
| Performance overhead | Low | Medium | Benchmark tests <5ms overhead; Redis pipelining; async operations |
| Bypass via IP spoofing | Low | High | Use X-Forwarded-For carefully; validate IP chain; combine with user-based limits |
| Rate limit exhaustion attacks | Low | High | Global limits protect infrastructure; alerts on unusual patterns; WAF integration |
| Complexity in configuration | Medium | Low | Clear documentation; validation on startup; monitoring for misconfiguration |

## Rollout Strategy

**Phase 1: Shadow Mode (Week 1)**
- Enable rate limiting in logging-only mode
- Log what WOULD be blocked without actually blocking
- Analyze false positive rate
- Tune limits based on real traffic

**Phase 2: Soft Enforcement (Week 2)**
- Enable for 5% of traffic
- Monitor error rates and support tickets
- Adjust limits if needed
- Increase to 25% after 2 days

**Phase 3: Full Rollout (Week 3)**
- Enable for 100% of traffic
- Monitor dashboards closely
- Have rollback plan ready
- Document any edge cases

**Rollback Plan:**
```csharp
// Feature flag for quick disable
if (_featureFlags.IsEnabled("RateLimiting"))
{
    app.UseIpRateLimiting();
}
```

## Dependencies

- **Blocks**: ACF-0003 (JWT Authentication - rate limiting needs to identify authenticated users)
- **Depends on**: ACF-0001 (Platform Governance - security baseline)
- **Infrastructure**: Redis for distributed state
- **Related**: net-jwt-auth skill, net-observability skill

## Traceability Expectations

- **Tests**:
  - Unit tests in `tests/ProjectName.UnitTests/Infrastructure/RateLimiting/`
  - Integration tests in `tests/ProjectName.IntegrationTests/Api/RateLimitingTests.cs`
  - Load tests in `tests/ProjectName.PerformanceTests/RateLimitLoadTests.cs`
  - All tests include `[Trait("Story", "ACF-0006")]`
  - Test names: `ACF0006_<Scenario>_<ExpectedBehavior>`

- **Commits**:
  - Format: `ACF-0006: <description>`
  - Examples:
    - `ACF-0006: Add AspNetCoreRateLimit package and configuration`
    - `ACF-0006: Implement Redis-backed distributed rate limiting`
    - `ACF-0006: Add JWT-based client identification`
    - `ACF-0006: Add rate limiting integration tests`
    - `ACF-0006: Configure endpoint-specific limits for auth endpoints`

- **Documentation**:
  - `docs/architecture/adr/ADR-006-rate-limiting-strategy.md` created
  - `docs/operations/runbooks/rate-limit-tuning.md` created
  - API documentation updated with rate limit headers
  - Security runbook updated

- **Release Notes**:
  - "ACF-0006: Implemented multi-tier rate limiting with Redis - protects against brute force, DDoS, and resource exhaustion"

## Notes

- Consider implementing sliding window algorithm for more fair rate limiting
- Monitor for bypass attempts (multiple IPs, VPN rotation)
- Plan for API key-based rate limiting for future partner integrations
- Evaluate using a CDN/WAF (Cloudflare, AWS WAF) for additional layer of protection
- Consider geographic rate limiting for regions with high attack rates
- Document rate limits in API documentation for consumers
- Implement graceful degradation if rate limiting service fails

## Security Test Cases

**Brute Force Simulation:**
```bash
# Should be blocked after 5 attempts
for i in {1..10}; do
  curl -X POST https://api.example.com/api/auth/login \
    -d '{"email":"test@test.com","password":"wrong"}'
done
```

**Distributed Attack Simulation:**
```bash
# From multiple IPs - should still be limited per user
parallel -j 50 curl https://api.example.com/api/orders ::: {1..1000}
```
