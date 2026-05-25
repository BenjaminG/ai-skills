# Hangs & Responsiveness

## What Is a Hang?

A hang occurs when the main thread is blocked and the app cannot respond to user input. The system classifies hangs by duration:

| Classification | Duration | User Perception |
|----------------|----------|-----------------|
| MicroHang | 100–250ms | Subtle lag |
| Hang | 250ms–1s | Noticeable unresponsiveness |
| Severe Hang | >1s | App feels frozen |
| Fatal Hang | >5s (watchdog) | System may kill the app |

## Root Causes

### 1. Synchronous I/O on Main Thread

```swift
// BAD: Blocks main thread during file read
let data = try! Data(contentsOf: largeFileURL)
updateUI(with: data)

// GOOD: Async I/O
Task {
    let data = try await Data(contentsOf: largeFileURL)
    await MainActor.run { updateUI(with: data) }
}
```

### 2. Synchronous Network Calls

```swift
// BAD: Blocks until response arrives
let (data, _) = try await URLSession.shared.data(from: url)
// This is fine if called from a non-main context, but BAD if on main thread

// GOOD: Ensure network calls happen off main
func loadData() async {
    let (data, _) = try await URLSession.shared.data(from: url)
    await MainActor.run { self.items = decode(data) }
}
```

### 3. Lock Contention

```swift
// BAD: Main thread waits for lock held by background thread
let lock = NSLock()
// Background thread holds lock for extended time
// Main thread calls lock.lock() and blocks

// GOOD: Use actors for thread-safe access without blocking
actor DataStore {
    private var cache: [String: Data] = [:]

    func get(_ key: String) -> Data? { cache[key] }
    func set(_ key: String, _ value: Data) { cache[key] = value }
}
```

### 4. Expensive Computation on Main Thread

```swift
// BAD: CPU-bound work on main thread
func viewDidAppear() {
    let sorted = hugeArray.sorted { complexComparison($0, $1) }
    tableView.reloadData()
}

// GOOD: Move to background
func viewDidAppear() {
    Task.detached(priority: .userInitiated) {
        let sorted = hugeArray.sorted { complexComparison($0, $1) }
        await MainActor.run {
            self.data = sorted
            self.tableView.reloadData()
        }
    }
}
```

### 5. Core Data / Database on Main Thread

```swift
// BAD: Fetch on main context blocks main thread
let request = NSFetchRequest<Item>(entityName: "Item")
let items = try context.fetch(request)  // blocks if large dataset

// GOOD: Use background context
let bgContext = persistentContainer.newBackgroundContext()
bgContext.perform {
    let items = try bgContext.fetch(request)
    let objectIDs = items.map { $0.objectID }
    DispatchQueue.main.async {
        let mainItems = objectIDs.map { mainContext.object(with: $0) as! Item }
        self.updateUI(with: mainItems)
    }
}
```

### 6. Deadlocks

```swift
// DEADLOCK: DispatchQueue.main.sync from main thread
// This WILL freeze the app
DispatchQueue.main.sync {
    // Never reaches here — main thread is waiting for itself
}

// GOOD: Use async dispatch or check if already on main
if Thread.isMainThread {
    doWork()
} else {
    DispatchQueue.main.async { doWork() }
}
```

## Swift Concurrency Patterns

### @MainActor for UI Updates

```swift
@MainActor
class ViewModel: ObservableObject {
    @Published var items: [Item] = []

    func loadItems() async {
        // Automatically dispatched to main actor
        let fetched = await fetchFromNetwork()
        items = fetched  // safe — we're on @MainActor
    }
}
```

### Task Groups for Parallel Work

```swift
func loadDashboard() async {
    async let profile = fetchProfile()
    async let feed = fetchFeed()
    async let notifications = fetchNotifications()

    // All three run concurrently, none blocks main thread
    let (p, f, n) = await (profile, feed, notifications)
    updateDashboard(profile: p, feed: f, notifications: n)
}
```

### Structured Concurrency in SwiftUI

```swift
struct ContentView: View {
    @State private var data: [Item] = []

    var body: some View {
        List(data) { item in ItemRow(item: item) }
            .task {
                // Runs on cooperative thread pool — never blocks main
                data = await fetchItems()
            }
            .refreshable {
                // Pull-to-refresh — also cooperative
                data = await fetchItems()
            }
    }
}
```

## Analyzing Hangs in Production

### Xcode Organizer

`Window → Organizer → Hangs` shows hang reports from real users with:
- Call stack of the blocking main thread
- Hang duration
- Device/OS distribution

### MetricKit

```swift
import MetricKit

class PerformanceSubscriber: NSObject, MXMetricManagerSubscriber {
    func didReceive(_ payloads: [MXMetricPayload]) {
        for payload in payloads {
            if let responsiveness = payload.applicationResponsivenessMetrics {
                // Hang count and duration histogram
                print(responsiveness)
            }
        }
    }

    func didReceive(_ payloads: [MXDiagnosticPayload]) {
        for payload in payloads {
            if let hangDiags = payload.hangDiagnostics {
                for hang in hangDiags {
                    // Full call stack tree of the hang
                    print(hang.callStackTree)
                }
            }
        }
    }
}

// Register in app delegate
let subscriber = PerformanceSubscriber()
MXMetricManager.shared.add(subscriber)
```

## Prevention Checklist

- [ ] No synchronous I/O on main thread (file, network, database)
- [ ] No `DispatchQueue.main.sync` from any thread
- [ ] Core Data fetches use background contexts
- [ ] Heavy computation runs on background threads / Task.detached
- [ ] All UI updates dispatch to @MainActor
- [ ] No lock contention involving main thread
- [ ] .task modifier used for async loading in SwiftUI views
- [ ] MetricKit subscriber registered for production monitoring
