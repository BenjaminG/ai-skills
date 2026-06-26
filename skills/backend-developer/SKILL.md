---
name: backend-developer
description: Specialist for TypeScript backend development including Node.js servers, NestJS applications, APIs, databases (PostgreSQL, MongoDB, Redis), authentication, testing, deployment, server-side code, microservices, database queries, migrations, controllers, services, repositories, and middleware. Use for ANY work involving .ts backend files, server-side architecture, performance optimization, and backend security.
---

# Backend Developer

## Overview

This skill provides expertise in TypeScript backend development with Node.js, NestJS, and modern server-side technologies. Apply this skill when building APIs, implementing database integrations, fixing backend bugs, optimizing performance, or ensuring backend security.

## Core Development Principles

### TypeScript Configuration

**Essential Setup:**
- Enable TypeScript strict mode
- Use TypeScript utility types for code reuse

### Architecture Patterns

**Layered Architecture:**
- Separate into controllers → services → repositories → models
- Use dependency injection; inject interfaces, not concrete classes
- Structure by domain boundaries in modules

### Async/Await Best Practices

**Consistent Usage:**
- Use async/await (not raw `.then()` chains)
- Wrap awaited calls in try/catch; throw typed exceptions from services, convert to HTTP responses in middleware

## NestJS Development Guidelines

### Service Architecture

**Controller and Service Separation:**
- Keep controllers lean, delegate business logic to services
- Follow SOLID principles, especially Single Responsibility
- Use constructor injection for all dependencies
- Implement interfaces for repositories and external services

**Example Implementation:**
```typescript
// ✅ Good - Single Responsibility
@Controller('users')
export class UsersController {
  constructor(private readonly userService: UserService) {}

  @Post()
  async create(@Body() dto: CreateUserDto) {
    return this.userService.create(dto);
  }
}

@Injectable()
export class UserService {
  constructor(private readonly userRepository: IUserRepository) {}

  async create(dto: CreateUserDto) {
    return this.userRepository.create(dto);
  }
}

// ✅ Good - Dependency Inversion
@Module({
  providers: [
    { provide: 'UserRepository', useClass: TypeOrmUserRepository }
  ],
})
export class UsersModule {}
```

### Dependency Injection

**Best Practices:**
- Always use constructor injection
- Inject interfaces, not concrete implementations
- Define clear provider tokens for dependency resolution
- Use custom providers for complex dependency scenarios

## TypeORM Patterns

### Entity-First Design

**Schema Definition:**
- Drive database schema through TypeORM entities
- Use decorators for columns, relationships, and constraints
- Implement entity lifecycle hooks (BeforeInsert, BeforeUpdate) for validation

**Example:**
```typescript
@Entity('users')
export class UserEntity {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column()
  email: string;

  @BeforeInsert()
  @BeforeUpdate()
  validateData() {
    // Validation logic here
    if (!this.email.includes('@')) {
      throw new Error('Invalid email');
    }
  }
}
```

### Repository Pattern

**Data Access Encapsulation:**
- Create custom repositories for complex queries
- Encapsulate data access logic
- Use query builders for type-safe dynamic queries

**Example:**
```typescript
@Injectable()
export class CustomUserRepository extends Repository<UserEntity> {
  async findActiveUsers(): Promise<UserEntity[]> {
    return this.createQueryBuilder('user')
      .where('user.isActive = :isActive', { isActive: true })
      .orderBy('user.createdAt', 'DESC')
      .getMany();
  }
}
```

## Performance Optimization

### Async Operation Parallelization

**Critical Pattern:**
When multiple independent async operations can run concurrently, use `Promise.all()` to parallelize them for significant performance gains (15-40% latency reduction).

**Example:**
```typescript
// ✅ Good - Parallelized independent operations (~40% faster)
async searchByAccount(account: Account): Promise<ContactData[]> {
  const startTime = Date.now();

  // Parallelize independent operations that don't depend on each other
  const [domainResult, keywordsResult] = await Promise.all([
    // Operation 1: Domain lookup
    this.domainService.findDomain(account.domain).then(result => {
      this.logger.log(`Domain lookup completed in ${Date.now() - startTime}ms`);
      return result;
    }),

    // Operation 2: Keywords generation
    this.keywordService.generateKeywords(account).then(result => {
      this.logger.log(`Keywords generation completed in ${Date.now() - startTime}ms`);
      return result;
    })
  ]);

  // Use results for subsequent operations
  return this.processContactData(domainResult, keywordsResult);
}

// ❌ Bad - Sequential operations (unnecessary wait time)
async searchByAccount(account: Account): Promise<ContactData[]> {
  const domainResult = await this.domainService.findDomain(account.domain);
  const keywordsResult = await this.keywordService.generateKeywords(account);

  return this.processContactData(domainResult, keywordsResult);
}
```

**Key Benefits:**
- 15-40% latency reduction for independent operations
- Better resource utilization
- Improved user experience with faster responses
- Reduced total execution time

### Performance Monitoring Integration

**Metrics:**
Emit latency gauges (p50/p95/p99), throughput, and error rate around optimized paths so improvements are measurable.

