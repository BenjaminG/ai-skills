import { describe, expect, test } from 'claude-code/testing'

import { SESSION, world } from './fixtures'

const A = 'a'.repeat(40)
const B = 'b'.repeat(40)
const MAIN = 'c'.repeat(40)

// One modified hunk in src/x.ts (old lines 3-4), one new file: only the hunk blames.
const DIFF = `diff --git a/src/x.ts b/src/x.ts
--- a/src/x.ts
+++ b/src/x.ts
@@ -3,2 +3,2 @@ export function x() {
-  return 1
-  // old
+  return 2
+  // new
@@ -9,0 +10 @@
+// added only
diff --git a/src/new.ts b/src/new.ts
new file mode 100644
--- /dev/null
+++ b/src/new.ts
@@ -0,0 +1 @@
+export const y = 1
`

const FLAGS = '-U0 --no-color --no-ext-diff --src-prefix=a/ --dst-prefix=b/'

/**
 * A branch of two commits on origin/main whose lines 3-4 of src/x.ts come from `blamed`, the change
 * staged unless `staged` is false (then only in the working tree); `originHead` false: never set.
 */
const repo = (blamed: string, { staged = true, originHead = true } = {}) => (argv: readonly string[]) => {
  const command = argv.join(' ')

  if (command === 'git rev-parse --abbrev-ref origin/HEAD') return originHead ? { stdout: 'origin/main\n' } : { stderr: 'unknown revision' }
  if (command === 'git rev-list origin/main..HEAD') return { stdout: `${A}\n${B}\n` }
  if (command === `git diff --cached ${FLAGS}`) return { stdout: staged ? DIFF : '' }
  if (command === `git diff HEAD ${FLAGS}`) return { stdout: DIFF }
  if (command === 'git blame -l -s -L 3,+2 HEAD -- src/x.ts') {
    return { stdout: `${blamed} 3)   return 1\n^${blamed} 4)   // old\n` }
  }
  if (command === `git log -1 --format=%s ${A}`) return { stdout: 'feat: x returns a number\n' }

  return { stderr: `unexpected ${command}` }
}

const COMMIT = { tool: 'Bash', command: 'git commit -m "fix x"' } as const

describe('fixup-guard', () => {
  test('a commit touching lines of an earlier branch commit asks; Fixup refuses it with the fixup command', async ($, on) => {
    const w = world(on, { run: repo(A), ask: 'Fixup into aaaaaaa' })
    await $.session.start(SESSION)

    const answer = await $.tool.call(COMMIT)

    const asked = w.toolCalls.filter(c => c.tool === 'AskUserQuestion')
    expect(asked).toHaveLength(1)
    expect(JSON.stringify(asked[0])).toContain('feat: x returns a number')
    expect(w.toolCalls.some(c => c.tool === 'Bash'), 'the commit never ran').toBe(false)
    expect(JSON.stringify(answer)).toContain(`git commit --fixup=${A}`)
  })

  test('New commit lets the commit run', async ($, on) => {
    const w = world(on, { run: repo(A), ask: 'New commit' })
    await $.session.start(SESSION)

    await $.tool.call(COMMIT)

    expect(w.toolCalls.map(c => c.tool)).toEqual(['AskUserQuestion', 'Bash'])
  })

  test('lines from outside the branch, a fixup, or another git command run without asking', async ($, on) => {
    const w = world(on, { run: repo(MAIN), ask: 'Fixup into aaaaaaa' })
    await $.session.start(SESSION)

    await $.tool.call(COMMIT)
    await $.tool.call({ tool: 'Bash', command: `git commit --fixup=${A}` })
    await $.tool.call({ tool: 'Bash', command: 'git log --grep commit' })

    expect(w.toolCalls.map(c => c.tool)).toEqual(['Bash', 'Bash', 'Bash'])
  })

  test('only what the commit takes counts: the staged change, or the tree when the command stages it first', async ($, on) => {
    const w = world(on, { run: repo(A, { staged: false }), ask: 'New commit' })
    await $.session.start(SESSION)

    await $.tool.call(COMMIT)
    expect(w.toolCalls.map(c => c.tool), 'the rewrite is left unstaged').toEqual(['Bash'])

    await $.tool.call({ tool: 'Bash', command: 'git add src/x.ts && git commit -m "fix x"' })
    await $.tool.call({ tool: 'Bash', command: 'git commit -am "fix x"' })
    expect(w.toolCalls.map(c => c.tool)).toEqual(['Bash', 'AskUserQuestion', 'Bash', 'AskUserQuestion', 'Bash'])
  })

  test('a clone with no origin/HEAD still compares against origin/main', async ($, on) => {
    const w = world(on, { run: repo(A, { originHead: false }), ask: 'New commit' })
    await $.session.start(SESSION)

    await $.tool.call(COMMIT)

    expect(w.toolCalls.map(c => c.tool)).toEqual(['AskUserQuestion', 'Bash'])
  })

  test('a commit on a branch with nothing of its own runs without asking', async ($, on) => {
    const w = world(on, {
      run: argv => (argv.join(' ') === 'git rev-list origin/main..HEAD' ? { stdout: '' } : repo(A)(argv)),
      ask: 'Fixup into aaaaaaa',
    })
    await $.session.start(SESSION)

    await $.tool.call(COMMIT)

    expect(w.toolCalls.map(c => c.tool)).toEqual(['Bash'])
  })
})
