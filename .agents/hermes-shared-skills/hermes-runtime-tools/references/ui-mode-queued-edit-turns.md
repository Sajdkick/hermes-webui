# UI Mode queued edit turns

Session-derived notes from designing fast queued UI edits in Hermes WebUI UI Mode.

## Problem shape

UI Mode supports a live preview iframe beside a normal WebUI chat iframe. The preview can highlight/select one or more DOM elements and sends current UI context to the chat iframe. The normal chat UI already has a per-session queue for messages sent while a response is active.

The dangerous mismatch is that UI Mode context is live/global in the chat iframe. If a queued turn stores only user text, then when it drains later it may append whatever elements are highlighted at drain time, not the elements highlighted when the user clicked Send.

## Invariant

A queued UI edit must be a prepared turn with a frozen UI Mode snapshot captured at enqueue time.

Do not recapture UI Mode context when draining the queue.

## Preferred architecture

- Keep the backend one-active-run-per-session guard. Parallel UI-edit agents in the same session risk duplicate clarify/tool state and source-edit races.
- Reuse the existing chat-session queue rather than creating a second queue in the UI Mode parent shell. The embedded chat owns session id, model/profile state, attachments, busy state, stream lifecycle, and queue drain.
- Split chat sending conceptually into:
  1. `buildOutgoingTurnFromComposer()` / prepare turn;
  2. `queuePreparedTurn(turn)`;
  3. `sendPreparedTurn(turn)`.
- Queue drain should pop a prepared turn and pass it directly to `sendPreparedTurn(turn)`, not write text back into the textarea and call a path that re-reads live UI Mode globals.

## Queue entry shape

Extend existing queue payloads with a nested UI Mode snapshot while preserving backward compatibility for plain text queue items:

```js
{
  text: 'Make this button red',
  files: [],
  model: '...',
  model_provider: '...',
  profile: '...',
  _queued_at: Date.now(),
  session_mode: 'ui_mode',
  ui_mode: {
    context_text: '[UI Mode context]\n...',
    metadata: {
      projectId: '...',
      projectLabel: '...',
      projectWorkspace: '...',
      previewPath: '/settings',
      previewUrl: '...',
      previewTitle: 'Settings'
    },
    page: {},
    selections: [],
    summary: '1 element · /settings · button “Save”',
    captured_at: Date.now()
  }
}
```

Keep `text` as the visible user instruction. Do not insert raw `[UI Mode context]` into queue row text or the textarea editor.

## UX rules

- While busy in UI Mode, the primary send action may display as Queue, but clicking it should clear the composer immediately and let the user highlight another set of elements.
- Queue rows should show compact metadata such as `UI · 3 elements · /pricing`, not the full hidden context blob.
- Inline editing a queued row changes only the visible instruction text; it must preserve the frozen UI snapshot unless the user explicitly chooses a `Refresh context from current selection` action.
- Be cautious with `Combine queued messages`: if items have different UI snapshots, disable combine or warn rather than merging text and losing per-edit context.
- Consider clearing preview highlights after enqueue, but only after the snapshot is captured. This supports the intended rhythm: highlight → send → highlight next → send.

## Hotspots in current WebUI structure

- `static/ui-mode.js`: owns preview/page/selection state and posts `hermes-ui-mode-context-update` to the chat iframe.
- `static/ui-proxy-compat.js`: maintains multi-selection and element descriptors with selectors/text/bounds.
- `static/messages.js`: stores live `_uiModeContextText`, appends UI Mode context to outgoing text, and handles busy/409 requeue cases.
- `static/ui.js`: owns `SESSION_QUEUES`, `queueSessionMessage`, `shiftQueuedSessionMessage`, queue rendering, and stream-finish drain behavior.
- `api/routes.py`: `_start_chat_stream_for_session()` rejects same-session concurrent runs with `session already has an active stream` / HTTP 409. Keep this guard.

## Verification cases

- Busy UI Mode send queues a turn with selection A, selection changes to B, and drained request still contains A.
- Idle UI Mode send uses the current snapshot exactly once.
- 409 conflict requeues the already-prepared turn without double-appending UI context.
- Queue row edit/reorder/delete preserves the `ui_mode` payload.
- SessionStorage round-trip preserves the UI snapshot.
- Mixed UI-snapshot queue items do not silently combine into a lossy single text-only message.
- Optional clear-selection behavior clears highlights after enqueue, not before snapshot capture.
