# Quick Reference

A concise reference you can scan quickly.

## 📋 Table of Contents
1. [SOLID Principles in One Line](#solid-principles-in-one-line)
2. [Common Mistakes and Fixes](#common-mistakes-and-fixes)
3. [Code Review Checkpoints](#code-review-checkpoints)
4. [Design Pattern Cheat Sheet](#design-pattern-cheat-sheet)

---

## SOLID Principles in One Line

### S - Single Responsibility
**There is only one reason to change.**
```typescript
// ❌ class User { save(), sendEmail(), generateReport() }
// ✅ class User { }, class UserRepository { }, class EmailService { }
```

### O - Open/Closed
**Open to extension, closed to modification.**
```typescript
// ❌ if (type === 'A') { } else if (type === 'B') { }
// ✅ interface Handler { handle() }; class HandlerA implements Handler { }
```

### L - Liskov Substitution
**Subclasses must be substitutable for their base class.**
```typescript
// ❌ class Penguin extends Bird { fly() { throw Error } }
// ✅ class Penguin extends Bird implements Swimmable { }
```

### I - Interface Segregation
**Don't force dependencies on methods that aren't used.**
```typescript
// ❌ interface Worker { work(), eat(), sleep() }
// ✅ interface Workable { work() }; interface Eatable { eat() }
```

### D - Dependency Inversion
**Depend on abstractions, not concretions.**
```typescript
// ❌ class UserService { db = new MySQLDatabase() }
// ✅ class UserService { constructor(private db: Database) }
```

---

## Common Mistakes and Fixes

### 1. Oversized classes/functions
```typescript
// ❌ Bad
class UserManager {
  // 500+ lines...
  validateUser() { }
  saveUser() { }
  sendEmail() { }
  generateReport() { }
  // ...
}

// ✅ Good
class UserValidator { validateUser() { } }
class UserRepository { saveUser() { } }
class EmailService { sendEmail() { } }
class ReportGenerator { generateReport() { } }
```

### 2. Magic numbers
```typescript
// ❌ Bad
if (user.age > 18) { }
setTimeout(() => {}, 5000)

// ✅ Good
const ADULT_AGE = 18
const DEFAULT_TIMEOUT_MS = 5000

if (user.age > ADULT_AGE) { }
setTimeout(() => {}, DEFAULT_TIMEOUT_MS)
```

### 3. Deep nesting
```typescript
// ❌ Bad
if (user) {
  if (user.isActive) {
    if (user.hasPermission) {
      // handle
    }
  }
}

// ✅ Good (early returns)
if (!user) return
if (!user.isActive) return
if (!user.hasPermission) return
// handle
```

### 4. Too many parameters
```typescript
// ❌ Bad
function createUser(name, email, age, address, phone, country) { }

// ✅ Good
interface UserData {
  name: string
  email: string
  age: number
  address: string
  phone: string
  country: string
}

function createUser(data: UserData) { }
```

### 5. Ambiguous naming
```typescript
// ❌ Bad
function getData(id) { }
let temp = {}
const result = process()

// ✅ Good
function getUserById(userId: string): User { }
let temporaryUserData: User = {}
const validationResult: ValidationResult = validateUser()
```

### 6. Functions with side effects
```typescript
// ❌ Bad (mutates its argument)
function addItem(items: Item[], newItem: Item): void {
  items.push(newItem)  // mutates the original array
}

// ✅ Good (returns a new array)
function addItem(items: Item[], newItem: Item): Item[] {
  return [...items, newItem]
}
```

### 7. Direct dependency on concrete classes
```typescript
// ❌ Bad
class UserService {
  private db = new MySQLDatabase()  // depends on a concrete class
  saveUser(user: User) {
    this.db.save(user)
  }
}

// ✅ Good (dependency injection)
interface Database {
  save(data: any): void
}

class UserService {
  constructor(private db: Database) { }  // depends on an abstraction
  saveUser(user: User) {
    this.db.save(user)
  }
}
```

---

## Code Review Checkpoints

### 🔴 Required Checks (reasons to reject)

#### Security
- [ ] SQL injection mitigations
- [ ] XSS mitigations
- [ ] CSRF mitigations
- [ ] Input validation
- [ ] Authentication/authorization

#### Type Safety (TypeScript/Python)
- [ ] No `any` type used (TypeScript)
- [ ] No `Any` type used (Python)
- [ ] Appropriate type annotations
- [ ] null/undefined checks

#### Error Handling
- [ ] try-catch used appropriately
- [ ] Error messages are clear
- [ ] Errors are logged

### 🟡 Recommended Checks (encourage improvement)

#### SOLID Principles
- [ ] Single Responsibility
- [ ] Open/Closed
- [ ] Dependency Inversion

#### Clean Code
- [ ] Small functions (under 20 lines)
- [ ] Few parameters (0–2)
- [ ] No deep nesting (3 levels max)
- [ ] No magic numbers

#### Naming
- [ ] Intent is clear
- [ ] Consistent
- [ ] Searchable

#### Tests
- [ ] Unit tests present
- [ ] Edge cases covered
- [ ] Tests are meaningful

---

## Design Pattern Cheat Sheet

### Creational Patterns

#### Singleton
**Use case**: Guarantee a single instance.
```typescript
class Singleton {
  private static instance: Singleton

  private constructor() { }

  static getInstance(): Singleton {
    if (!Singleton.instance) {
      Singleton.instance = new Singleton()
    }
    return Singleton.instance
  }
}
```

#### Factory
**Use case**: Abstract object creation.
```typescript
interface Product {
  operation(): string
}

class ConcreteProductA implements Product {
  operation() { return 'Product A' }
}

class ConcreteProductB implements Product {
  operation() { return 'Product B' }
}

class Factory {
  createProduct(type: string): Product {
    if (type === 'A') return new ConcreteProductA()
    if (type === 'B') return new ConcreteProductB()
    throw new Error('Unknown type')
  }
}
```

---

### Structural Patterns

#### Adapter
**Use case**: Translate between interfaces.
```typescript
interface Target {
  request(): string
}

class Adaptee {
  specificRequest(): string {
    return 'Adaptee'
  }
}

class Adapter implements Target {
  constructor(private adaptee: Adaptee) { }

  request(): string {
    return this.adaptee.specificRequest()
  }
}
```

#### Decorator
**Use case**: Add functionality dynamically.
```typescript
interface Component {
  operation(): string
}

class ConcreteComponent implements Component {
  operation() { return 'Base' }
}

class Decorator implements Component {
  constructor(protected component: Component) { }

  operation(): string {
    return `Decorated(${this.component.operation()})`
  }
}
```

---

### Behavioral Patterns

#### Strategy
**Use case**: Make algorithms swappable.
```typescript
interface Strategy {
  execute(data: any): any
}

class ConcreteStrategyA implements Strategy {
  execute(data: any) { return `Strategy A: ${data}` }
}

class ConcreteStrategyB implements Strategy {
  execute(data: any) { return `Strategy B: ${data}` }
}

class Context {
  constructor(private strategy: Strategy) { }

  setStrategy(strategy: Strategy) {
    this.strategy = strategy
  }

  executeStrategy(data: any) {
    return this.strategy.execute(data)
  }
}
```

#### Observer
**Use case**: Implement event notifications.
```typescript
interface Observer {
  update(data: any): void
}

class Subject {
  private observers: Observer[] = []

  attach(observer: Observer) {
    this.observers.push(observer)
  }

  notify(data: any) {
    this.observers.forEach(observer => observer.update(data))
  }
}

class ConcreteObserver implements Observer {
  update(data: any) {
    console.log('Received:', data)
  }
}
```

---

## 🎯 Quick Checks During Implementation

Items to quickly confirm while coding:

### When writing a function
```
✓ Under 20 lines? → split if not
✓ 0–2 parameters? → pass an object if 3+
✓ No side effects? → prefer pure functions
✓ Using early returns? → reduce nesting
```

### When writing a class
```
✓ Single responsibility? → split if you catch yourself saying "does X and Y"
✓ Depending on abstractions? → use DI rather than `new`
✓ Small interfaces? → split off methods that aren't used
```

### When defining a variable
```
✓ Name conveys intent? → avoid data, temp, result
✓ Not a magic number? → turn it into a constant
✓ Searchable? → avoid abbreviations
```

### Before committing
```
✓ SOLID principles respected?
✓ Tests written?
✓ No code smells?
✓ Secure?
```

---

## 📊 Code Quality Metrics

### Target Values

| Metric | Ideal | Acceptable | Needs work |
|---------|-------|---------|--------|
| Function length | <20 lines | <50 lines | >50 lines |
| Parameter count | 0–2 | 3 | >3 |
| Nesting depth | 1–2 levels | 3 levels | >3 levels |
| Class length | <200 lines | <500 lines | >500 lines |
| Cyclomatic complexity | <10 | <20 | >20 |
| Test coverage | >80% | >60% | <60% |

---

## 🔗 Related Documents

- [SOLID Principles in Detail](./SOLID-PRINCIPLES.md) — detailed explanation of each principle
- [Clean Code Basics](./CLEAN-CODE-BASICS.md) — naming, functions, comments
- [Quality Checklist](./QUALITY-CHECKLIST.md) — items to check before completion

## 📖 References

- [Quick Reference main page](./SKILL.md)

---

## 💡 One-Line Tips

### When in doubt

**Favor simplicity**
```
Complex design vs. simple design
→ When in doubt, pick the simple one.
```

**Favor testability**
```
Hard to write tests
→ A sign the design needs rethinking.
```

**Favor readability**
```
Comments keep getting longer
→ See if the code itself can convey the meaning.
```

**Favor ease of change**
```
Changes ripple widely
→ Responsibilities may not be properly separated.
```
