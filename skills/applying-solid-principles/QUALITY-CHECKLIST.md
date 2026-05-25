# Quality Checklist

A checklist of items to verify before considering an implementation complete.

## 📋 Table of Contents
1. [Pre-Completion Checklist](#pre-completion-checklist)
2. [Detecting Code Smells](#detecting-code-smells)
3. [Refactoring Decisions](#refactoring-decisions)
4. [Design Principle Review](#design-principle-review)

---

## Pre-Completion Checklist

### 🎯 SOLID Principle Adherence

#### Single Responsibility
- [ ] Each class/function has a single responsibility.
- [ ] There is only one "reason to change."
- [ ] Multiple concerns are not mixed together.

**How to verify**:
```
Try to describe the class/function aloud.
→ If it comes out as "does X and does Y," consider splitting it.
→ If "does X" is enough, you're fine.
```

#### Open/Closed
- [ ] Open to extension (easy to add new features).
- [ ] Closed to modification (existing code is not changed).
- [ ] Extension is possible via interfaces or abstract classes.

**How to verify**:
```
When adding a new feature:
→ If you need to modify existing if/switch statements, it needs improvement.
→ If you can just add a new class, the design is good.
```

#### Liskov Substitution
- [ ] Subclasses are substitutable for their base class.
- [ ] Subclasses do not violate the parent's contract.
- [ ] Prefer composition over inheritance.

**How to verify**:
```
Assign an instance of the subclass to a variable of the base type.
→ Test whether it behaves as expected.
→ If exceptions occur, rethink the inheritance relationship.
```

#### Interface Segregation
- [ ] You are not forcing dependencies on unused methods.
- [ ] Interfaces are small and specialized.
- [ ] Classes implement only the features they need.

**How to verify**:
```
If an implementing class has empty methods or methods that throw errors,
→ the interface is too big.
→ Consider splitting it.
```

#### Dependency Inversion
- [ ] Depends on abstractions (interfaces).
- [ ] Does not depend directly on concrete classes.
- [ ] Uses dependency injection (DI).

**How to verify**:
```
Look at places where you instantiate classes with `new`.
→ If there are many, consider a DI container.
→ Check whether you can inject a mock in tests.
```

---

### 🎨 Clean Code Fundamentals

#### Naming
- [ ] Names clearly convey intent.
- [ ] Names are searchable (constants).
- [ ] Names are pronounceable.
- [ ] Naming conventions are consistent.

**Bad examples**:
```typescript
// ❌
let d: number  // days of what?
let temp: any  // temp what?
let usrNm: string  // over-abbreviated

// ✅
let daysSinceCreation: number
let temporaryUserData: User
let userName: string
```

#### Functions
- [ ] Functions are small (ideally under 20 lines).
- [ ] Single responsibility.
- [ ] 0–2 parameters (3 maximum).
- [ ] Avoid side effects.

**How to verify**:
```
If a function doesn't fit on one screen → consider splitting it.
If there are 3+ parameters → pass them as an object.
If it's hard to test → responsibilities may be doing too much.
```

#### Nesting
- [ ] Avoid deep nesting (3+ levels).
- [ ] Use guard clauses with early returns.
- [ ] Extract complex conditions into functions.

**Bad example**:
```typescript
// ❌ Deep nesting
if (user) {
  if (user.isActive) {
    if (user.hasPermission) {
      // handle
    }
  }
}

// ✅ Early returns
if (!user) return
if (!user.isActive) return
if (!user.hasPermission) return
// handle
```

---

### 📐 Design and Architecture

#### DRY (Don't Repeat Yourself)
- [ ] Avoid duplicated code.
- [ ] Extract shared logic into functions or modules.
- [ ] Turn magic numbers into constants.

**How to verify**:
```
The same code appears 3+ times → consider extracting a function.
Numeric literals appear in several places → consider constants.
```

#### YAGNI (You Aren't Gonna Need It)
- [ ] Don't implement features you don't need.
- [ ] Avoid over-abstraction for hypothetical future needs.
- [ ] Implement only what's needed now.

**How to verify**:
```
A feature exists "in case we need it later."
→ Check whether it is actually needed now.
→ If not, remove it.
```

#### KISS (Keep It Simple, Stupid)
- [ ] Simple design.
- [ ] Avoid over-abstraction.
- [ ] Easy-to-understand code.

**How to verify**:
```
Can another developer understand it?
→ If the explanation becomes long, it's too complex.
→ Consider simplifying.
```

---

## Detecting Code Smells

### 🚨 Red Flags (fix immediately)

#### 1. Oversized classes/functions
```typescript
// ❌ A class with 500+ lines
class UserManager {
  // many methods...
}

// ✅ Split the responsibilities
class UserRepository { }
class UserService { }
class UserValidator { }
```

#### 2. Long parameter lists
```typescript
// ❌ 5+ parameters
function createUser(name, email, age, address, phone) { }

// ✅ Pass an object
function createUser(userData: UserData) { }
```

#### 3. Duplicated code
```typescript
// ❌ The same logic appears in multiple places
function processUserA(user) {
  if (!user.email.includes('@')) throw new Error('Invalid email')
  // ...
}

function processUserB(user) {
  if (!user.email.includes('@')) throw new Error('Invalid email')
  // ...
}

// ✅ Extract into a function
function validateEmail(email: string) {
  if (!email.includes('@')) throw new Error('Invalid email')
}
```

#### 4. Magic numbers
```typescript
// ❌
if (user.age > 18) { }
setTimeout(() => {}, 5000)

// ✅
const ADULT_AGE = 18
const DEFAULT_TIMEOUT_MS = 5000

if (user.age > ADULT_AGE) { }
setTimeout(() => {}, DEFAULT_TIMEOUT_MS)
```

#### 5. Dead code
```typescript
// ❌ Unused functions/variables
function oldFunction() { }  // never called
const unusedVariable = 10   // never used

// ✅ Delete (git history preserves it)
```

---

### ⚠️ Yellow Flags (consider improving)

#### 1. Commented-out code
```typescript
// ❌
// function oldImplementation() {
//   // old code
// }

// ✅ Delete (restore from git history if needed)
```

#### 2. Excessive branching
```typescript
// ❌ Huge switch statement
switch (type) {
  case 'A': // handle A
  case 'B': // handle B
  case 'C': // handle C
  // ... 20+ cases
}

// ✅ Polymorphism
interface Handler {
  handle(): void
}

const handlers: Record<string, Handler> = {
  A: new HandlerA(),
  B: new HandlerB(),
  C: new HandlerC()
}

handlers[type].handle()
```

#### 3. Deep nesting
```typescript
// ❌ 3+ levels
if (a) {
  if (b) {
    if (c) {
      // handle
    }
  }
}

// ✅ Early returns
if (!a) return
if (!b) return
if (!c) return
// handle
```

#### 4. Long method chains
```typescript
// ❌ Hard to read
user.getOrders().filter(o => o.status === 'pending').map(o => o.total).reduce((a, b) => a + b, 0)

// ✅ Split across variables
const pendingOrders = user.getOrders().filter(o => o.status === 'pending')
const orderTotals = pendingOrders.map(o => o.total)
const totalAmount = orderTotals.reduce((a, b) => a + b, 0)
```

---

## Refactoring Decisions

### When to Refactor

#### 🔴 Refactor immediately
- [ ] It is causing bugs.
- [ ] It creates a security risk.
- [ ] It has a performance problem.
- [ ] It's blocking a new feature.

#### 🟡 Refactor on a plan
- [ ] Tests are hard to write.
- [ ] The blast radius of changes is unpredictable.
- [ ] The same bug keeps recurring.
- [ ] Code reviews surface many concerns.

#### 🟢 Refactor when you have time
- [ ] Code smells are present.
- [ ] Naming is poor.
- [ ] Too many comments (the code could speak for itself).

### Refactoring Procedure

1. **Write tests**
   - Tests that pin down the existing behavior.
   - Confirm the behavior after refactoring.

2. **Change in small steps**
   - One improvement at a time.
   - Split commits into small units.

3. **Run the tests**
   - Run tests after each step.
   - Revert if they fail.

4. **Review**
   - Confirm via code review.
   - Discuss improvements.

---

## Design Principle Review

### ✅ Signs of a Good Design

- [ ] Classes/functions are small.
- [ ] Responsibilities are clear.
- [ ] Tests are easy to write.
- [ ] Changes stay local (blast radius is limited).
- [ ] New features are easy to add.
- [ ] Reviewers say the code is easy to understand.

### ❌ Signs of a Bad Design

- [ ] Classes/functions are big (100+ lines).
- [ ] Responsibilities are unclear (explanations run long).
- [ ] Tests are hard to write (you need many mocks).
- [ ] Changes ripple widely.
- [ ] Every new feature forces large edits to existing code.
- [ ] Reviewers ask many questions.

---

## 🎯 Final Check Before Completion

Go through all of the following when you consider an implementation done:

### Design and Architecture
- [ ] SOLID principles are respected.
- [ ] DRY principle is followed.
- [ ] YAGNI is respected (no unnecessary features).
- [ ] The abstraction level is appropriate.

### Code Quality
- [ ] Functions are small and single-purpose (20 lines ideally).
- [ ] Parameter counts are minimal (0–2 ideal, 3 max).
- [ ] Deep nesting (3+ levels) is avoided.
- [ ] Magic numbers are lifted into constants.

### Naming and Readability
- [ ] Naming is consistent and intent is clear.
- [ ] Comments are kept to a minimum (nothing that the code already conveys).
- [ ] Early returns are used.

### Error Handling
- [ ] Error handling is appropriate.
- [ ] Error messages are clear.
- [ ] Exceptions are caught appropriately.

### Tests
- [ ] Unit tests are written.
- [ ] Tests are meaningful (not merely ceremonial).
- [ ] Edge cases are covered.

### Security
- [ ] Inputs are validated.
- [ ] SQL injection is prevented.
- [ ] XSS is prevented.
- [ ] Authentication and authorization are correct.

### Performance
- [ ] No unnecessary loops or computation.
- [ ] Database queries are optimized.
- [ ] Caching is used appropriately.

### Documentation
- [ ] Public APIs have JSDoc.
- [ ] Complex logic is documented with explanatory comments.
- [ ] The README is up to date.

---

## 🔗 Related Documents

- [SOLID Principles in Detail](./SOLID-PRINCIPLES.md)
- [Clean Code Basics](./CLEAN-CODE-BASICS.md)
- [Quick Reference](./QUICK-REFERENCE.md)

## 📖 References

- [Quality Checklist main page](./SKILL.md)
