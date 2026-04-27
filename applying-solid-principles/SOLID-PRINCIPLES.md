# SOLID Principles in Detail

A detailed explanation of the five SOLID principles. Each principle is described using contrasting bad and good examples.

## 📋 Table of Contents
1. [Single Responsibility Principle](#1-single-responsibility-principle)
2. [Open/Closed Principle](#2-openclosed-principle)
3. [Liskov Substitution Principle](#3-liskov-substitution-principle)
4. [Interface Segregation Principle](#4-interface-segregation-principle)
5. [Dependency Inversion Principle](#5-dependency-inversion-principle)

---

## 1. Single Responsibility Principle

### Definition
**Each class and function should have a single responsibility.**

Design so that there is only one "reason to change."

### Why It Matters
- **Better maintainability**: The scope of change is limited.
- **Easier to test**: You only need to test a single piece of functionality.
- **Reusability**: Components with clearly defined responsibilities are easier to reuse.

### ❌ Bad Example: A class with multiple responsibilities
```typescript
class User {
  name: string
  email: string

  // ❌ The User class is responsible for database operations
  saveToDatabase() {
    const db = new Database()
    db.insert('users', this)
  }

  // ❌ The User class is responsible for sending emails
  sendEmail(subject: string, body: string) {
    const emailService = new EmailService()
    emailService.send(this.email, subject, body)
  }

  // ❌ The User class is responsible for generating reports
  generateReport(): string {
    return `User Report: ${this.name} (${this.email})`
  }
}
```

**Problems**:
- The User class must be modified whenever the DB schema changes.
- The User class must be modified whenever email-sending logic changes.
- The User class must be modified whenever the report format changes.
- Tests are complex (you must mock the DB, email, and reporting).

### ✅ Good Example: Responsibilities separated
```typescript
// User entity: holds data only
class User {
  constructor(
    public readonly name: string,
    public readonly email: string
  ) {}
}

// Database responsibility extracted
class UserRepository {
  save(user: User): void {
    const db = new Database()
    db.insert('users', user)
  }

  findById(id: string): User | null {
    const db = new Database()
    return db.findOne('users', { id })
  }
}

// Email responsibility extracted
class UserEmailService {
  sendWelcomeEmail(user: User): void {
    const emailService = new EmailService()
    emailService.send(
      user.email,
      'Welcome!',
      `Hello ${user.name}, welcome to our service!`
    )
  }
}

// Report-generation responsibility extracted
class UserReportGenerator {
  generate(user: User): string {
    return `User Report: ${user.name} (${user.email})`
  }
}
```

**Improvements**:
- Each class has a single responsibility.
- The scope of change is limited.
- Tests are simpler (each class can be tested independently).
- Easier to reuse.

---

## 2. Open/Closed Principle

### Definition
**Software entities should be open for extension but closed for modification.**

When adding new functionality, extend existing code rather than modifying it.

### Why It Matters
- **Safety**: Because existing code is not modified, there is less risk of breaking existing behavior.
- **Extensibility**: New features are easy to add.
- **Maintainability**: You don't need to understand the existing code to extend it.

### ❌ Bad Example: Adding a new type requires modifying existing code
```typescript
class Shape {
  type: 'circle' | 'square' | 'rectangle'
  radius?: number
  side?: number
  width?: number
  height?: number
}

function getArea(shape: Shape): number {
  if (shape.type === 'circle') {
    return Math.PI * shape.radius! ** 2
  }
  if (shape.type === 'square') {
    return shape.side! ** 2
  }
  if (shape.type === 'rectangle') {
    return shape.width! * shape.height!
  }
  // To add a new shape (e.g. a triangle),
  // you must modify this function.
  throw new Error('Unknown shape type')
}
```

**Problems**:
- Every new shape forces you to change `getArea`.
- Each change risks breaking existing behavior.
- Test cases keep growing.

### ✅ Good Example: Extend through interfaces
```typescript
// Abstract through an interface
interface Shape {
  getArea(): number
}

class Circle implements Shape {
  constructor(private radius: number) {}

  getArea(): number {
    return Math.PI * this.radius ** 2
  }
}

class Square implements Shape {
  constructor(private side: number) {}

  getArea(): number {
    return this.side ** 2
  }
}

class Rectangle implements Shape {
  constructor(
    private width: number,
    private height: number
  ) {}

  getArea(): number {
    return this.width * this.height
  }
}

// Adding a new shape without changing existing code
class Triangle implements Shape {
  constructor(
    private base: number,
    private height: number
  ) {}

  getArea(): number {
    return (this.base * this.height) / 2
  }
}

// Calling code doesn't need to change
function printArea(shape: Shape): void {
  console.log(`Area: ${shape.getArea()}`)
}
```

**Improvements**:
- Adding a new shape does not require changing existing code.
- Each shape's logic is independent.
- Tests can be written independently as well.

---

## 3. Liskov Substitution Principle

### Definition
**Subclasses must be substitutable for their base classes.**

Subclasses must not break the contract (behavior) of their parent class.

### Why It Matters
- **Reliability**: Behavior across the inheritance hierarchy is predictable.
- **Polymorphism**: You can safely use base-class types.
- **Maintainability**: Inheritance relationships are clear.

### ❌ Bad Example: Subclass breaks the parent's contract
```typescript
class Bird {
  fly(): void {
    console.log('Flying in the sky')
  }
}

class Sparrow extends Bird {
  fly(): void {
    console.log('Sparrow flying fast')
  }
}

// ❌ Penguins cannot fly, so they break the parent's contract
class Penguin extends Bird {
  fly(): void {
    throw new Error('Penguins cannot fly!')
  }
}

// Problems appear at the call site
function makeBirdFly(bird: Bird): void {
  bird.fly()  // With Penguin, this throws
}

makeBirdFly(new Sparrow())  // OK
makeBirdFly(new Penguin())  // ❌ throws
```

**Problems**:
- A function expecting `Bird` breaks with `Penguin`.
- The inheritance relationship is inappropriate.

### ✅ Good Example: Correct abstraction
```typescript
// Base class: common to all birds
class Bird {
  constructor(public name: string) {}
}

// Ability to fly expressed as an interface
interface Flyable {
  fly(): void
}

// Ability to swim expressed as an interface
interface Swimmable {
  swim(): void
}

// Sparrow: a bird that can fly
class Sparrow extends Bird implements Flyable {
  fly(): void {
    console.log(`${this.name} is flying`)
  }
}

// Penguin: a bird that can swim
class Penguin extends Bird implements Swimmable {
  swim(): void {
    console.log(`${this.name} is swimming`)
  }
}

// Duck: a bird that can fly and swim
class Duck extends Bird implements Flyable, Swimmable {
  fly(): void {
    console.log(`${this.name} is flying`)
  }

  swim(): void {
    console.log(`${this.name} is swimming`)
  }
}

// Call sites: functions that require specific abilities
function makeFly(flyable: Flyable): void {
  flyable.fly()
}

function makeSwim(swimmable: Swimmable): void {
  swimmable.swim()
}

makeFly(new Sparrow('Tweety'))  // OK
makeSwim(new Penguin('Pingu'))  // OK
makeFly(new Duck('Donald'))     // OK
makeSwim(new Duck('Donald'))    // OK
```

**Improvements**:
- Inheritance and interfaces are used appropriately.
- Each class only exposes the abilities it can implement.
- Everything is type-safe.

---

## 4. Interface Segregation Principle

### Definition
**Clients should not be forced to depend on methods they do not use.**

Prefer many small, specialized interfaces over a single large one.

### Why It Matters
- **Flexibility**: Implement only the capabilities you need.
- **Maintainability**: The blast radius of interface changes is limited.
- **Clarity**: Roles are explicit.

### ❌ Bad Example: A bloated interface
```typescript
interface Worker {
  work(): void
  eat(): void
  sleep(): void
  takeBreak(): void
}

class Human implements Worker {
  work() { console.log('Working') }
  eat() { console.log('Eating') }
  sleep() { console.log('Sleeping') }
  takeBreak() { console.log('Taking a break') }
}

// ❌ Robots don't need to eat or sleep
class Robot implements Worker {
  work() { console.log('Processing tasks') }

  // Has to implement methods it doesn't need
  eat() { throw new Error('Robots do not eat') }
  sleep() { throw new Error('Robots do not sleep') }
  takeBreak() { throw new Error('Robots do not take breaks') }
}
```

**Problems**:
- Robots must implement methods they don't need.
- Interface changes have a large blast radius.

### ✅ Good Example: Segregated interfaces
```typescript
// Ability to work
interface Workable {
  work(): void
}

// Ability to eat
interface Eatable {
  eat(): void
}

// Ability to sleep
interface Sleepable {
  sleep(): void
}

// Ability to take breaks
interface Breakable {
  takeBreak(): void
}

// Humans: have every ability
class Human implements Workable, Eatable, Sleepable, Breakable {
  work() { console.log('Working') }
  eat() { console.log('Eating') }
  sleep() { console.log('Sleeping') }
  takeBreak() { console.log('Taking a break') }
}

// Robots: just the ability to work
class Robot implements Workable {
  work() { console.log('Processing tasks') }
}

// Call sites: require only the abilities they need
function assignWork(worker: Workable): void {
  worker.work()
}

function serveMeal(eater: Eatable): void {
  eater.eat()
}

assignWork(new Human())   // OK
assignWork(new Robot())   // OK
serveMeal(new Human())    // OK
// serveMeal(new Robot()) // compile error (type-safe)
```

**Improvements**:
- Each interface defines a single ability.
- Classes implement only the abilities they need.
- Everything remains type-safe.

---

## 5. Dependency Inversion Principle

### Definition
**High-level modules should not depend on low-level modules. Both should depend on abstractions.**

Depend on interfaces (abstractions) rather than on concrete classes.

### Why It Matters
- **Flexibility**: Implementations can be swapped easily.
- **Testability**: Mocks and stubs can be injected.
- **Loose coupling**: Dependencies between modules are weak.

### ❌ Bad Example: Directly depending on a concrete class
```typescript
// Concrete class
class MySQLDatabase {
  save(data: any): void {
    console.log('Saving to MySQL:', data)
  }
}

// ❌ UserService depends directly on MySQLDatabase
class UserService {
  private db = new MySQLDatabase()  // Depends on a concrete class

  saveUser(user: User): void {
    this.db.save(user)
  }
}

// If you want to switch to PostgreSQL
// → UserService must be modified
```

**Problems**:
- Changing DB implementations forces UserService to change.
- Testing requires a real database.
- UserService and MySQLDatabase are tightly coupled.

### ✅ Good Example: Depend on an abstraction (interface)
```typescript
// Abstraction (interface)
interface Database {
  save(data: any): void
  findById(id: string): any
}

// Concrete class 1: MySQL implementation
class MySQLDatabase implements Database {
  save(data: any): void {
    console.log('Saving to MySQL:', data)
  }

  findById(id: string): any {
    console.log('Finding in MySQL:', id)
    return null
  }
}

// Concrete class 2: PostgreSQL implementation
class PostgreSQLDatabase implements Database {
  save(data: any): void {
    console.log('Saving to PostgreSQL:', data)
  }

  findById(id: string): any {
    console.log('Finding in PostgreSQL:', id)
    return null
  }
}

// Concrete class 3: In-memory implementation (for tests)
class InMemoryDatabase implements Database {
  private data = new Map()

  save(data: any): void {
    this.data.set(data.id, data)
  }

  findById(id: string): any {
    return this.data.get(id)
  }
}

// ✅ UserService depends on the abstraction (dependency injection)
class UserService {
  constructor(private db: Database) {}  // Depends on the abstraction

  saveUser(user: User): void {
    this.db.save(user)
  }

  getUser(id: string): User {
    return this.db.findById(id)
  }
}

// Inject the implementation at use time
const mysqlService = new UserService(new MySQLDatabase())
const postgresService = new UserService(new PostgreSQLDatabase())
const testService = new UserService(new InMemoryDatabase())
```

**Improvements**:
- UserService depends on an abstraction (interface).
- DB implementations can be swapped trivially.
- Mocks can be injected for tests.
- UserService and DB implementations are loosely coupled.

### Dependency Injection (DI) in Practice
```typescript
// Simple DI container
class Container {
  private services = new Map<string, any>()

  register(name: string, service: any): void {
    this.services.set(name, service)
  }

  resolve<T>(name: string): T {
    return this.services.get(name)
  }
}

// Usage
const container = new Container()
container.register('database', new MySQLDatabase())
container.register('userService',
  new UserService(container.resolve('database'))
)

const userService = container.resolve<UserService>('userService')
```

---

## 🔗 Related Documents

- [Clean Code Basics](./CLEAN-CODE-BASICS.md)
- [Quality Checklist](./QUALITY-CHECKLIST.md)
- [Quick Reference](./QUICK-REFERENCE.md)

## 📖 References

- [SOLID Principles main page](./SKILL.md)
