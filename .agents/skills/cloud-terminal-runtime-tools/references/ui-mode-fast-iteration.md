# UI Mode fast iteration workflow

Use this reference for UI Mode/live-preview requests where the user selects or describes UI elements and expects quick source iteration beside the chat.

## Goal

Optimize for the shortest correct loop:

1. identify the actual project source workspace,
2. make a targeted source edit,
3. let hot reload update the preview when possible,
4. verify cheaply,
5. rebuild/restart only after evidence shows hot reload cannot apply the change.

## Fast path

1. Treat UI Mode context as authoritative starting context:
   - project label/id,
   - resolved project source workspace (`ui_project_workspace` when present),
   - current page/path/title,
   - selected/highlighted element descriptors.
2. Start from the source workspace, not task metadata folders or generated runtime directories.
3. Use selected/page text, selectors, labels, and route names for targeted searches in source files.
4. Edit the source component/style directly.
5. Verify with the cheapest reliable check first:
   - source grep for removed/changed copy,
   - type/syntax check for edited files,
   - focused unit/source test if one exists,
   - DOM/browser check only when visual structure or runtime behavior is the actual requirement.
6. Let the live preview/hot reload update naturally. Do not rebuild or restart unless the quick verification shows the running preview is serving immutable built output or did not pick up the source edit.

## Rebuild/restart decision ladder

Before running a production/client build or restarting Play, gather evidence:

- Is the running process a dev server with hot reload? Prefer waiting/reloading the preview.
- Is the served route referencing hashed built chunks or static output? A rebuild may be needed.
- Is there an existing project command/config that distinguishes dev vs build? Use that rather than guessing package scripts.
- Can a route/chunk/DOM check prove the edit is already served? If yes, stop; do not rebuild.

If a build is required:

- run the narrow project build needed to refresh the served preview assets,
- inspect generated-source diffs and revert incidental generated source changes unrelated to the request,
- verify the served route/chunk or DOM reflects the requested source change.

## Pitfalls to avoid

- Do not begin by searching `project_tasks/`, session metadata, generated run journals, or built output when UI Mode provides a source workspace.
- Do not make broad repository scans before using selected element/page context for targeted searches.
- Do not treat generated bundle edits as the durable fix. Edit source; generated output is only a serving artifact when the preview requires it.
- Do not run production builds for routine UI text/layout edits unless there is evidence hot reload/dev serving is unavailable.
- Do not spend a long browser-automation loop proving simple copy removal when source and focused checks already prove it; reserve DOM checks for layout, interaction, or served-preview uncertainty.

## Reporting

When reporting back, state the path taken in one or two lines:

- source workspace used,
- whether hot reload was expected or a rebuild was evidence-required,
- exact verification result.
