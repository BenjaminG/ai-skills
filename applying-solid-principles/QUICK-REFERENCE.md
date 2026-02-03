# クイックリファレンス

素早く参照できる簡潔な情報をまとめたリファレンスです。

## 📋 目次
1. [SOLID原則 1行まとめ](#solid原則-1行まとめ)
2. [よくある間違いと修正](#よくある間違いと修正)
3. [コードレビューポイント](#コードレビューポイント)
4. [設計パターン早見表](#設計パターン早見表)

---

## SOLID原則 1行まとめ

### S - Single Responsibility（単一責任）
**「変更する理由」は1つだけ**
```typescript
// ❌ class User { save(), sendEmail(), generateReport() }
// ✅ class User { }, class UserRepository { }, class EmailService { }
```

### O - Open/Closed（開放閉鎖）
**拡張に開き、修正に閉じる**
```typescript
// ❌ if (type === 'A') { } else if (type === 'B') { }
// ✅ interface Handler { handle() }; class HandlerA implements Handler { }
```

### L - Liskov Substitution（リスコフの置換）
**派生クラスは基底クラスと置換可能**
```typescript
// ❌ class Penguin extends Bird { fly() { throw Error } }
// ✅ class Penguin extends Bird implements Swimmable { }
```

### I - Interface Segregation（インターフェース分離）
**使わないメソッドへの依存を強制しない**
```typescript
// ❌ interface Worker { work(), eat(), sleep() }
// ✅ interface Workable { work() }; interface Eatable { eat() }
```

### D - Dependency Inversion（依存関係逆転）
**抽象に依存、具象に依存しない**
```typescript
// ❌ class UserService { db = new MySQLDatabase() }
// ✅ class UserService { constructor(private db: Database) }
```

---

## よくある間違いと修正

### 1. 巨大なクラス・関数
```typescript
// ❌ 悪い例
class UserManager {
  // 500行以上...
  validateUser() { }
  saveUser() { }
  sendEmail() { }
  generateReport() { }
  // ...
}

// ✅ 良い例
class UserValidator { validateUser() { } }
class UserRepository { saveUser() { } }
class EmailService { sendEmail() { } }
class ReportGenerator { generateReport() { } }
```

### 2. マジックナンバー
```typescript
// ❌ 悪い例
if (user.age > 18) { }
setTimeout(() => {}, 5000)

// ✅ 良い例
const ADULT_AGE = 18
const DEFAULT_TIMEOUT_MS = 5000

if (user.age > ADULT_AGE) { }
setTimeout(() => {}, DEFAULT_TIMEOUT_MS)
```

### 3. 深いネスト
```typescript
// ❌ 悪い例
if (user) {
  if (user.isActive) {
    if (user.hasPermission) {
      // 処理
    }
  }
}

// ✅ 良い例（早期リターン）
if (!user) return
if (!user.isActive) return
if (!user.hasPermission) return
// 処理
```

### 4. 引数が多すぎる
```typescript
// ❌ 悪い例
function createUser(name, email, age, address, phone, country) { }

// ✅ 良い例
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

### 5. 曖昧な命名
```typescript
// ❌ 悪い例
function getData(id) { }
let temp = {}
const result = process()

// ✅ 良い例
function getUserById(userId: string): User { }
let temporaryUserData: User = {}
const validationResult: ValidationResult = validateUser()
```

### 6. 副作用のある関数
```typescript
// ❌ 悪い例（引数を変更）
function addItem(items: Item[], newItem: Item): void {
  items.push(newItem)  // 元の配列を変更
}

// ✅ 良い例（新しい配列を返す）
function addItem(items: Item[], newItem: Item): Item[] {
  return [...items, newItem]
}
```

### 7. 具象クラスへの直接依存
```typescript
// ❌ 悪い例
class UserService {
  private db = new MySQLDatabase()  // 具象に依存
  saveUser(user: User) {
    this.db.save(user)
  }
}

// ✅ 良い例（依存性注入）
interface Database {
  save(data: any): void
}

class UserService {
  constructor(private db: Database) { }  // 抽象に依存
  saveUser(user: User) {
    this.db.save(user)
  }
}
```

---

## コードレビューポイント

### 🔴 必須チェック（拒否理由になる）

#### セキュリティ
- [ ] SQLインジェクション対策
- [ ] XSS対策
- [ ] CSRF対策
- [ ] 入力検証
- [ ] 認証・認可

#### 型安全性（TypeScript/Python）
- [ ] `any`型を使用していない（TypeScript）
- [ ] `Any`型を使用していない（Python）
- [ ] 適切な型注釈がある
- [ ] null/undefinedチェックがある

#### エラーハンドリング
- [ ] try-catchが適切
- [ ] エラーメッセージが明確
- [ ] エラーログが出力される

### 🟡 推奨チェック（改善を促す）

#### SOLID原則
- [ ] 単一責任の原則
- [ ] 開放閉鎖の原則
- [ ] 依存関係逆転の原則

#### クリーンコード
- [ ] 関数が小さい（20行以内）
- [ ] 引数が少ない（0-2個）
- [ ] 深いネストがない（3階層以内）
- [ ] マジックナンバーがない

#### 命名
- [ ] 意図が明確
- [ ] 一貫性がある
- [ ] 検索可能

#### テスト
- [ ] ユニットテストがある
- [ ] エッジケースをカバー
- [ ] テストが意味のある内容

---

## 設計パターン早見表

### 生成パターン

#### Singleton（シングルトン）
**用途**: 1つのインスタンスのみを保証
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

#### Factory（ファクトリ）
**用途**: オブジェクト生成を抽象化
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

### 構造パターン

#### Adapter（アダプター）
**用途**: インターフェースを変換
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

#### Decorator（デコレーター）
**用途**: 動的に機能を追加
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

### 振る舞いパターン

#### Strategy（ストラテジー）
**用途**: アルゴリズムを切り替え可能に
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

#### Observer（オブザーバー）
**用途**: イベント通知を実装
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

## 🎯 実装時クイックチェック

実装中に素早く確認できる項目：

### 関数を書いているとき
```
✓ 20行以内か？ → 超えたら分割
✓ 引数は0-2個か？ → 3個以上ならオブジェクトで渡す
✓ 副作用はないか？ → 純粋関数を優先
✓ 早期リターンを使っているか？ → ネストを減らす
```

### クラスを書いているとき
```
✓ 単一責任か？ → 「〜と〜をする」となったら分割
✓ 抽象に依存しているか？ → newではなくDI
✓ インターフェースは小さいか？ → 使わないメソッドは分離
```

### 変数を定義するとき
```
✓ 意図が明確な名前か？ → data, temp, result は避ける
✓ マジックナンバーでないか？ → 定数化
✓ 検索可能か？ → 省略形は避ける
```

### コミット前
```
✓ SOLID原則を守っているか？
✓ テストは書いたか？
✓ コードスメルはないか？
✓ セキュリティは大丈夫か？
```

---

## 📊 コード品質メトリクス

### 良い値の目安

| メトリクス | 理想値 | 許容範囲 | 要改善 |
|---------|-------|---------|--------|
| 関数の行数 | <20行 | <50行 | >50行 |
| 引数の数 | 0-2個 | 3個 | >3個 |
| ネストの深さ | 1-2階層 | 3階層 | >3階層 |
| クラスの行数 | <200行 | <500行 | >500行 |
| サイクロマティック複雑度 | <10 | <20 | >20 |
| テストカバレッジ | >80% | >60% | <60% |

---

## 🔗 関連ドキュメント

- [SOLID原則の詳細](./SOLID-PRINCIPLES.md) - 各原則の詳細解説
- [クリーンコードの基礎](./CLEAN-CODE-BASICS.md) - 命名、関数、コメント
- [品質チェックリスト](./QUALITY-CHECKLIST.md) - 実装完了前の確認項目

## 📖 参考リンク

- [クイックリファレンス メインページ](./SKILL.md)

---

## 💡 ワンポイントアドバイス

### 迷ったときの判断基準

**シンプルさを優先**
```
複雑な設計 vs シンプルな設計
→ 迷ったらシンプルな方を選ぶ
```

**テストしやすさを優先**
```
テストが書きにくい
→ 設計を見直すサイン
```

**読みやすさを優先**
```
コメントが長くなる
→ コードで説明できないか検討
```

**変更しやすさを優先**
```
変更の影響範囲が広い
→ 責任が分離されていない可能性
```
