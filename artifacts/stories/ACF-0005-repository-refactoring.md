---
id: ACF-0005
title: Refactor OrderRepository to use Specification pattern
type: Technical Debt
status: In Progress
owner: Developer Agent
story_points: 3
priority: Medium
---

# ACF-0005 - Refactor OrderRepository to use Specification pattern

## User Story

**As a** developer working on the Order module
**I want** to refactor OrderRepository to use the Specification pattern
**So that** query logic is reusable, testable, and follows Clean Architecture principles

## Technical Debt Context

### Current Problem
The `OrderRepository` currently has 12+ specialized methods for different query scenarios:
- `GetOrdersByCustomerIdAsync()`
- `GetOrdersByStatusAsync()`
- `GetOrdersByDateRangeAsync()`
- `GetOrdersByCustomerAndStatusAsync()`
- `GetPendingOrdersAsync()`
- `GetCompletedOrdersAsync()`
- `GetOrdersWithItemsAsync()`
- And 5 more variations...

This leads to:
1. **Code duplication** - Similar filtering logic scattered across methods
2. **Poor testability** - Hard to unit test query logic separately from repository
3. **Violation of Open/Closed Principle** - Adding new filters requires modifying repository
4. **Repository bloat** - Class has grown to 800+ lines
5. **Query optimization issues** - Each method loads data differently, causing N+1 problems

### Impact
- **Development velocity**: Adding new filters takes 2-3 days instead of 2-3 hours
- **Bug rate**: 3 production bugs in last 6 months related to incorrect query logic
- **Code maintainability**: Repository is most changed file (45 commits in last quarter)
- **Performance**: Multiple database round trips due to inconsistent eager loading

### Target State
Implement Specification pattern to:
1. Encapsulate query criteria in separate, reusable classes
2. Enable composition of complex queries from simple specifications
3. Support lazy evaluation and deferred execution
4. Make repository generic and focused on persistence only
5. Improve testability with isolated specification unit tests

## Acceptance Criteria

### Scenario 1: Specification Pattern Implementation
**Given** the current OrderRepository with multiple specialized methods
**When** the Specification pattern is implemented
**Then** the repository reduces to standard CRUD operations (GetById, GetAll, Add, Update, Delete)
**And** all query logic moves to Specification classes

### Scenario 2: Query Composition
**Given** multiple simple specifications (ByCustomer, ByStatus, ByDateRange)
**When** they are combined using AND/OR operators
**Then** complex queries can be built without modifying repository
**And** the composed query executes as a single database round trip

### Scenario 3: Backward Compatibility
**Given** existing code using old repository methods
**When** the refactoring is complete
**Then** all existing functionality continues to work (no breaking changes)
**And** obsolete methods are marked with `[Obsolete]` attribute with migration guidance

### Scenario 4: Performance Improvement
**Given** orders with related entities (Items, Customer)
**When** using specifications with eager loading configuration
**Then** data is loaded in a single query (no N+1 problems)
**And** query execution time improves by minimum 30%

### Scenario 5: Testability
**Given** a specification class (e.g., `PendingOrdersSpecification`)
**When** unit testing the specification
**Then** the criteria can be tested in isolation without database
**And** specifications have >80% unit test coverage

## Definition of Done

- [x] Specification base classes implemented in Domain layer
- [ ] OrderRepository refactored to use generic `IRepository<Order>`
- [ ] All 12+ specialized methods migrated to specifications
- [ ] 100% backward compatibility (no breaking changes)
- [ ] Unit tests for all specifications (>80% coverage)
- [ ] Integration tests verify correct query execution
- [ ] Performance benchmarks show >30% improvement
- [ ] ADR-005 created documenting the pattern choice
- [ ] Developer documentation updated with examples
- [ ] Traceability: All commits reference `ACF-0005`
- [ ] Code review approved by 2 reviewers
- [ ] No regression in existing Order module tests
- [ ] Obsolete methods marked with `[Obsolete]` and migration guide

## Technical Notes / Approach

### Architecture Overview

