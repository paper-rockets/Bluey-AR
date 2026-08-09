# Rules

## Verification is not optional

Never report work as done, working, or complete without having run it.
"Should work" and "the code looks correct" are not completion.

For anything browser-based:

1. Start the server and open the page.
2. Read the browser console. Zero errors before claiming success.
3. Confirm the thing you built is actually visible and moving/responding — not
   merely that the file parsed.
4. Test the failure path too: deny the camera, kill the network, load in a
   background tab. An app that only survives the happy path is not done.
5. State what you verified and what you could not. If you could not run it, say
   so in the first line of the reply.

## Traps in this codebase

These are real bugs that have already been shipped here. Do not repeat them.

- **`rig.play()` sets the clip AND resets its start time.** Call it on state
  *change* only. Calling it every frame pins the clip at t=0 and nothing
  animates — the model stands frozen while looking superficially alive, because
  the spring/secondary motion still runs off absolute time. The engine now
  guards against this, but don't rely on the guard.
- **Optional subsystems must never gate the core experience.** The camera,
  MediaPipe and the network are all optional. Hide loading overlays in a
  `finally`, never only on the success path — a denied camera once left an
  opaque overlay covering a perfectly good render, forever.
- **Don't enable shadows unless something sets `receiveShadow`.** These scenes
  have no ground. A shadow map that nothing samples is a full depth pass
  rendered and thrown away every frame.
- **A page can boot at zero size** (hidden tab, undisplayed pane). `innerWidth`
  is 0, the canvas stays 0x0 and never recovers. Re-check the size from the
  render loop, not only from the `resize` event.
- **`requestAnimationFrame` does not run in a hidden tab.** If a check seems to
  show "nothing is happening", confirm frames are actually being scheduled
  before concluding the logic is broken.

## Style

- Match the surrounding code: no build step, plain ES modules, no framework.
- Comments explain *why*, not what. Skip them for self-evident lines.
- Keep each app self-contained in its own folder — only the files it needs.
