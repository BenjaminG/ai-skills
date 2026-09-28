# SwiftUI View Performance

## View Identity

SwiftUI tracks views using two identity mechanisms:

**Structural identity** — position in the view hierarchy. SwiftUI infers identity from where a view appears in the `body` computation. Changing structure (e.g., wrapping in an `if`) can cause SwiftUI to destroy and recreate views.

**Explicit identity** — `.id()` modifier. Forces SwiftUI to treat a view as new when the ID changes.

```swift
// Changing .id() destroys and recreates the view — use intentionally
List(items) { item in
    ItemRow(item: item)
        // DON'T change .id() unless you need to force recreation
}
```

**Rule:** Preserve structural identity across state changes. Use `if/else` branches carefully — SwiftUI may destroy and recreate views when switching branches.

## Dependency Tracking & Invalidation

SwiftUI only re-evaluates `body` for views whose dependencies changed. The framework tracks which properties each view reads.

```swift
// Fine-grained @State reduces unnecessary redraws
struct ParentView: View {
    @State private var count = 0
    @State private var name = ""

    var body: some View {
        CounterView(count: count)  // only redraws when count changes
        NameView(name: name)       // only redraws when name changes
    }
}
```

**Common mistake:** Putting all state in one large object invalidates every observing view on any change.

## @Observable vs ObservableObject

### @Observable (iOS 17+) — Preferred

Fine-grained property tracking. Only views that read a specific property re-evaluate when that property changes.

```swift
@Observable
class Store {
    var count = 0
    var name = ""
}

struct CounterView: View {
    var store: Store

    var body: some View {
        // Only invalidates when store.count changes
        // Changing store.name has NO effect on this view
        Text("\(store.count)")
    }
}
```

### ObservableObject (Legacy)

Any `@Published` change invalidates ALL observing views.

```swift
class OldStore: ObservableObject {
    @Published var count = 0
    @Published var name = ""
    // Changing EITHER property triggers ALL observing views to re-evaluate
}
```

**Migration path:** Replace `ObservableObject` + `@Published` + `@StateObject`/`@ObservedObject` with `@Observable` + `@State` for local ownership.

## Expensive Body Computations

The `body` property is called frequently. Keep it fast.

```swift
// BAD: Heavy computation in body
var body: some View {
    Text(expensiveComputation())
}

// GOOD: Cache result, recompute only when dependency changes
struct MyView: View {
    let data: [Item]

    private var processedData: [Item] {
        data.filter { $0.isValid }.sorted { $0.date > $1.date }
    }

    var body: some View {
        List(processedData) { item in ItemRow(item: item) }
    }
}
```

For truly expensive computations, use `.task` to run off the main thread:

```swift
struct HeavyView: View {
    let rawData: [RawItem]
    @State private var processed: [ProcessedItem] = []

    var body: some View {
        List(processed) { item in ItemRow(item: item) }
            .task(id: rawData.hashValue) {
                processed = await processInBackground(rawData)
            }
    }
}
```

## Lazy Containers

`VStack` / `HStack` evaluate ALL children immediately. `LazyVStack` / `LazyHStack` only evaluate visible children.

```swift
// BAD for large datasets — renders ALL 10,000 rows
ScrollView {
    VStack {
        ForEach(largeArray) { item in ItemRow(item: item) }
    }
}

// GOOD — only renders visible rows
ScrollView {
    LazyVStack {
        ForEach(largeArray) { item in ItemRow(item: item) }
    }
}
```

`List` is lazy by default. Use `LazyVGrid` / `LazyHGrid` for grid layouts.

## Avoiding AnyView

`AnyView` erases type information, preventing SwiftUI from diffing efficiently. It also breaks structural identity.

```swift
// BAD: Type erasure kills optimization
func makeView(for state: ViewState) -> AnyView {
    switch state {
    case .a: return AnyView(ViewA())
    case .b: return AnyView(ViewB())
    }
}

// GOOD: @ViewBuilder preserves type information
@ViewBuilder
func makeView(for state: ViewState) -> some View {
    switch state {
    case .a: ViewA()
    case .b: ViewB()
    }
}
```

## Equatable Views

Implement `Equatable` to give SwiftUI a fast comparison path, skipping body re-evaluation when nothing changed.

```swift
struct ItemRow: View, Equatable {
    let item: Item

    static func == (lhs: ItemRow, rhs: ItemRow) -> Bool {
        lhs.item.id == rhs.item.id && lhs.item.updatedAt == rhs.item.updatedAt
    }

    var body: some View {
        HStack {
            Text(item.title)
            Spacer()
            Text(item.subtitle)
        }
    }
}
```

## Image Performance

Large images cause memory pressure and slow rendering.

```swift
// Always constrain image size
Image("largePhoto")
    .resizable()
    .scaledToFit()
    .frame(width: 100, height: 100)

// AsyncImage with proper sizing
AsyncImage(url: url) { image in
    image.resizable().scaledToFill()
} placeholder: {
    ProgressView()
}
.frame(width: 200, height: 200)
.clipped()
```

For thumbnails, downsample at load time rather than loading full-res and scaling with a frame modifier:

```swift
func downsample(imageAt url: URL, to size: CGSize) -> UIImage? {
    let options = [kCGImageSourceShouldCache: false] as CFDictionary
    guard let source = CGImageSourceCreateWithURL(url as CFURL, options) else { return nil }

    let maxDimension = max(size.width, size.height) * UIScreen.main.scale
    let downsampleOptions = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceThumbnailMaxPixelSize: maxDimension,
        kCGImageSourceCreateThumbnailWithTransform: true
    ] as CFDictionary

    guard let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, downsampleOptions) else { return nil }
    return UIImage(cgImage: cgImage)
}
```

## drawingGroup() for Complex Graphics

Flattens a complex view hierarchy into a single Metal-rendered layer. Use for complex shapes, gradients, and animations.

```swift
ZStack {
    ForEach(0..<100) { i in
        Circle()
            .fill(Color.blue.opacity(Double(i) / 100))
            .frame(width: CGFloat(i) * 3)
    }
}
.drawingGroup()  // renders offscreen via Metal, composites as one layer
```

**When to use:** Many overlapping layers, complex gradients, particle effects. **When NOT to use:** Simple views — the overhead of offscreen rendering outweighs the benefit.
