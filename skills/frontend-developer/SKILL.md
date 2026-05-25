---
name: frontend-developer
description: Specialist for modern React applications, TypeScript frontend code, UI development, TanStack Query, component creation, CSS styling, responsive design, accessibility, form validation, state management, routing, and performance optimization. Use for ANY work involving .tsx/.jsx files, React components, frontend bugs, or client-side development tasks.
---

# Frontend Developer

## Overview

This skill provides expertise in modern frontend development with React, TypeScript, and current best practices. Apply this skill when building components, fixing frontend bugs, optimizing performance, or ensuring accessibility compliance.

## Core Principles

### React Development Standards

**Component Architecture:**
- Use functional components with hooks exclusively
- Implement single responsibility principle - separate UI from business logic
- Prefer composition over conditional rendering
- Extract complex logic into custom hooks prefixed with "use"
- Implement proper cleanup in useEffect for subscriptions and timers

**Custom Hooks:**
- Always prefix custom hooks with "use" (e.g., `useOnlineStatus`)
- Keep hooks focused on a single concern
- Return stable object references to prevent unnecessary re-renders
- Clean up all side effects (subscriptions, timers, async operations)

Example implementation:
```jsx
function useOnlineStatus() {
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return isOnline;
}
```

### State Management

**Core Principles:**
- **Derive state, don't sync it** - Calculate values during render instead of managing multiple related state variables
- Implement single sources of truth to prevent synchronization bugs
- Handle async state properly with loading and error states
- Use React Context for shared state across component trees

**When to use useReducer vs useState:**

Use **useReducer** when:
- State has multiple sub-values that change together
- Next state depends on previous state values
- Complex state transitions with multiple actions
- State logic becomes difficult to test inline
- Calling multiple setState functions in sequence

Use **useState** when:
- Simple primitive values (boolean, string, number)
- Independent state variables
- Straightforward state updates without complex logic

**useReducer Example:**
```jsx
const initialFormState = {
  data: { name: '', email: '', company: '' },
  loading: false,
  errors: {},
  submitted: false
};

function formReducer(state, action) {
  switch (action.type) {
    case 'FIELD_CHANGE':
      return {
        ...state,
        data: { ...state.data, [action.field]: action.value },
        errors: { ...state.errors, [action.field]: null }
      };
    case 'SUBMIT_START':
      return { ...state, loading: true, errors: {}, submitted: false };
    case 'SUBMIT_SUCCESS':
      return { ...state, loading: false, submitted: true };
    case 'SUBMIT_ERROR':
      return { ...state, loading: false, errors: action.errors };
    case 'RESET':
      return initialFormState;
    default:
      return state;
  }
}
```

**State Derivation Example:**
```jsx
// ✅ Good - Single source with derived values
function GameBoard() {
  const [squares, setSquares] = useState(Array(9).fill(null));

  // Derive these instead of managing as separate state
  const winner = calculateWinner(squares);
  const nextPlayer = calculateNextPlayer(squares);
  const status = calculateStatus(winner, squares, nextPlayer);

  return <div>{status}</div>;
}

// ❌ Bad - Manual synchronization of multiple state variables
function GameBoard() {
  const [squares, setSquares] = useState(Array(9).fill(null));
  const [winner, setWinner] = useState(null);
  const [nextPlayer, setNextPlayer] = useState('X');
  const [status, setStatus] = useState('Next player: X');

  // Manually sync all related state - error-prone!
  useEffect(() => {
    const newWinner = calculateWinner(squares);
    const newNextPlayer = calculateNextPlayer(squares);
    const newStatus = calculateStatus(newWinner, squares, newNextPlayer);

    setWinner(newWinner);
    setNextPlayer(newNextPlayer);
    setStatus(newStatus);
  }, [squares]);
}
```

### TypeScript & Type Safety

**Strict Typing:**
- Use strict typing, avoid `any` type
- Define interfaces for object shapes and component props
- Use Zod schemas for runtime validation and type inference
- Always use `z.infer<typeof schema>` to derive types from Zod schemas
- Implement proper error boundaries for type-safe error handling

### Performance Optimization

**Optimization Strategy:**
- Implement code splitting and lazy loading for routes and components
- Use virtualization (react-window, react-virtuoso) for large lists
- Optimize images with proper sizing and lazy loading
- Minimize bundle size through tree shaking and dead code elimination
- Profile performance with React DevTools and browser tools

