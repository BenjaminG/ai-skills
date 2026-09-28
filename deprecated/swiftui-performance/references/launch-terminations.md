# Launch Time & App Terminations

## Launch Types

| Type | Description | Target |
|------|-------------|--------|
| Cold | App not in memory | <400ms to first frame |
| Warm | App partially in memory (dylibs cached) | <200ms |
| Resume | App suspended, brought to foreground | Near-instant |

## Launch Phases

```
┌──────────┐   ┌──────────────┐   ┌─────────────┐   ┌─────────────┐
│   dyld   │──>│  Runtime Init │──>│  App Init    │──>│ First Frame │
│ (load    │   │ (+load, C++   │   │ (didFinish-  │   │ (initial    │
│  dylibs) │   │  constructors)│   │  Launching)  │   │  render)    │
└──────────┘   └──────────────┘   └─────────────┘   └─────────────┘
```

## Phase 1: dyld (Dynamic Linker)

Each dynamic library adds ~1–2ms to launch.

**Optimizations:**
- Minimize dynamic frameworks — prefer static linking
- Merge small frameworks into fewer targets
- Enable dead code stripping: `DEAD_CODE_STRIPPING = YES`

```
# Check dynamic library count
otool -L YourApp.app/YourApp | wc -l
```

## Phase 2: Runtime Initialization

**Avoid `+load` methods:**
```objc
// BAD: Runs at launch unconditionally
+ (void)load {
    [self swizzleMethod];
}

// GOOD: Runs lazily on first use
+ (void)initialize {
    if (self == [MyClass self]) {
        [self swizzleMethod];
    }
}
```

**Avoid global stored properties with complex initializers:**
```swift
// BAD: Initialized at launch
let heavyManager = HeavyManager()

// GOOD: Lazy initialization
lazy var heavyManager = HeavyManager()

// GOOD: Static let is lazy by default in Swift
class MyManager {
    static let shared = MyManager()
}
```

## Phase 3: App Initialization

```swift
// BAD: Blocking work in didFinishLaunching
func application(_ app: UIApplication,
    didFinishLaunchingWithOptions opts: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {

    Database.shared.initialize()     // blocks main thread
    Analytics.shared.configure()     // network call
    RemoteConfig.fetch()            // network call
    return true
}

// GOOD: Only critical-path work
func application(_ app: UIApplication,
    didFinishLaunchingWithOptions opts: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {

    setupCriticalUI()  // only what's needed for first frame

    // Defer non-critical initialization
    DispatchQueue.global(qos: .utility).async {
        Analytics.shared.configure()
    }

    // Defer even further for truly optional work
    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
        RemoteConfig.fetch()
    }

    return true
}
```

## Phase 4: First Frame

```swift
// SwiftUI: Use .task for async loading — never blocks first frame
struct RootView: View {
    @State private var items: [Item] = []

    var body: some View {
        Group {
            if items.isEmpty {
                SkeletonView()  // lightweight placeholder
            } else {
                ItemList(items: items)
            }
        }
        .task {
            items = await loadItems()
        }
    }
}
```

## Build Settings for Launch Performance

```
DEAD_CODE_STRIPPING = YES
SWIFT_OPTIMIZATION_LEVEL = -O            // Release only
SWIFT_COMPILATION_MODE = wholemodule     // Release only
GCC_OPTIMIZATION_LEVEL = -Os            // Optimize for size
```

## Profiling Launch Time

```bash
# Command line
xctrace record --template "App Launch" --launch -- /path/to/YourApp.app

# In Instruments
# Product → Profile → App Launch template
```

Key tracks to examine:
- **dyld** — library loading duration
- **Static Initializers** — `+load` and C++ constructor time
- **Main Thread** — blocking calls before first frame
- **Time Profiler** — CPU breakdown during launch

---

# App Terminations

## Termination Types

