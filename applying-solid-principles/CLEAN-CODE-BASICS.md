# Clean Code Basics

An explanation of the fundamental principles to apply in everyday coding.

## 📋 Table of Contents
1. [Naming Conventions](#naming-conventions)
2. [Function Design](#function-design)
3. [Early Returns](#early-returns)
4. [Eliminating Magic Numbers](#eliminating-magic-numbers)
5. [Comments and Documentation](#comments-and-documentation)

---

## Naming Conventions

### Principle: Make intent obvious

**Qualities of a good name**:
- The purpose is clear at a glance.
- It is searchable.
- It is pronounceable.
- It is culturally appropriate.

### Function names: Start with a verb

#### ✅ Good Example: Clear intent
```typescript
// The action is explicit
getUserById(id: string): User
calculateTotalPrice(items: Item[]): number
validateEmail(email: string): boolean
formatDate(date: Date): string
isAuthenticated(): boolean
hasPermission(user: User, resource: string): boolean

// Reading state: get/is/has
getActiveUsers(): User[]
isEmailValid(email: string): boolean
hasUnreadMessages(): boolean

// Changing state: set/update/create/delete
setUserName(name: string): void
updateUserProfile(profile: Profile): void
createOrder(items: Item[]): Order
deleteAccount(userId: string): void
```

#### ❌ Bad Example: Ambiguous names
```typescript
// Unclear what they do
getUser(id: string): User  // which user? under what condition?
calc(items: Item[]): number  // calculate what?
check(email: string): boolean  // check what?
process(data: any): void  // process what?
handle(event: Event): void  // handle it how?

// Over-abbreviated
usr(): User
calc(): number
chk(): boolean
proc(): void
```

### Variable names: Use nouns

#### ✅ Good Example: Purpose is clear
```typescript
// Concrete and searchable
const MAX_RETRY_COUNT = 3
const DEFAULT_TIMEOUT_MS = 5000
const API_BASE_URL = 'https://api.example.com'

// Use plurals for arrays
const activeUsers: User[] = []
const completedOrders: Order[] = []
const errorMessages: string[] = []

// Booleans start with is/has/can
const isAuthenticated: boolean = true
const hasPermission: boolean = false
const canEdit: boolean = checkPermission()

// Meaningful names
const userRegistrationDate: Date = new Date()
const totalPriceIncludingTax: number = calculateTotal()
```

#### ❌ Bad Example: Magic numbers and vague names
```typescript
// Magic numbers (no meaning)
setTimeout(() => {}, 5000)  // what does 5000 mean?
for (let i = 0; i < 3; i++) { }  // what does 3 mean?

// Vague names
let data: any = {}  // what kind of data?
let temp: string = ''  // temporary what?
let result: any = process()  // what kind of result?
let flag: boolean = true  // flag for what?

// Abbreviations (unpronounceable, unsearchable)
let usrNm: string = ''  // userName
let dtFmt: string = ''  // dateFormat
let errCd: number = 0   // errorCode
```

### Class names: Use nouns

#### ✅ Good Example
```typescript
// Clear role
class UserRepository { }
class EmailService { }
class PaymentProcessor { }
class OrderValidator { }
class ReportGenerator { }

// Multiple words for specificity
class UserAuthenticationService { }
class ProductInventoryManager { }
class CustomerNotificationService { }
```

#### ❌ Bad Example
```typescript
// Too vague
class Manager { }  // manages what?
class Handler { }  // handles what?
class Helper { }   // helps with what?
class Util { }     // utility for what?

// Starts with a verb (that's for functions, not classes)
class ProcessUser { }
class HandleOrder { }
class ValidateData { }
```

---

## Function Design

### Principle 1: Small, with a single responsibility

#### ✅ Good Example: Split into small functions
```typescript
// Each function has a single responsibility
function validateEmail(email: string): boolean {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return emailRegex.test(email)
}

function validatePassword(password: string): boolean {
  return password.length >= 8
}

function validateUserData(user: User): void {
  if (!validateEmail(user.email)) {
    throw new Error('Invalid email address')
  }
  if (!validatePassword(user.password)) {
    throw new Error('Password must be at least 8 characters')
  }
}

function saveUser(user: User): void {
  validateUserData(user)
  database.save(user)
}

function sendWelcomeEmail(user: User): void {
  const emailService = new EmailService()
  emailService.send(user.email, 'Welcome!', 'Welcome to our service!')
}

// Main flow: composed from the functions above
function registerUser(user: User): void {
  saveUser(user)
  sendWelcomeEmail(user)
}
```

**Benefits**:
- Each function has a clear responsibility.
- They are easy to test.
- They are reusable.
- They are easy to understand.

#### ❌ Bad Example: Enormous and multi-purpose
```typescript
// ❌ One giant function of 100+ lines
function processUser(user: User) {
  // Validation (20 lines)
  if (!user.email || !user.email.includes('@')) {
    throw new Error('Invalid email')
  }
  if (!user.password || user.password.length < 8) {
    throw new Error('Invalid password')
  }
  // ... more validation logic

  // Database save (20 lines)
  const db = new Database()
  db.connect()
  db.insert('users', user)
  db.disconnect()
  // ... more DB operations

  // Email sending (20 lines)
  const emailService = new EmailService()
  emailService.configure()
  emailService.send(user.email, 'Welcome', 'Welcome!')
  // ... more email handling

  // Logging (20 lines)
  const logger = new Logger()
  logger.log('User registered')
  // ... more logging

  // And so on...
}
```

**Problems**:
- Hard to understand what it does.
- Tests are complex.
- A change in one part can affect everything.
- Not reusable.

### Principle 2: Minimize parameters (0–2 is ideal)

#### ✅ Good Example: Few parameters
```typescript
// Zero parameters (ideal)
function getCurrentUser(): User {
  return authService.getUser()
}

// One parameter (good)
function getUserById(id: string): User {
  return database.findOne({ id })
}

// Two parameters (acceptable)
function createUser(name: string, email: string): User {
  return { name, email }
}
```

#### ⚠️ When you need many parameters: Pass an object
```typescript
// ❌ Too many parameters
function createUser(
  name: string,
  email: string,
  age: number,
  address: string,
  phone: string,
  country: string,
  zipCode: string
) { }

// ✅ Pass an object
interface UserData {
  name: string
  email: string
  age: number
  address: string
  phone: string
  country: string
  zipCode: string
}

function createUser(data: UserData): User {
  return { ...data }
}

// Usage
createUser({
  name: 'John',
  email: 'john@example.com',
  age: 30,
  address: '123 Main St',
  phone: '123-456-7890',
  country: 'USA',
  zipCode: '12345'
})
```

**Benefits of passing an object**:
- Order doesn't matter.
- Optional properties can be defined.
- Type-safe (in TypeScript).
- Easy to extend.

### Principle 3: Avoid side effects

#### ✅ Good Example: Pure functions
```typescript
// No side effects: returns a new array
function addItem(items: Item[], newItem: Item): Item[] {
  return [...items, newItem]
}

// No side effects: returns a new object
function updateUserName(user: User, newName: string): User {
  return { ...user, name: newName }
}

// Pure computation: no external state changes
function calculateTotal(items: Item[]): number {
  return items.reduce((sum, item) => sum + item.price, 0)
}
```

#### ❌ Bad Example: With side effects
```typescript
// ❌ Mutates its argument (unpredictable)
function addItem(items: Item[], newItem: Item): void {
  items.push(newItem)  // mutates the original array
}

// ❌ Mutates global state
let totalPrice = 0
function calculateTotal(items: Item[]): void {
  totalPrice = items.reduce((sum, item) => sum + item.price, 0)
}
```

---

## Early Returns

### Principle: Use guard clauses to reduce nesting

#### ✅ Good Example: Early returns to flatten nesting
```typescript
function processOrder(order: Order | null): void {
  // Guard clauses: early return
  if (!order) {
    console.log('Order is null')
    return
  }

  if (order.status !== 'pending') {
    console.log('Order is not pending')
    return
  }

  if (order.items.length === 0) {
    console.log('Order has no items')
    return
  }

  // Main logic (no nesting)
  const total = calculateTotal(order)
  sendConfirmation(order, total)
  updateInventory(order)
}
```

**Benefits**:
- Shallow nesting (easy to read).
- Error cases are explicit.
- The main logic stands out.

#### ❌ Bad Example: Deep nesting
```typescript
function processOrder(order: Order | null): void {
  if (order) {  // nest 1
    if (order.status === 'pending') {  // nest 2
      if (order.items.length > 0) {  // nest 3
        // Main logic (buried in deep nesting)
        const total = calculateTotal(order)
        sendConfirmation(order, total)
        updateInventory(order)
      } else {
        console.log('Order has no items')
      }
    } else {
      console.log('Order is not pending')
    }
  } else {
    console.log('Order is null')
  }
}
```

**Problems**:
- Deep nesting (hard to read).
- The main logic is hidden.
- Lots of `else` branches add complexity.

### For complex conditions

#### ✅ Good Example: Extract the condition into a function
```typescript
function canProcessOrder(order: Order | null): boolean {
  if (!order) return false
  if (order.status !== 'pending') return false
  if (order.items.length === 0) return false
  return true
}

function processOrder(order: Order | null): void {
  if (!canProcessOrder(order)) {
    console.log('Cannot process order')
    return
  }

  // Main logic
  const total = calculateTotal(order)
  sendConfirmation(order!, total)
  updateInventory(order!)
}
```

---

## Eliminating Magic Numbers

### Principle: Give constants meaningful names

#### ✅ Good Example: Named constants
```typescript
// Define as constants
const MAX_RETRY_COUNT = 3
const DEFAULT_TIMEOUT_MS = 5000
const API_RATE_LIMIT_PER_MINUTE = 100
const MIN_PASSWORD_LENGTH = 8
const MAX_FILE_SIZE_MB = 10

// Usage
function retryRequest(request: Request): Promise<Response> {
  for (let i = 0; i < MAX_RETRY_COUNT; i++) {
    try {
      return await fetch(request)
    } catch (error) {
      if (i === MAX_RETRY_COUNT - 1) throw error
      await sleep(DEFAULT_TIMEOUT_MS)
    }
  }
}

function validatePassword(password: string): boolean {
  return password.length >= MIN_PASSWORD_LENGTH
}
```

**Benefits**:
- Intent is clear.
- Searchable.
- Easy to change (managed in one place).
- Type-safe (in TypeScript).

#### ❌ Bad Example: Magic numbers
```typescript
// ❌ The meaning of the numbers is unclear
function retryRequest(request: Request): Promise<Response> {
  for (let i = 0; i < 3; i++) {  // what does 3 mean?
    try {
      return await fetch(request)
    } catch (error) {
      if (i === 2) throw error  // why 2?
      await sleep(5000)  // why 5000ms?
    }
  }
}

function validatePassword(password: string): boolean {
  return password.length >= 8  // why 8 characters?
}
```

### Using Enums

#### ✅ Good Example: Manage state with an enum
```typescript
// TypeScript enum
enum OrderStatus {
  Pending = 'pending',
  Processing = 'processing',
  Shipped = 'shipped',
  Delivered = 'delivered',
  Cancelled = 'cancelled'
}

function processOrder(order: Order): void {
  if (order.status === OrderStatus.Pending) {
    // handle
  }
}

// Or a const assertion (recommended)
const OrderStatus = {
  Pending: 'pending',
  Processing: 'processing',
  Shipped: 'shipped',
  Delivered: 'delivered',
  Cancelled: 'cancelled'
} as const

type OrderStatus = typeof OrderStatus[keyof typeof OrderStatus]
```

---

## Comments and Documentation

### Principle: Only comment what code cannot express

#### ✅ Good Comments
```typescript
// Explains business logic
// Orders of 10,000 yen or more ship for free
function calculateShippingFee(orderAmount: number): number {
  const FREE_SHIPPING_THRESHOLD = 10000
  return orderAmount >= FREE_SHIPPING_THRESHOLD ? 0 : 500
}

// Explains a complex algorithm
// Quick Sort: average O(n log n), worst case O(n^2)
function quickSort(arr: number[]): number[] {
  if (arr.length <= 1) return arr
  const pivot = arr[0]
  const left = arr.slice(1).filter(x => x <= pivot)
  const right = arr.slice(1).filter(x => x > pivot)
  return [...quickSort(left), pivot, ...quickSort(right)]
}

// TODO, FIXME, NOTE
// TODO: add caching in the future
// FIXME: error handling needs improvement
// NOTE: this runs asynchronously
```

#### ❌ Unnecessary Comments
```typescript
// ❌ The code already says this
// Get the user ID
const userId = user.id

// ❌ Contradicts the code
// Delete the user (actually deactivates)
function deleteUser(userId: string): void {
  database.update({ id: userId, active: false })
}

// ❌ Commented-out code (should be removed)
// function oldFunction() {
//   // old implementation
// }

// ❌ Change log (belongs in git history)
// 2023-01-01: John - initial implementation
// 2023-02-01: Jane - bug fix
```

### Using JSDoc (TypeScript)

#### ✅ Good Example: Documenting a public API
```typescript
/**
 * Look up a user by ID.
 *
 * @param userId - The unique identifier of the user.
 * @returns The matching user, or null if none was found.
 * @throws {DatabaseError} If a database error occurs.
 *
 * @example
 * const user = await getUserById('user-123')
 * if (user) {
 *   console.log(user.name)
 * }
 */
async function getUserById(userId: string): Promise<User | null> {
  return database.findOne({ id: userId })
}
```

---

## 🔗 Related Documents

- [SOLID Principles in Detail](./SOLID-PRINCIPLES.md)
- [Quality Checklist](./QUALITY-CHECKLIST.md)
- [Quick Reference](./QUICK-REFERENCE.md)

## 📖 References

- [Clean Code main page](./SKILL.md)
