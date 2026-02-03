# クリーンコードの基礎

日常的なコーディングで適用すべき基本原則を解説します。

## 📋 目次
1. [命名規則](#命名規則)
2. [関数設計](#関数設計)
3. [早期リターン](#早期リターン)
4. [マジックナンバーの排除](#マジックナンバーの排除)
5. [コメントとドキュメント](#コメントとドキュメント)

---

## 命名規則

### 原則: 意図を明確にする

**良い命名の条件**:
- 目的が一目でわかる
- 検索可能
- 発音可能
- 文化的に適切

### 関数名: 動詞で始める

#### ✅ 良い例: 意図が明確
```typescript
// 動作が明確
getUserById(id: string): User
calculateTotalPrice(items: Item[]): number
validateEmail(email: string): boolean
formatDate(date: Date): string
isAuthenticated(): boolean
hasPermission(user: User, resource: string): boolean

// 状態を取得: get/is/has
getActiveUsers(): User[]
isEmailValid(email: string): boolean
hasUnreadMessages(): boolean

// 状態を変更: set/update/create/delete
setUserName(name: string): void
updateUserProfile(profile: Profile): void
createOrder(items: Item[]): Order
deleteAccount(userId: string): void
```

#### ❌ 悪い例: 曖昧な命名
```typescript
// 何をするか不明確
getUser(id: string): User  // どのユーザー？条件は？
calc(items: Item[]): number  // 何を計算？
check(email: string): boolean  // 何をチェック？
process(data: any): void  // 何を処理？
handle(event: Event): void  // どう処理？

// 省略しすぎ
usr(): User
calc(): number
chk(): boolean
proc(): void
```

### 変数名: 名詞で表現

#### ✅ 良い例: 目的が明確
```typescript
// 具体的で検索可能
const MAX_RETRY_COUNT = 3
const DEFAULT_TIMEOUT_MS = 5000
const API_BASE_URL = 'https://api.example.com'

// 複数形で配列を表現
const activeUsers: User[] = []
const completedOrders: Order[] = []
const errorMessages: string[] = []

// boolean は is/has/can で始める
const isAuthenticated: boolean = true
const hasPermission: boolean = false
const canEdit: boolean = checkPermission()

// 意味のある名前
const userRegistrationDate: Date = new Date()
const totalPriceIncludingTax: number = calculateTotal()
```

#### ❌ 悪い例: マジックナンバーと曖昧な名前
```typescript
// マジックナンバー（意味不明）
setTimeout(() => {}, 5000)  // 5000の意味は？
for (let i = 0; i < 3; i++) { }  // 3の意味は？

// 曖昧な名前
let data: any = {}  // どんなデータ？
let temp: string = ''  // 一時的な何？
let result: any = process()  // どんな結果？
let flag: boolean = true  // 何のフラグ？

// 省略形（発音不可、検索困難）
let usrNm: string = ''  // userName
let dtFmt: string = ''  // dateFormat
let errCd: number = 0   // errorCode
```

### クラス名: 名詞で表現

#### ✅ 良い例
```typescript
// 役割が明確
class UserRepository { }
class EmailService { }
class PaymentProcessor { }
class OrderValidator { }
class ReportGenerator { }

// 複数の単語で具体的に
class UserAuthenticationService { }
class ProductInventoryManager { }
class CustomerNotificationService { }
```

#### ❌ 悪い例
```typescript
// 曖昧すぎる
class Manager { }  // 何を管理？
class Handler { }  // 何を処理？
class Helper { }   // 何を助ける？
class Util { }     // 何のユーティリティ？

// 動詞で始まる（関数名ではない）
class ProcessUser { }
class HandleOrder { }
class ValidateData { }
```

---

## 関数設計

### 原則1: 小さく、単一の責任

#### ✅ 良い例: 小さく分割
```typescript
// 各関数が単一の責任
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

// メイン処理: 各関数を組み合わせ
function registerUser(user: User): void {
  saveUser(user)
  sendWelcomeEmail(user)
}
```

**利点**:
- 各関数の責任が明確
- テストしやすい
- 再利用可能
- 理解しやすい

#### ❌ 悪い例: 巨大で複数の責任
```typescript
// ❌ 100行以上の巨大関数
function processUser(user: User) {
  // バリデーション（20行）
  if (!user.email || !user.email.includes('@')) {
    throw new Error('Invalid email')
  }
  if (!user.password || user.password.length < 8) {
    throw new Error('Invalid password')
  }
  // ... さらに検証ロジック

  // データベース保存（20行）
  const db = new Database()
  db.connect()
  db.insert('users', user)
  db.disconnect()
  // ... さらにDB操作

  // メール送信（20行）
  const emailService = new EmailService()
  emailService.configure()
  emailService.send(user.email, 'Welcome', 'Welcome!')
  // ... さらにメール処理

  // ログ記録（20行）
  const logger = new Logger()
  logger.log('User registered')
  // ... さらにログ処理

  // その他の処理...
}
```

**問題点**:
- 何をしているか理解困難
- テストが複雑
- 一部の変更が全体に影響
- 再利用できない

### 原則2: 引数は最小限（0-2個が理想）

#### ✅ 良い例: 引数が少ない
```typescript
// 引数0個（理想的）
function getCurrentUser(): User {
  return authService.getUser()
}

// 引数1個（良い）
function getUserById(id: string): User {
  return database.findOne({ id })
}

// 引数2個（許容範囲）
function createUser(name: string, email: string): User {
  return { name, email }
}
```

#### ⚠️ 引数が多い場合: オブジェクトで渡す
```typescript
// ❌ 引数が多すぎる
function createUser(
  name: string,
  email: string,
  age: number,
  address: string,
  phone: string,
  country: string,
  zipCode: string
) { }

// ✅ オブジェクトで渡す
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

// 使用時
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

**オブジェクト渡しの利点**:
- 順序を気にしない
- 省略可能なプロパティを定義可能
- 型安全（TypeScriptの場合）
- 拡張しやすい

### 原則3: 副作用を避ける

#### ✅ 良い例: 純粋関数
```typescript
// 副作用なし: 新しい配列を返す
function addItem(items: Item[], newItem: Item): Item[] {
  return [...items, newItem]
}

// 副作用なし: 新しいオブジェクトを返す
function updateUserName(user: User, newName: string): User {
  return { ...user, name: newName }
}

// 計算のみ: 外部状態を変更しない
function calculateTotal(items: Item[]): number {
  return items.reduce((sum, item) => sum + item.price, 0)
}
```

#### ❌ 悪い例: 副作用あり
```typescript
// ❌ 引数を直接変更（予測不可能）
function addItem(items: Item[], newItem: Item): void {
  items.push(newItem)  // 元の配列を変更
}

// ❌ グローバル状態を変更
let totalPrice = 0
function calculateTotal(items: Item[]): void {
  totalPrice = items.reduce((sum, item) => sum + item.price, 0)
}
```

---

## 早期リターン

### 原則: ガード句でネストを減らす

#### ✅ 良い例: 早期リターンでネスト削減
```typescript
function processOrder(order: Order | null): void {
  // ガード句: 早期リターン
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

  // メインロジック（ネストなし）
  const total = calculateTotal(order)
  sendConfirmation(order, total)
  updateInventory(order)
}
```

**利点**:
- ネストが浅い（理解しやすい）
- エラーケースが明確
- メインロジックが目立つ

#### ❌ 悪い例: 深いネスト
```typescript
function processOrder(order: Order | null): void {
  if (order) {  // ネスト1
    if (order.status === 'pending') {  // ネスト2
      if (order.items.length > 0) {  // ネスト3
        // メインロジック（深いネストの中）
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

**問題点**:
- ネストが深い（理解困難）
- メインロジックが埋もれる
- elseが多く複雑

### 複雑な条件の場合

#### ✅ 良い例: 条件を関数化
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

  // メインロジック
  const total = calculateTotal(order)
  sendConfirmation(order!, total)
  updateInventory(order!)
}
```

---

## マジックナンバーの排除

### 原則: 定数に名前をつける

#### ✅ 良い例: 意味のある定数名
```typescript
// 定数として定義
const MAX_RETRY_COUNT = 3
const DEFAULT_TIMEOUT_MS = 5000
const API_RATE_LIMIT_PER_MINUTE = 100
const MIN_PASSWORD_LENGTH = 8
const MAX_FILE_SIZE_MB = 10

// 使用例
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

**利点**:
- 意図が明確
- 検索可能
- 変更が容易（1箇所で管理）
- 型安全（TypeScriptの場合）

#### ❌ 悪い例: マジックナンバー
```typescript
// ❌ 数値の意味が不明
function retryRequest(request: Request): Promise<Response> {
  for (let i = 0; i < 3; i++) {  // 3の意味は？
    try {
      return await fetch(request)
    } catch (error) {
      if (i === 2) throw error  // なぜ2？
      await sleep(5000)  // 5000msの理由は？
    }
  }
}

function validatePassword(password: string): boolean {
  return password.length >= 8  // なぜ8文字？
}
```

### Enum の活用

#### ✅ 良い例: 状態をEnumで管理
```typescript
// TypeScript Enum
enum OrderStatus {
  Pending = 'pending',
  Processing = 'processing',
  Shipped = 'shipped',
  Delivered = 'delivered',
  Cancelled = 'cancelled'
}

function processOrder(order: Order): void {
  if (order.status === OrderStatus.Pending) {
    // 処理
  }
}

// または const assertion（推奨）
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

## コメントとドキュメント

### 原則: コードで説明できないことのみコメント

#### ✅ 良いコメント
```typescript
// ビジネスロジックの説明
// 注文金額が10,000円以上の場合、送料無料
function calculateShippingFee(orderAmount: number): number {
  const FREE_SHIPPING_THRESHOLD = 10000
  return orderAmount >= FREE_SHIPPING_THRESHOLD ? 0 : 500
}

// 複雑なアルゴリズムの説明
// Quick Sort: 平均O(n log n)、最悪O(n^2)
function quickSort(arr: number[]): number[] {
  if (arr.length <= 1) return arr
  const pivot = arr[0]
  const left = arr.slice(1).filter(x => x <= pivot)
  const right = arr.slice(1).filter(x => x > pivot)
  return [...quickSort(left), pivot, ...quickSort(right)]
}

// TODO、FIXME、NOTE
// TODO: 将来的にキャッシュ機能を追加
// FIXME: エラーハンドリングを改善する必要あり
// NOTE: この処理は非同期で実行される
```

#### ❌ 不要なコメント
```typescript
// ❌ コードを読めばわかる
// ユーザーIDを取得
const userId = user.id

// ❌ コードと矛盾
// ユーザーを削除（実際は無効化）
function deleteUser(userId: string): void {
  database.update({ id: userId, active: false })
}

// ❌ コメントアウトされたコード（削除すべき）
// function oldFunction() {
//   // 古い実装
// }

// ❌ 履歴情報（Git履歴で管理すべき）
// 2023-01-01: John - 初回実装
// 2023-02-01: Jane - バグ修正
```

### JSDoc の活用（TypeScript）

#### ✅ 良い例: 公開APIのドキュメント
```typescript
/**
 * ユーザーをIDで検索
 *
 * @param userId - ユーザーの一意識別子
 * @returns 見つかったユーザー、または null
 * @throws {DatabaseError} データベースエラー時
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

## 🔗 関連ドキュメント

- [SOLID原則の詳細](./SOLID-PRINCIPLES.md)
- [品質チェックリスト](./QUALITY-CHECKLIST.md)
- [クイックリファレンス](./QUICK-REFERENCE.md)

## 📖 参考リンク

- [クリーンコード メインページ](./SKILL.md)
