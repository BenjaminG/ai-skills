---
name: swiftui-performance
description: Diagnose and fix SwiftUI performance issues including hangs, hitches, slow launches, excessive view redraws, and app terminations. This skill should be used when profiling SwiftUI apps, investigating UI responsiveness problems, optimizing render performance, reducing launch time, or fixing memory-related terminations. Triggers on SwiftUI performance, hang, hitch, jank, stutter, slow launch, OOM, watchdog kill, frame drop, or responsiveness issues.
---

# SwiftUI Performance

Comprehensive guide for diagnosing and fixing performance issues in SwiftUI apps. Based on Apple's Xcode performance documentation covering responsiveness, hangs, hitches, launch time, and terminations.

## Issue Decision Tree

Start here to identify what type of performance problem you're dealing with:

```
Is the app unresponsive to touch/input?
├─ YES → HANG (main thread blocked >250ms)
│        See references/hangs-responsiveness.md
│
├─ NO, but scrolling/animations stutter?
│  → HITCH (frame delivered late)
│    See references/hitches-rendering.md
│
├─ NO, but app takes too long to appear?
│  → SLOW LAUNCH
│    See references/launch-terminations.md
│
├─ NO, but app gets killed by system?
│  → TERMINATION (OOM, watchdog, background timeout)
│    See references/launch-terminations.md
│
└─ NO, but views redraw too often / UI feels sluggish?
   → SWIFTUI VIEW PERFORMANCE
     See references/swiftui-views.md
```

## Key Metrics

| Issue | Metric | Target | Tool |
|-------|--------|--------|------|
| Hang | Main thread block duration | <250ms | Time Profiler, MetricKit |
| Hitch | Hitch time ratio (ms/s) | <5 ms/s | Hitches instrument |
| Launch | Time to first frame (cold) | <400ms | App Launch template |
| Frame | Render time per frame | <16ms (60fps) / <8ms (120fps) | Core Animation instrument |
| Memory | Background footprint | <50MB | Allocations instrument |
| Redraws | Body invocation count | Minimize per interaction | SwiftUI instrument |

## Quick Patterns

### Move work off main thread
```swift
// Use .task for async work — suspends, never blocks
.task {
    let result = await heavyOperation()
    self.data = result  // @MainActor auto-dispatch in SwiftUI
}
```

### Prevent unnecessary view redraws
```swift
// Use @Observable (iOS 17+) for fine-grained invalidation
@Observable class Store {
    var count = 0
    var name = ""  // changing name won't redraw views that only read count
}
```

### Use lazy containers for large datasets
```swift
ScrollView {
    LazyVStack {  // only materializes visible views
        ForEach(items) { item in ItemRow(item: item) }
    }
}
```

### Avoid AnyView type erasure
```swift
// Use @ViewBuilder instead — preserves structural identity
@ViewBuilder
func content(for state: State) -> some View {
    switch state {
    case .loading: ProgressView()
    case .loaded(let data): DataView(data: data)
    case .error(let err): ErrorView(error: err)
    }
}
```

### Defer non-critical launch work
```swift
func application(_ app: UIApplication, didFinishLaunchingWithOptions opts: ...) -> Bool {
    setupCriticalUI()  // only what's needed for first frame
    DispatchQueue.global(qos: .utility).async { Analytics.configure() }
    return true
}
```

## Profiling Workflow

1. **Reproduce** the issue on a physical device (Simulator hides real perf)
2. **Profile** with Instruments (`Product → Profile`)
   - Hangs → Time Profiler or System Trace
   - Hitches → Animation Hitches template
   - Redraws → SwiftUI template
   - Launch → App Launch template
   - Memory → Allocations + Leaks
3. **Identify** the bottleneck (main thread work, expensive body, excessive redraws)
4. **Fix** using patterns from reference docs
5. **Measure** again — use XCTest performance metrics for regression testing

```swift
// XCTest scroll hitch measurement
func testScrollPerformance() {
    let app = XCUIApplication()
    app.launch()
    measure(metrics: [XCTOSSignpostMetric.scrollDecelerationMetric]) {
        app.tables.firstMatch.swipeUp()
    }
}
```

## Diagnostic Tools Reference

| Tool | What It Shows | When to Use |
|------|---------------|-------------|
| **SwiftUI Instrument** | Body invocations, attribute graph updates | Excessive redraws |
| **Time Profiler** | CPU usage per thread | Hangs, slow operations |
| **System Trace** | Thread states, waits, blocking | Lock contention, deadlocks |
| **Hitches Instrument** | Frame delivery timing | Scroll/animation jank |
| **App Launch Template** | dyld, static init, main thread phases | Slow startup |
| **Allocations** | Memory growth, leaks | OOM terminations |
| **Xcode Organizer** | Real-world metrics from shipped app | Field data analysis |
| **MetricKit** | Programmatic hang/hitch/launch/crash data | Production monitoring |

## Reference Docs

Detailed guidance by topic:
- `references/swiftui-views.md` — View identity, dependency tracking, @Observable, body optimization
- `references/hangs-responsiveness.md` — Main thread blocking, async patterns, hang prevention
- `references/hitches-rendering.md` — Frame pipeline, commit vs render hitches, scroll performance
- `references/launch-terminations.md` — Launch phases, cold/warm start, OOM, watchdog kills
- `references/diagnostic-tools.md` — Instruments templates, MetricKit, XCTest metrics, os_signpost