| Type | Exit Code | Cause |
|------|-----------|-------|
| Crash | Various | Unhandled exception, bad memory access |
| Watchdog Kill | `0x8badf00d` | App too slow to launch/suspend/resume |
| OOM Kill (Jetsam) | `0xc00010ff` | Excessive memory usage |
| Background Timeout | — | Background task exceeded time limit |
| Memory Pressure | Jetsam | System reclaiming memory from background apps |

## Watchdog Kills (0x8badf00d)

The system kills apps that take too long in critical transitions:

| Transition | Watchdog Timeout |
|------------|-----------------|
| Launch | ~20 seconds |
| Background transition | ~5–10 seconds |
| Resume | ~10 seconds |

**Prevention:** Never block the main thread during these transitions.

## OOM / Jetsam Kills

The system kills apps exceeding memory limits. Limits vary by device.

### Reduce Memory Usage

```swift
// Use autoreleasepool in tight loops
for url in imageURLs {
    autoreleasepool {
        let image = UIImage(contentsOfFile: url.path)
        process(image)
        // image is released at end of each iteration
    }
}
```

### Respond to Memory Warnings

```swift
// UIKit
override func didReceiveMemoryWarning() {
    super.didReceiveMemoryWarning()
    imageCache.removeAllObjects()
    temporaryData = nil
}

// Notification-based
NotificationCenter.default.addObserver(
    forName: UIApplication.didReceiveMemoryWarningNotification,
    object: nil, queue: .main
) { _ in
    self.clearCaches()
}
```

### Image Memory

A 4000×3000 image uses ~48MB of memory (4000 × 3000 × 4 bytes/pixel). Always downsample before display:

```swift
// Load a thumbnail instead of full-res
let options: [CFString: Any] = [
    kCGImageSourceCreateThumbnailFromImageAlways: true,
    kCGImageSourceThumbnailMaxPixelSize: 200,
    kCGImageSourceCreateThumbnailWithTransform: true
]
```

## Background Task Management

```swift
// Always call endBackgroundTask — even in expiration handler
var bgTaskID: UIBackgroundTaskIdentifier = .invalid

bgTaskID = UIApplication.shared.beginBackgroundTask {
    // Expiration handler — MUST end the task
    UIApplication.shared.endBackgroundTask(bgTaskID)
    bgTaskID = .invalid
}

// Do work...
UIApplication.shared.endBackgroundTask(bgTaskID)
bgTaskID = .invalid
```

For long-running background work, use `BGTaskScheduler`:
```swift
BGTaskScheduler.shared.register(
    forTaskWithIdentifier: "com.app.refresh",
    using: nil
) { task in
    handleAppRefresh(task: task as! BGAppRefreshTask)
}
```

## Monitoring Terminations in Production

### Xcode Organizer

`Window → Organizer → Crashes/Terminations` — shows field data including:
- Termination reason
- Memory footprint at time of kill
- Device/OS distribution

### MetricKit

```swift
func didReceive(_ payloads: [MXMetricPayload]) {
    for payload in payloads {
        // Launch metrics
        if let launch = payload.applicationLaunchMetrics {
            print("Time to first draw:", launch.histogrammedTimeToFirstDraw)
            print("Resume time:", launch.histogrammedApplicationResumeTime)
        }
    }
}

func didReceive(_ payloads: [MXDiagnosticPayload]) {
    for payload in payloads {
        // Crash diagnostics
        if let crashes = payload.crashDiagnostics {
            for crash in crashes { print(crash.callStackTree) }
        }
        // CPU exception diagnostics (thermal/energy kills)
        if let cpuExceptions = payload.cpuExceptionDiagnostics {
            for exc in cpuExceptions { print(exc.callStackTree) }
        }
    }
}
```

## Termination Prevention Checklist

- [ ] Launch-critical path completes in <20 seconds (watchdog)
- [ ] No synchronous network/IO in didFinishLaunching
- [ ] Memory warning handlers clear caches and release large resources
- [ ] Images downsampled before display
- [ ] autoreleasepool used in loops processing large data
- [ ] Background tasks always call endBackgroundTask in expiration handler
- [ ] BGTaskScheduler used for long background work (not UIBackgroundTask)
- [ ] Target <50MB memory in background state