**Before (Current State):**
```csharp
public interface IOrderRepository
{
    Task<Order> GetByIdAsync(Guid id);
    Task<IReadOnlyList<Order>> GetOrdersByCustomerIdAsync(Guid customerId);
    Task<IReadOnlyList<Order>> GetOrdersByStatusAsync(OrderStatus status);
    Task<IReadOnlyList<Order>> GetOrdersByDateRangeAsync(DateTime start, DateTime end);
    Task<IReadOnlyList<Order>> GetOrdersByCustomerAndStatusAsync(Guid customerId, OrderStatus status);
    // ... 8 more methods
}
```

**After (Target State):**
```csharp
// Domain Layer - Specification contracts
public interface ISpecification<T>
{
    Expression<Func<T, bool>> Criteria { get; }
    List<Expression<Func<T, object>>> Includes { get; }
    List<string> IncludeStrings { get; }
    bool IsPagingEnabled { get; }
    int Take { get; }
    int Skip { get; }
}

// Generic repository (only CRUD)
public interface IRepository<T> where T : class
{
    Task<T> GetByIdAsync(Guid id);
    Task<IReadOnlyList<T>> ListAllAsync();
    Task<IReadOnlyList<T>> ListAsync(ISpecification<T> spec);
    Task<T> FirstOrDefaultAsync(ISpecification<T> spec);
    Task<int> CountAsync(ISpecification<T> spec);
    Task<bool> AnyAsync(ISpecification<T> spec);
    Task AddAsync(T entity);
    Task UpdateAsync(T entity);
    Task DeleteAsync(T entity);
}

// Specifications in Application Layer
public class OrdersByCustomerSpecification : Specification<Order>
{
    public OrdersByCustomerSpecification(Guid customerId)
    {
        Criteria = o => o.CustomerId == customerId;
        AddInclude(o => o.Items);
        AddInclude(o => o.Customer);
        ApplyOrderByDescending(o => o.OrderDate);
    }
}
```

### Implementation Steps

**Step 1: Create Specification Base Classes (Domain Layer)**
```csharp
public abstract class Specification<T>
{
    public Expression<Func<T, bool>> Criteria { get; protected set; }
    public List<Expression<Func<T, object>>> Includes { get; } = new();
    public List<string> IncludeStrings { get; } = new();
    public Expression<Func<T, object>> OrderBy { get; protected set; }
    public Expression<Func<T, object>> OrderByDescending { get; protected set; }
    public int Take { get; protected set; }
    public int Skip { get; protected set; }
    public bool IsPagingEnabled { get; protected set; }
    public bool IsTrackingEnabled { get; protected set; } = true;

    protected virtual void AddInclude(Expression<Func<T, object>> includeExpression)
        => Includes.Add(includeExpression);

    protected virtual void AddInclude(string includeString)
        => IncludeStrings.Add(includeString);

    protected virtual void ApplyPaging(int skip, int take)
    {
        Skip = skip;
        Take = take;
        IsPagingEnabled = true;
    }

    protected virtual void ApplyOrderBy(Expression<Func<T, object>> orderByExpression)
        => OrderBy = orderByExpression;

    protected virtual void ApplyOrderByDescending(Expression<Func<T, object>> orderByDescendingExpression)
        => OrderByDescending = orderByDescendingExpression;

    protected virtual void DisableTracking()
        => IsTrackingEnabled = false;
}
```

**Step 2: Create Specification Evaluator (Infrastructure Layer)**
```csharp
public class SpecificationEvaluator<T> where T : class
{
    public static IQueryable<T> GetQuery(IQueryable<T> inputQuery, ISpecification<T> specification)
    {
        var query = inputQuery;

        // Apply criteria
        if (specification.Criteria != null)
            query = query.Where(specification.Criteria);

        // Apply includes
        query = specification.Includes.Aggregate(query, (current, include) => current.Include(include));
        query = specification.IncludeStrings.Aggregate(query, (current, include) => current.Include(include));

        // Apply ordering
        if (specification.OrderBy != null)
            query = query.OrderBy(specification.OrderBy);
        else if (specification.OrderByDescending != null)
            query = query.OrderByDescending(specification.OrderByDescending);

        // Apply paging (must be last)
        if (specification.IsPagingEnabled)
            query = query.Skip(specification.Skip).Take(specification.Take);

        // Apply tracking
        if (!specification.IsTrackingEnabled)
            query = query.AsNoTracking();

        return query;
    }
}
```

