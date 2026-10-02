import type { Register } from 'claude-code'

import { COMMAND as BABYSIT, register as registerBabysit } from './babysit'
import { register as registerFixupGuard } from './fixup-guard'
import { register as registerNextStep } from './next-step'
import { COMMAND as PRS, register as registerPrs } from './prs'
import { COMMAND as XRAY, register as registerXray } from './skill-xray'
import { COMMAND as WT, register as registerWt } from './wt'

/**
 * The plugin's one hooks module. One event may be hooked once without a
 * matcher per module, so `session.start` lives here and registers every
 * pane's command; each mod hooks its own events, and no two hook the same
 * one without a matcher. The loader reads `on` statically: it goes only to
 * functions imported by name.
 */
export const register: Register = (on, options) => {
  on('session.start', async ($, e, next) => {
    await $.command.register(PRS)
    await $.command.register(WT)
    await $.command.register(XRAY)
    await $.command.register(BABYSIT)

    return next(e)
  })

  registerPrs(on, options)
  registerWt(on, options)
  registerXray(on, options)
  registerNextStep(on, options)
  registerFixupGuard(on, options)
  registerBabysit(on, options)
}