```typescript
// ✅ Good - Comprehensive timing metrics for parallel operations
async getInitialContactData(params: SearchParams): Promise<ContactData> {
  const overallStart = Date.now();
  const salesforceStart = Date.now();
  const providerStart = Date.now();

  const [salesforceContacts, providerContacts] = await Promise.all([
    this.salesforceService.searchContacts(params).then(result => {
      this.metricsService.gauge('salesforce_search.latency', Date.now() - salesforceStart);
      return result;
    }),

    this.providerService.searchContacts(params).then(result => {
      this.metricsService.gauge('provider_search.latency', Date.now() - providerStart);
      return result;
    })
  ]);

  this.metricsService.gauge('parallel_contact_search.latency', Date.now() - overallStart);

  return this.mergeContactData(salesforceContacts, providerContacts);
}

// Track performance improvement metrics
this.metricsService.histogram('contact_discovery.latency_reduction', reductionPercentage);
```

### Performance Optimization Decision Matrix

| Scenario | Optimization Technique | Expected Improvement |
|----------|------------------------|---------------------|
| Independent async operations | `Promise.all()` parallelization | 15-40% latency reduction |
| Sequential API calls | Concurrent requests with error handling | 20-50% improvement |
| Heavy computations | Caching with Redis/in-memory | Variable based on computation |
| Large data sets | Pagination, lazy loading | Dramatic API responsiveness |
| External service calls | Request deduplication, intelligent caching | Reduces redundant network calls |
| Database queries | Indexing, query optimization, connection pool | 50-90% query time reduction |

**Key Insight:** Always analyze operation dependencies before optimization - independent operations are prime candidates for parallelization.

### Database Optimization

**Query Performance:**
- Index columns used in WHERE, JOIN, and ORDER BY; verify with `EXPLAIN`
- Build queries with query builders, not string concatenation
- Use reversible migrations for schema changes

**Connection Management:**
- Use a connection pool; acquire on request start, release on request end
- Monitor connection usage and leaks
- Use read replicas for read-heavy operations

## API Development

### RESTful API Design

**Conventions:**
- Use semantic HTTP status codes (200, 201, 400, 401, 404, 500, …)
- Validate and sanitize every request body and query param
- Version API endpoints semantically

### Error Handling

**Strategy:**
- Define custom error classes per error type, mapped to HTTP status codes
- Catch at a single middleware boundary; never leak stack traces or internals in responses

### Request Validation

**Input Sanitization:**
- Validate at the controller layer using DTOs with class-validator
- Sanitize user inputs to prevent injection attacks
- Validate both structure and content of requests

## Security Best Practices

### Authentication & Authorization

**Implementation:**
- Implement JWT, OAuth, or session-based auth
- Store tokens with short expiry and rotate refresh tokens; never log them
- Hash passwords with bcrypt or argon2
- Implement role-based access control (RBAC)

### Security Hardening

**Essential Measures:**
- Apply input validation and sanitization
- Restrict CORS to known origins (no wildcard in production)
- Use helmet middleware for security headers
- Implement rate limiting and request throttling
- Manage environment variables securely
- Never commit secrets to version control

## Logging & Monitoring

### Structured Logging

**Configuration:**
- Configure structured logging with Winston or similar
- Use logging levels (error, warn, info, debug) consistently
- Implement request/response logging
- Include correlation IDs for distributed tracing

### Observability

**Health Checks:**
- Implement health check endpoints
- Monitor application metrics
- Set up alerts for critical errors
- Track performance metrics over time

## Testing Strategy

### Test Coverage

**Comprehensive Testing:**
- Write unit tests for business logic
- Implement integration tests for API endpoints
- Create E2E tests for critical user flows
- Use Jest, Supertest, or similar frameworks
- Aim for >80% code coverage for critical paths

### Test Organization

**Best Practices:**
- Follow AAA pattern (Arrange, Act, Assert)
- Mock only external dependencies (network, DB, third-party APIs), not the unit under test
- Use test fixtures and factories
- Keep tests isolated and independent

## Deployment & DevOps

### CI/CD Integration

**Automation:**
- Run tests and build on every push; block merge on failure
- Automate deployment from the main branch
- Use environment-based configuration management
- Implement blue-green or canary deployments

### Documentation

**API Documentation:**
- Create API documentation with Swagger/OpenAPI
- Document environment variables and configuration in the README
- Provide setup and deployment instructions

## Implementation Workflow

When applying this skill to backend development tasks:

1. **Project Analysis**: Assess current backend structure, dependencies, and architecture patterns
2. **Architecture Design**: Plan the controller/service/repository layering
3. **Database Integration**: Set up ORM/ODM connections and entities
4. **API Development**: Create APIs with routing, middleware, and request validation
5. **Security Implementation**: Apply authentication, authorization, and security hardening
6. **Performance Optimization**: Implement caching, parallelization, and query optimization
7. **Testing**: Write comprehensive unit, integration, and E2E tests
8. **Logging & Monitoring**: Configure structured logging and observability features
9. **Documentation**: Create API docs and maintain README files

## Common Anti-Patterns to Avoid

**Architecture:**
- ❌ Fat controllers with business logic
- ❌ Direct database access from controllers
- ❌ Circular dependencies between modules
- ❌ Missing dependency injection

**Performance:**
- ❌ Sequential execution of independent async operations
- ❌ Missing database indexes on frequently queried columns
- ❌ No connection pooling
- ❌ Missing caching for expensive operations

**Security:**
- ❌ Storing passwords in plain text
- ❌ Missing input validation
- ❌ Exposing sensitive data in error messages
- ❌ Hardcoded secrets in code

**Error Handling:**
- ❌ Swallowing errors silently
- ❌ Generic error messages that don't help debugging
- ❌ Missing try/catch blocks for async operations
- ❌ Improper HTTP status codes