**Step 3: Refactor Repository (Infrastructure Layer)**
```csharp
public class Repository<T> : IRepository<T> where T : class
{
    protected readonly ApplicationDbContext _context;

    public Repository(ApplicationDbContext context)
    {
        _context = context;
    }

    public virtual async Task<IReadOnlyList<T>> ListAsync(ISpecification<T> spec)
    {
        return await ApplySpecification(spec).ToListAsync();
    }

    public virtual async Task<int> CountAsync(ISpecification<T> spec)
    {
        return await ApplySpecification(spec).CountAsync();
    }

    private IQueryable<T> ApplySpecification(ISpecification<T> spec)
    {
        return SpecificationEvaluator<T>.GetQuery(_context.Set<T>().AsQueryable(), spec);
    }

    // ... other CRUD methods
}
```

**Step 4: Create Order Specifications (Application Layer)**
```csharp
public class PendingOrdersSpecification : Specification<Order>
{
    public PendingOrdersSpecification()
    {
        Criteria = o => o.Status == OrderStatus.Pending;
        AddInclude(o => o.Items);
        AddInclude(o => o.Customer);
        ApplyOrderByDescending(o => o.OrderDate);
    }
}

public class OrdersByCustomerSpecification : Specification<Order>
{
    public OrdersByCustomerSpecification(Guid customerId)
    {
        Criteria = o => o.CustomerId == customerId;
        AddInclude(o => o.Items);
        ApplyOrderByDescending(o => o.OrderDate);
    }
}

public class OrdersByDateRangeSpecification : Specification<Order>
{
    public OrdersByDateRangeSpecification(DateTime startDate, DateTime endDate)
    {
        Criteria = o => o.OrderDate >= startDate && o.OrderDate <= endDate;
        AddInclude(o => o.Items);
        AddInclude(o => o.Customer);
        ApplyOrderBy(o => o.OrderDate);
    }
}

// Composite specification example
public class CustomerPendingOrdersSpecification : Specification<Order>
{
    public CustomerPendingOrdersSpecification(Guid customerId)
    {
        Criteria = o => o.CustomerId == customerId && o.Status == OrderStatus.Pending;
        AddInclude(o => o.Items);
        ApplyOrderByDescending(o => o.OrderDate);
    }
}
```

**Step 5: Backward Compatibility (Gradual Migration)**
```csharp
public class OrderRepository : Repository<Order>, IOrderRepository
{
    private readonly IRepository<Order> _repository;

    public OrderRepository(ApplicationDbContext context) : base(context)
    {
    }

    // New way - using specifications
    public async Task<IReadOnlyList<Order>> GetOrdersAsync(ISpecification<Order> spec)
    {
        return await ListAsync(spec);
    }

    // Old methods - marked obsolete but still working
    [Obsolete("Use GetOrdersAsync(new OrdersByCustomerSpecification(customerId)) instead. Will be removed in v2.0")]
    public async Task<IReadOnlyList<Order>> GetOrdersByCustomerIdAsync(Guid customerId)
    {
        return await ListAsync(new OrdersByCustomerSpecification(customerId));
    }

    [Obsolete("Use GetOrdersAsync(new PendingOrdersSpecification()) instead. Will be removed in v2.0")]
    public async Task<IReadOnlyList<Order>> GetPendingOrdersAsync()
    {
        return await ListAsync(new PendingOrdersSpecification());
    }
}
```

### Testing Strategy

**Unit Tests for Specifications:**
```csharp
public class PendingOrdersSpecificationTests
{
    [Fact]
    [Trait("Story", "ACF-0005")]
    public void ACF0005_PendingOrdersSpecification_MatchesPendingOrders()
    {
        // Arrange
        var pendingOrder = new Order { Status = OrderStatus.Pending };
        var completedOrder = new Order { Status = OrderStatus.Completed };
        var spec = new PendingOrdersSpecification();

        // Act & Assert
        Assert.True(spec.Criteria.Compile()(pendingOrder));
        Assert.False(spec.Criteria.Compile()(completedOrder));
    }

    [Fact]
    [Trait("Story", "ACF-0005")]
    public void ACF0005_OrdersByCustomerSpecification_MatchesCorrectCustomer()
    {
        // Arrange
        var customerId = Guid.NewGuid();
        var order = new Order { CustomerId = customerId };
        var otherOrder = new Order { CustomerId = Guid.NewGuid() };
        var spec = new OrdersByCustomerSpecification(customerId);

        // Act & Assert
        Assert.True(spec.Criteria.Compile()(order));
        Assert.False(spec.Criteria.Compile()(otherOrder));
    }
}
```

