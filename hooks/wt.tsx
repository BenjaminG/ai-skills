/* @jsxRuntime classic */
/* @jsx h */
/* @jsxFrag Fragment */
import type { EngineInterface as Engine, Register } from 'claude-code'

const ID = 'wt'

type Worktree = {
  branch: string
  path: string
  is_current: boolean
  working_tree: {
    staged: boolean
    modified: boolean
    untracked: boolean
    diff: { added: number; deleted: number }
  }
  remote?: { ahead: number; behind: number } | null
}

/** `+12 −3 * ? ↑1 ↓2`: what worktrunk's table shows, as one dim string. */
function statusOf(w: Worktree): string {
  const { staged, modified, untracked, diff } = w.working_tree

  return [
    diff.added + diff.deleted > 0 ? `+${diff.added} −${diff.deleted}` : '',
    staged || modified ? '*' : '',
    untracked ? '?' : '',
    w.remote?.ahead ? `↑${w.remote.ahead}` : '',
    w.remote?.behind ? `↓${w.remote.behind}` : '',
  ]
    .filter(Boolean)
    .join(' ')
}

export const COMMAND = {
  name: ID,
  description:
    'worktrunk worktrees of this repo, a button per worktree entering it (EnterWorktree)',
} as const

// Module state: one hooks module runs per session. The loader lets `$` reach
// only functions declared at the module's top, so `refresh` and `enter` live here.
let worktrees: Worktree[] | null = null
let error: string | null = null
let isOpen = false

async function refresh($: Engine) {
  // ponytail: pinned to worktrunk's JSON schema 1; move to schema 2 ({ items }) when wt drops it
  const run = await $.process
    .run(['wt', 'list', '--format', 'json', '--config-set', 'list.json-schema=1'])
    .catch((e: unknown) => ({
      exitCode: 1,
      stdout: '',
      stderr: e instanceof Error ? e.message : String(e),
    }))

  if (run.exitCode === 0) {
    worktrees = JSON.parse(run.stdout) as Worktree[]
    error = null
  } else {
    error = run.stderr.trim() || `wt exited ${run.exitCode}`
  }

  $.ui.invalidate('ui.render')
}

async function enter($: Engine, w: Worktree) {
  const answer = await $.tool.call({
    tool: 'EnterWorktree',
    path: w.path,
    consent: `The user pressed "${w.branch}" in the Worktrees pane`,
  })

  $.ui.toast(answer.deny ?? `→ ${w.branch}`)
  void refresh($)
}

/** The pane's hooks; `session.start` registers COMMAND once for every pane, in register.ts. */
export const register: Register = on => {
  on('command.run', { command: ID }, async $ => {
    if (isOpen) {
      await $.ui.close({ id: ID })

      return { text: 'Worktrees panel hidden' }
    }

    isOpen = true
    await $.ui.open({ id: ID, title: 'Worktrees' })
    void refresh($)

    return { text: 'Worktrees panel shown' }
  })

  on('ui.close', { id: ID }, async ($, e, next) => {
    const result = await next(e)

    if (result.deny === undefined) {
      isOpen = false
    }

    return result
  })

  on('ui.render', { component: 'Pane', requestId: ID }, async ($, e, next) => {
    if (e.surface === 'mobile') {
      return next(e)
    }

    const { Box, Text, Button } = await $.ui.resolve(e)

    const rows = (worktrees ?? []).map(w => (
      <Box key={`wt:${w.branch}`} flexDirection="row" gap={1}>
        <Text color="cyan">{w.is_current ? '❯' : ' '}</Text>
        {w.is_current ? (
          <Text bold>{w.branch}</Text>
        ) : (
          <Button key={`wt:${w.branch}`} plain onPress={() => void enter($, w)}>
            {w.branch}
          </Button>
        )}
        <Text dimColor>{statusOf(w)}</Text>
        <Text dimColor wrap="truncate-start">
          {w.path}
        </Text>
      </Box>
    ))

    const note = error ?? (worktrees === null ? 'Loading…' : null)

    return (
      <Box flexDirection="column" paddingX={1}>
        <Text bold>{`Worktrees · ${worktrees?.length ?? '…'}`}</Text>
        {note === null ? null : <Text color={error ? 'red' : undefined} dimColor={!error}>{note}</Text>}
        {rows}
        <Text dimColor>Click a branch to enter its worktree · /wt to close</Text>
      </Box>
    )
  })
}
