# Hitches & Rendering Performance

## What Is a Hitch?

A hitch occurs when a frame appears on screen later than expected, causing visible stuttering or jank during scrolling and animations.

```
Hitch Time = Actual Presentation Time − Expected Presentation Time
```

## The Render Loop

Each frame passes through two phases, each with a deadline:

```
┌─────────────────────┐    ┌─────────────────────────┐
│     App Phase        │───>│   Render Server Phase    │
│ (layout, display,    │    │ (render, composite,      │
│  prepare, commit)    │    │  display to screen)      │
└─────────────────────┘    └─────────────────────────┘
```

**Frame deadlines:**
- 60 Hz display: ~16.67ms per frame
- 120 Hz ProMotion: ~8.33ms per frame

## Types of Hitches

| Type | Phase | Cause |
|------|-------|-------|
| **Commit Hitch** | App phase | Layout too expensive, too many views updated, heavy `body` computation |
| **Render Hitch** | Render server | Offscreen rendering, complex layer effects, too many transparent layers |

## Hitch Time Ratio

The key metric for hitch severity:

```
Hitch Time Ratio = Total Hitch Time (ms) / Scroll Duration (s)
```

| Rating | Ratio | Meaning |
|--------|-------|---------|
| Good | <5 ms/s | Smooth experience |
| Warning | 5–10 ms/s | Occasional visible jank |
| Critical | >10 ms/s | Clearly broken scrolling |

## Commit Hitch Fixes

### Reduce layout passes

```swift
// BAD: Forces multiple layout passes
VStack {
    GeometryReader { geo in
        // Reading geometry triggers additional layout
        Text("Width: \(geo.size.width)")
    }
    // More views that depend on geometry...
}

// GOOD: Minimize GeometryReader usage, prefer fixed sizes
VStack {
    Text("Content")
        .frame(maxWidth: .infinity)
}
```

### Avoid expensive work in body

```swift
// BAD: DateFormatter created every body call
var body: some View {
    Text(DateFormatter.localizedString(from: date, dateStyle: .medium, timeStyle: .short))
}

// GOOD: Cached formatter
private static let formatter: DateFormatter = {
    let f = DateFormatter()
    f.dateStyle = .medium
    f.timeStyle = .short
    return f
}()

var body: some View {
    Text(Self.formatter.string(from: date))
}
```

### Batch state updates

```swift
// BAD: Multiple state changes trigger multiple body evaluations
func handleResponse(_ response: Response) {
    title = response.title       // triggers body
    subtitle = response.subtitle // triggers body again
    items = response.items       // triggers body again
}

// GOOD: Single state object = single invalidation
struct ViewState {
    var title: String
    var subtitle: String
    var items: [Item]
}

@State private var state = ViewState(...)

func handleResponse(_ response: Response) {
    state = ViewState(
        title: response.title,
        subtitle: response.subtitle,
        items: response.items
    )  // single body evaluation
}
```

## Render Hitch Fixes

### Avoid offscreen rendering

```swift
// EXPENSIVE: masksToBounds triggers offscreen render pass
view.layer.cornerRadius = 10
view.layer.masksToBounds = true  // forces offscreen render

// CHEAPER: cornerRadius alone (without masking) uses GPU fast-path
view.layer.cornerRadius = 10
// Only add masksToBounds if content actually overflows

// BEST in SwiftUI: .clipShape is optimized
Image("photo")
    .clipShape(RoundedRectangle(cornerRadius: 10))
```

### Minimize transparency and overdraw

```swift
// BAD: Transparent layers cause blending on every frame
ZStack {
    Color.white
    Color.blue.opacity(0.3)
    Color.red.opacity(0.5)
    Text("Hello")
}

// GOOD: Use opaque colors where possible
ZStack {
    Color(red: 0.65, green: 0.3, blue: 0.5)  // pre-blended
    Text("Hello")
}
```

In UIKit:
```swift
view.isOpaque = true
view.backgroundColor = .white  // opaque background avoids blending
```

### Shadow optimization

```swift
// EXPENSIVE: Shadow without path requires render server to compute shape
view.layer.shadowColor = UIColor.black.cgColor
view.layer.shadowOpacity = 0.5
view.layer.shadowRadius = 4

// FASTER: Provide explicit shadow path
view.layer.shadowPath = UIBezierPath(
    roundedRect: view.bounds,
    cornerRadius: view.layer.cornerRadius
).cgPath
```

In SwiftUI:
```swift
// Use .shadow modifier — SwiftUI optimizes automatically
RoundedRectangle(cornerRadius: 10)
    .shadow(radius: 4)
```

### Rasterize complex static content

```swift
// For complex but static view hierarchies
view.layer.shouldRasterize = true
view.layer.rasterizationScale = UIScreen.main.scale
```

**Warning:** Only rasterize content that doesn't change frequently. Rasterizing animated content is worse than not rasterizing.

## Scroll Performance in SwiftUI

### Cell prefetching with List

`List` handles prefetching automatically. For custom scroll views:

```swift
ScrollView {
    LazyVStack(spacing: 8) {
        ForEach(items) { item in
            ItemCell(item: item)
                .task {
                    // Prefetch next page when near the end
                    if item == items.last {
                        await loadMoreItems()
                    }
                }
        }
    }
}
```

### Avoid identity changes during scroll

```swift
// BAD: Changing id during scroll destroys and recreates cells
ForEach(items) { item in
    ItemRow(item: item)
        .id(item.id + String(item.updatedAt))  // changes when item updates
}

// GOOD: Stable identity
ForEach(items) { item in
    ItemRow(item: item)  // uses item.id from Identifiable conformance
}
```

### Fixed-size cells

```swift
// Helps SwiftUI skip expensive sizing passes
LazyVStack(spacing: 0) {
    ForEach(items) { item in
        ItemRow(item: item)
            .frame(height: 60)  // known fixed height
    }
}
```

## XCTest Scroll Performance Metrics

```swift
func testScrollPerformance() throws {
    let app = XCUIApplication()
    app.launch()

    let metrics: [XCTMetric] = [
        XCTOSSignpostMetric.scrollDecelerationMetric,
        XCTOSSignpostMetric.scrollDraggingMetric
    ]

    measure(metrics: metrics) {
        let list = app.tables.firstMatch
        list.swipeUp(velocity: .fast)
    }
}

func testAnimationPerformance() throws {
    let app = XCUIApplication()
    app.launch()

    measure(metrics: [XCTOSSignpostMetric.navigationTransitionMetric]) {
        app.buttons["Navigate"].tap()
        app.navigationBars.buttons.element(boundBy: 0).tap()
    }
}
```

## Profiling Workflow for Hitches

1. **Open Instruments** → Animation Hitches template
2. **Record** a scroll or animation interaction on a physical device
3. **Identify hitch type** — commit hitch (app phase) or render hitch (render server)
4. **For commit hitches:** Switch to Time Profiler, drill into the heaviest stack frame during the frame
5. **For render hitches:** Use Core Animation instrument, look for offscreen rendering and overdraw
6. **Fix** and re-measure with XCTest performance tests