**Performance Benchmarks:**
```csharp
[MemoryDiagnoser]
public class OrderRepositoryBenchmarks
{
    [Benchmark(Baseline = true)]
    public async Task OldRepository_MultipleQueries()
    {
        // Old way: Multiple round trips
        var orders = await _oldRepo.GetOrdersByCustomerIdAsync(customerId);
        foreach (var order in orders)
        {
            await _context.Entry(order).Collection(o => o.Items).LoadAsync();
        }
    }

    [Benchmark]
    public async Task NewRepository_WithSpecification()
    {
        // New way: Single query with eager loading
        var spec = new OrdersByCustomerSpecification(customerId);
        var orders = await _newRepo.ListAsync(spec);
    }
}
```

### Migration Guide for Developers

**Old Code:**
```csharp
var orders = await _orderRepository.GetOrdersByCustomerAndStatusAsync(customerId, OrderStatus.Pending);
```

**New Code:**
```csharp
var spec = new OrdersByCustomerSpecification(customerId)
    .And(new PendingOrdersSpecification());
var orders = await _orderRepository.ListAsync(spec);
```

Or use composite specification:
```csharp
var spec = new CustomerPendingOrdersSpecification(customerId);
var orders = await _orderRepository.ListAsync(spec);
```

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking changes in existing code | Medium | High | Gradual migration with obsolete attributes; maintain backward compatibility for 2 releases |
| Performance regression | Low | High | Comprehensive benchmarking before/after; query execution plan analysis |
| Complex specifications hard to understand | Medium | Medium | Developer documentation with examples; code review guidelines; training session |
| Repository test failures | Medium | High | Full regression test suite; integration tests for all query paths |
| Database query optimization issues | Low | High | SQL execution plan review; load testing with production-like data |
| Over-engineering (too abstract) | Low | Medium | Start with simple specifications; only add complexity when needed; YAGNI principle |

## Dependencies

- **Blocks**: None directly, but enables cleaner implementation of future features
- **Depends on**: ACF-0003 (JWT Authentication - Order queries may need user context)
- **Related**: Repository pattern skill (`net-repository-pattern`)

## Traceability Expectations

- **Tests**:
  - Unit tests in `tests/ProjectName.UnitTests/Application/Specifications/`
  - Integration tests in `tests/ProjectName.IntegrationTests/Infrastructure/Repositories/`
  - Performance benchmarks in `tests/ProjectName.PerformanceTests/`
  - All tests include `[Trait("Story", "ACF-0005")]`
  - Test names follow pattern: `ACF0005_<SpecificationName>_<Behavior>`

- **Commits**:
  - Format: `ACF-0005: <description>`
  - Examples:
    - `ACF-0005: Add Specification base classes`
    - `ACF-0005: Refactor OrderRepository to use specifications`
    - `ACF-0005: Create Order specifications (Pending, ByCustomer, ByDateRange)`
    - `ACF-0005: Add backward compatibility layer with Obsolete attributes`
    - `ACF-0005: Add performance benchmarks`

- **Documentation**:
  - `docs/architecture/adr/ADR-005-specification-pattern.md` created
  - `docs/modules/modules.md` updated with specification examples
  - Migration guide created for developers
  - Code comments in specification classes

- **Release Notes**:
  - "ACF-0005: Refactored OrderRepository to use Specification pattern - improved maintainability and query performance by 35%"

## Notes

- Consider using a library like `Ardalis.Specification` if team prefers not to maintain custom implementation
- Evaluate performance impact on complex queries with multiple includes
- Plan for gradual deprecation of old methods over 2-3 sprints
- Monitor for any query performance issues in production after deployment
- Consider adding specification caching for frequently used queries

## Technical Debt Metrics (Before/After)

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Repository LOC | 800+ | 150 | -81% |
| Methods in repository | 15 | 7 | -53% |
| Average query execution time | 245ms | 168ms | -31% |
| Unit test coverage | 62% | 87% | +25% |
| Cyclomatic complexity | 47 | 12 | -74% |
| Code duplication | 34% | 5% | -85% |
