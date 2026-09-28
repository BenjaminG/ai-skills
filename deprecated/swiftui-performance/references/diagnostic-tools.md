# Diagnostic Tools

## Instruments Templates

### SwiftUI Template

Tracks SwiftUI-specific performance:
- **View body invocations** — how often each view's `body` is called
- **Attribute graph updates** — dependency changes that trigger re-evaluation
- **View creation/destruction** — identity changes causing view lifecycle events

```
Product → Profile → SwiftUI
```

Use when: Views redraw too often, unclear which state change triggers which views.

### Time Profiler

Shows CPU usage per thread with call stacks:
- Identify the heaviest functions on the main thread
- Find CPU-bound work that should move to background

```
Product → Profile → Time Profiler
```

Use when: App feels slow, main thread blocked, hangs during interactions.

### Animation Hitches (Hitches Instrument)

Detects frames delivered late during scrolling and animations:
- Hitch type (commit vs render)
- Hitch duration and time ratio
- Correlated with app and render server phases

```
Product → Profile → Animation Hitches
```

Use when: Scrolling stutters, animations jank, frame drops.

### App Launch

Profiles the entire launch sequence:
- dyld (library loading)
- Static initializers
- App delegate initialization
- Time to first frame

```
Product → Profile → App Launch
```

Use when: App takes too long to appear after tap.

### Allocations + Leaks

Tracks memory usage over time:
- **Allocations** — total memory footprint, growth over time, largest allocations
- **Leaks** — retained objects with no references (retain cycles)

```
Product → Profile → Allocations (or Leaks)
```

Use when: Memory grows unbounded, OOM crashes, suspected retain cycles.

### System Trace

Low-level thread scheduling and system calls:
- Thread state transitions (running, blocked, waiting)
- Lock contention
- Priority inversion

```
Product → Profile → System Trace
```

Use when: Suspect lock contention, deadlocks, priority inversion.

### Core Animation

Rendering performance:
- FPS counter
- Offscreen rendering detection (yellow overlay)
- Blended layers (red/green overlay)

Use when: Render hitches, excessive overdraw, offscreen rendering.

## Command-Line Profiling

```bash
# Record app launch trace
xctrace record --template "App Launch" --launch -- /path/to/App.app

# Record time profile for running app
xctrace record --template "Time Profiler" --attach <PID> --time-limit 10s

# List available templates
xctrace list templates

# Export trace to file
xctrace export --input recording.trace --output results.xml
```

## os_signpost (Custom Intervals)

Mark custom intervals in your code for Instruments visualization:

```swift
import os.signpost

let log = OSLog(subsystem: "com.myapp", category: "Performance")

// Point-of-interest (single event)
os_signpost(.event, log: log, name: "UserTapped")

// Interval (begin/end pair)
let id = OSSignpostID(log: log)
os_signpost(.begin, log: log, name: "DataLoad", signpostID: id)
// ... work ...
os_signpost(.end, log: log, name: "DataLoad", signpostID: id)
```

In Instruments, these appear in the **Points of Interest** track or custom `os_signpost` track.

### SwiftUI-specific signposts

```swift
import os.signpost

struct ExpensiveView: View {
    private static let signpostLog = OSLog(subsystem: "com.myapp", category: "SwiftUI")

    var body: some View {
        let _ = Self.signpostLog.signpost("ExpensiveView body") {
            // This measures body evaluation time in Instruments
        }
        // actual view content...
        Text("Hello")
    }
}
```

## MetricKit (Production Monitoring)

Collect performance data from real users in the field:

```swift
import MetricKit

class AppMetricsSubscriber: NSObject, MXMetricManagerSubscriber {

    func register() {
        MXMetricManager.shared.add(self)
    }

    // Called ~once per day with aggregated metrics
    func didReceive(_ payloads: [MXMetricPayload]) {
        for payload in payloads {
            // Responsiveness (hangs)
            if let responsiveness = payload.applicationResponsivenessMetrics {
                log("Hang count: \(responsiveness)")
            }

            // Launch time
            if let launch = payload.applicationLaunchMetrics {
                log("Time to first draw: \(launch.histogrammedTimeToFirstDraw)")
                log("Resume time: \(launch.histogrammedApplicationResumeTime)")
            }

            // Animation hitches
            if let animation = payload.animationMetrics {
                log("Scroll hitch ratio: \(animation.scrollHitchTimeRatio)")
            }

            // Memory
            if let memory = payload.memoryMetrics {
                log("Peak memory: \(memory.peakMemoryUsage)")
            }
        }
    }

    // Called when diagnostic reports are available
    func didReceive(_ payloads: [MXDiagnosticPayload]) {
        for payload in payloads {
            // Hang diagnostics with call stacks
            if let hangs = payload.hangDiagnostics {
                for hang in hangs {
                    log("Hang stack: \(hang.callStackTree)")
                }
            }

            // CPU exceptions
            if let cpuExceptions = payload.cpuExceptionDiagnostics {
                for exc in cpuExceptions {
                    log("CPU exception: \(exc.callStackTree)")
                }
            }

            // Crash reports
            if let crashes = payload.crashDiagnostics {
                for crash in crashes {
                    log("Crash: \(crash.callStackTree)")
                }
            }
        }
    }
}
```

Register in your App or AppDelegate:
```swift
@main
struct MyApp: App {
    let metricsSubscriber = AppMetricsSubscriber()

    init() {
        metricsSubscriber.register()
    }

    var body: some Scene {
        WindowGroup { ContentView() }
    }
}
```

## XCTest Performance Metrics

Automate performance regression testing:

```swift
// Scroll performance
func testScrollPerformance() throws {
    let app = XCUIApplication()
    app.launch()

    measure(metrics: [
        XCTOSSignpostMetric.scrollDecelerationMetric,
        XCTOSSignpostMetric.scrollDraggingMetric
    ]) {
        app.tables.firstMatch.swipeUp(velocity: .fast)
    }
}

// Launch performance
func testLaunchPerformance() throws {
    measure(metrics: [XCTApplicationLaunchMetric()]) {
        XCUIApplication().launch()
    }
}

// Navigation transition
func testNavigationPerformance() throws {
    let app = XCUIApplication()
    app.launch()

    measure(metrics: [XCTOSSignpostMetric.navigationTransitionMetric]) {
        app.buttons["Detail"].tap()
        app.navigationBars.buttons.firstMatch.tap()
    }
}

// Custom metric
func testCustomOperation() throws {
    measure(metrics: [XCTClockMetric()]) {
        // operation to measure
        performExpensiveOperation()
    }
}
```

Set baselines in Xcode: after first run, click the diamond icon in the gutter to set a performance baseline. Future runs compare against it.

## Xcode Organizer (Field Data)

`Window → Organizer` in Xcode shows aggregated metrics from TestFlight and App Store users:

| Tab | Data |
|-----|------|
| **Crashes** | Crash logs with symbolicated stacks |
| **Hangs** | Hang reports with stack traces |
| **Disk Writes** | Excessive I/O |
| **Launch Time** | Histogram of launch durations |
| **Memory** | Peak memory usage |
| **Scrolling** | Hitch rate data |

Requires: App distributed via TestFlight or App Store, user opt-in to share diagnostics.

## Xcode View Debugger

For SwiftUI hierarchy inspection:
```
Debug → View Debugging → Capture View Hierarchy
```

Shows:
- 3D exploded view of the layer tree
- View count and depth
- Memory usage per view
- Constraint conflicts (UIKit)
