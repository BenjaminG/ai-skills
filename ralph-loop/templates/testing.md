# Ralph Agent: {{GOAL}}

## Configuration

- **Source code**: `$SOURCE_PATH`
- **Test directory**: `$TEST_PATH`
- **Backlog**: `backlog.json` (files needing tests)
- **Progress**: `progress.txt`
- **Knowledge**: `knowledge.md`

## Your Task (One Iteration)

### Step 1: Load Context

1. Read `backlog.json` to get files needing tests
2. Read `knowledge.md` to understand testing patterns used

### Step 2: Determine State

Check the backlog:

- **If ALL files have `status: "tested"`** → Output `<promise>COMPLETE</promise>` and stop
- **If untested files exist** → Continue to Step 3

### Step 3: Select Target

Pick the FIRST file where `status: "pending"` (sorted by priority).
Mark it as `status: "in_progress"` in backlog.json.

### Step 4: Analyze Source

Read the target file to understand:
1. **Functions/Methods**: What needs to be tested?
2. **Edge cases**: What could go wrong?
3. **Dependencies**: What needs to be mocked?
4. **Existing tests**: Are there any tests already?

### Step 5: Write Tests

Create test file at the appropriate location:
- Follow project testing conventions
- Cover happy path and edge cases
- Mock external dependencies
- Use descriptive test names

```typescript
describe('ModuleName', () => {
  describe('functionName', () => {
    it('should handle normal case', () => {
      // Arrange
      // Act
      // Assert
    });

    it('should handle edge case', () => {
      // ...
    });
  });
});
```

### Step 6: Validate

Run the tests:
```bash
# Run specific test file
pnpm test -- path/to/test.spec.ts

# Or run all tests
pnpm test
```

**Acceptance Criteria:**
- [ ] All new tests pass
- [ ] No existing tests broken
- [ ] Reasonable coverage of the target file
- [ ] Tests are meaningful (not just coverage padding)

### Step 7: Update Files

**Update backlog.json:**
- Set file `status: "tested"`
- Add `testFile` path
- Add `testCount` number of tests written

**Update progress.txt:**
```
[datetime] - Tested: {file} | Tests: {count} | Status: pass
```

**Update knowledge.md:**
```markdown
---

## {FileName} (tested {date})

**Test File**: {path}

**Tests Written**: {count}

**Patterns Used**:
- {mocking pattern}
- {assertion pattern}

**Notes**:
- {anything notable}
```

## Important Rules

- Test ONLY 1 file per iteration
- Write meaningful tests, not just coverage
- Follow existing test conventions in the project
- Don't modify source code unless fixing obvious bugs

## Completion

When all files have `status: "tested"`:

```
<promise>COMPLETE</promise>
```
