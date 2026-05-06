# Branch task run complete

## Result

No actionable tasks remain in `project_tasks/master.json`.

I processed these branch tasks and marked each `qaStatus` as `ready-for-test`:

- `39b6f4be-8856-420a-a13a-44823a3504a0` — added a project-detail `Back to ops dashboard` control in the fork-owned `ops-projects` page.
- `7d15e668-ebc7-4322-b187-6938e1c20a3b` — stopped the 5-second home auto-refresh from collapsing the quick-task project picker while it is focused.
- `0fa534cd-7465-4c7c-932b-3e2ea289c0cb` — removed the forced switch to the archived task view after archiving completed tasks.
- `dd8e0298-2ed9-493d-ba49-8c88eb913b2a` — hid the run-activity panel while the projects/epics view is open.
- `6651fc7f-3cd4-49cc-90e6-4c5a5c450391` — added `Execute ready tasks with AI` to the project/epics page, including actionable-task counting, batch-prompt generation, AI automation task creation, and direct launch of the created task session.

## Verification

- `pytest -q tests/test_upstream_restart_phase8_project_defaults.py -k "ops_ui"`
- `pytest -q tests/test_upstream_restart_phase11_activity.py -k "quick_task_project_picker or home_matches_cloud_terminal_menu_layout"`
- `pytest -q tests/test_upstream_restart_phase11_activity.py -k "archive_completed_keeps_current_task_view or quick_task_project_picker"`
- `pytest -q tests/test_upstream_restart_phase8_project_defaults.py -k "project_detail_can_return_to_dashboard or hides_run_activity_inside_projects_view"`
- `pytest -q tests/test_upstream_restart_phase8_project_defaults.py -k "execute_ready_tasks_creates_automation_session or hides_run_activity_inside_projects_view or project_detail_can_return_to_dashboard"`
- `node --check static/ops-projects.js`
- `node --check static/ops-legacy-home.js`
- `node --check static/ops-legacy-dashboard-actions.js`

## Note

The new project-page execute-ready-tasks flow matches the Cloud Terminal prompt construction and launches the created automation session immediately. The older legacy dashboard has an extra in-dashboard auto-send hook; this fork-owned page does not expose that same chat bridge.
