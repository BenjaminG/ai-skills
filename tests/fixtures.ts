import type {
  CommandRunInput,
  On,
  RenderInput,
  SessionStartInput,
} from 'claude-code'
import { mock } from 'claude-code/testing'

export const PLUGIN = 'ai-skills'

export const SESSION: SessionStartInput = {
  surface: 'terminal',
  isInteractive: true,
  cwd: '/work',
}

/** `/<name> <args>` typed fullscreen on a 160-column terminal. */
export const command = (name: string, args = ''): CommandRunInput => ({
  command: name,
  args,
  origin: { kind: 'composer' },
  presentation: { isFullscreen: true, columns: 160 },
})

/** The pane `id` docked on a 160-column terminal, 80 columns of body. */
export const pane = (id: string): RenderInput<'Pane'> => ({
  component: 'Pane',
  surface: 'terminal',
  requestId: id,
  viewport: { columns: 160, rows: 40 },
  props: {
    title: id,
    isFocused: false,
    bodyColumns: 80,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
})

/** A row of pr-dash's state.json (schema v4): an open PR in review, green, nothing waiting on anyone. */
export const stateRow = (number: number, over: Record<string, unknown> = {}) => ({
  number,
  url: `https://github.com/o/n/pull/${number}`,
  title: `PR ${number}`,
  author: 'me',
  draft: false,
  branch: `feat/${number}`,
  base: 'dev',
  merge_state: 'BLOCKED',
  stack: null,
  stack_pos: null,
  mergeable: 'MERGEABLE',
  queued: false,
  ci: 'SUCCESS',
  head: 'aaaaaaa',
  additions: 1,
  deletions: 0,
  files: 1,
  unresolved_bot: 0,
  unresolved_human: 0,
  held: 0,
  humans: [],
  threads_bot_open: 0,
  threads_bot_closed: 0,
  threads_human_open: 0,
  threads_human_closed: 0,
  seen: {},
  status: 'review',
  merge_ready: false,
  parent: null,
  stack_members: [number],
  needs_agent: false,
  waits_on: null,
  agent_running: false,
  report: null,
  ...over,
})

/** state.json's text, as pr-dash's Scan service writes it. */
export const stateOf = (prs: object[], over: Record<string, unknown> = {}) =>
  JSON.stringify({ schema_version: 4, taken_at: '2026-10-24T10:00:00.000Z', repo: 'o/n', error: null, prs, ...over })

type Answer = { stdout?: string; stderr?: string; exitCode?: number }

/**
 * The world beneath the plugin: a session in /work, one process answering
 * `stdout` (or failing with `stderr`), or `run` answering per argv (a throw is a
 * command that cannot start); panes,
 * prompt fills and suggestions kept; the AskUserQuestion dialog answered `ask`.
 */
export function world(on: On, process: Answer & { run?: (argv: readonly string[]) => Answer; ask?: string }) {
  const runs: string[][] = []
  const opened: string[] = []
  const closed: string[] = []
  const filled: string[] = []
  const suggested: string[] = []
  const toasts: string[] = []
  const toolCalls: Record<string, unknown>[] = []

  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('command.register', ($, e) => ({ value: { command: e.name } }))

  on('process.run', ($, e) => {
    runs.push([...e.argv])

    const answer: Answer = process.run?.(e.argv) ?? process

    return {
      value: {
        exitCode: answer.stderr === undefined ? 0 : (answer.exitCode ?? 1),
        stdout: answer.stdout ?? '',
        stderr: answer.stderr ?? '',
        isStdoutTruncated: false,
        isStderrTruncated: false,
      },
    }
  })

  on('ui.open', ($, e) => {
    opened.push(e.id)

    return { value: { isPlaced: true } }
  })

  on('ui.close', ($, e) => {
    closed.push(e.id)

    return { value: undefined }
  })

  on('ui.invalidate', () => ({ value: undefined }))

  on('ui.toast', ($, e) => {
    toasts.push(e.text)

    return { value: undefined }
  })

  on('prompt.fill', ($, e) => {
    filled.push(e.text)

    return { isFilled: true }
  })

  on('prompt.suggest', ($, e) => {
    suggested.push(e.text)

    return { isShown: true }
  })

  on('tool.call', ($, e) => {
    toolCalls.push({ ...e })

    if (e.tool === 'AskUserQuestion' && process.ask !== undefined) {
      const question = (e as { questions?: { question: string }[] }).questions?.[0]?.question ?? ''

      return { result: { questions: [], answers: { [question]: process.ask } } }
    }

    return { result: 'ok' }
  })

  const clock = mock.clock(on)

  return { runs, opened, closed, filled, suggested, toasts, toolCalls, clock }
}

/** A rendered tree's text as it reads: strings and Button labels, in order. */
export function textOf(tree: unknown): string {
  if (typeof tree === 'string' || typeof tree === 'number') {
    return String(tree)
  }

  if (Array.isArray(tree)) {
    return tree.map(textOf).join('')
  }

  if (typeof tree !== 'object' || !tree) {
    return ''
  }

  const props: unknown = Reflect.get(tree, 'props')
  const label: unknown =
    typeof props === 'object' && props ? Reflect.get(props, 'label') : ''

  return `${typeof label === 'string' ? label : ''}${textOf(Reflect.get(tree, 'children') ?? [])}`
}