**Memoization Guidelines:**
- Use `useMemo` ONLY for expensive computations - measure first!
- Use `useCallback` for callback functions passed to memoized child components
- Use `React.memo` for expensive components to avoid unnecessary re-renders

Example:
```jsx
// ✅ Good - Use useMemo ONLY for expensive derived calculations
function ExpensiveComponent() {
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState('');

  // Only for computationally expensive operations - measure first!
  const filteredAndSortedItems = useMemo(() => {
    return items
      .filter(item => item.name.includes(filter))
      .sort((a, b) => expensiveComparisonFunction(a, b));
  }, [items, filter]);

  return <ItemList items={filteredAndSortedItems} />;
}
```

### React SOLID Principles

**Single Responsibility:**
Separate data fetching logic from UI rendering.

```jsx
// ✅ Good - Custom hook handles data fetching
function useUserData(fetchUser) {
  const [user, setUser] = useState(null);
  useEffect(() => {
    fetchUser().then(setUser);
  }, [fetchUser]);
  return user;
}

function UserCard({ fetchUser }) {
  const user = useUserData(fetchUser);
  if (!user) return <p>Loading...</p>;
  return (
    <div>
      <h2>{user.name}</h2>
      <p>{user.email}</p>
    </div>
  );
}
```

**Open/Closed Principle:**
Extend behavior via composition, not modification.

```jsx
// ✅ Good - Composable Alert component
function Alert({ className, children }) {
  return <div className={className}>{children}</div>;
}

const SuccessAlert = ({ message }) => (
  <Alert className="alert-success">{message}</Alert>
);

const ErrorAlert = ({ message }) => (
  <Alert className="alert-error">{message}</Alert>
);
```

### TanStack Query Best Practices

**Optimistic Updates:**
```tsx
const mutation = useMutation({
  mutationFn: createItem,
  onMutate: async newItem => {
    // Cancel outgoing refetches
    await queryClient.cancelQueries({ queryKey: ['items'] });

    // Snapshot previous value
    const previousItems = queryClient.getQueryData(['items']);

    // Optimistically update cache
    queryClient.setQueryData(['items'], old => [...old, newItem]);

    // Return context with snapshot
    return { previousItems };
  },
  onError: (err, newItem, context) => {
    // Rollback on error
    queryClient.setQueryData(['items'], context.previousItems);
  },
  onSettled: () => {
    // Refetch after error or success
    queryClient.invalidateQueries(['items']);
  },
});
```

### Accessibility Standards

**Essential Requirements:**
- Use semantic HTML elements (button, nav, main, section)
- Implement proper ARIA labels and roles
- Ensure keyboard navigation support with proper focus management
- Maintain color contrast ratios meeting WCAG AA standards
- Test with screen readers and accessibility tools

### Code Organization

**Import and File Structure:**
- Follow ordered imports: builtin → external → internal → parent → sibling
- Use absolute imports for cleaner dependency management
- Organize by feature domains with clear boundaries
- Extract conditional logic into well-named variables
- Group related functionality in cohesive modules

## Implementation Workflow

When applying this skill to frontend development tasks:

1. **Analyze Requirements**: Understand the specific frontend task - component creation, bug fixing, performance optimization, or accessibility improvements

2. **Review Existing Code**: Use Read/Grep to examine current implementation and identify patterns or issues

3. **Apply Best Practices**: Implement solutions following React best practices, TypeScript strict typing, and performance guidelines outlined above

4. **Ensure Quality**: Verify responsive design, accessibility compliance, and optimal performance

5. **Test Implementation**: Validate the solution works across different scenarios and edge cases

## Common Anti-Patterns to Avoid

**State Management:**
- ❌ Using multiple useState calls for interdependent state
- ❌ Syncing state manually with useEffect
- ❌ Creating derived state instead of computing during render

**Performance:**
- ❌ Premature optimization with useMemo before measuring
- ❌ Using useCallback without React.memo on child components
- ❌ Deeply nested component trees without lazy loading

**TypeScript:**
- ❌ Using `any` type to bypass type checking
- ❌ Missing prop interfaces for components
- ❌ Ignoring type errors with `@ts-ignore`

**Accessibility:**
- ❌ Using div instead of button for clickable elements
- ❌ Missing alt text on images
- ❌ Insufficient color contrast
- ❌ No keyboard navigation support
