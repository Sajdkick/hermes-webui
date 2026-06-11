# UI Mode selected-element removal workflow

Use this when the user says to remove highlighted/selected UI elements from a Cloud Terminal UI Mode live preview.

## Durable pattern

1. Treat the UI Mode payload as the source of the requested scope: selected text, selectors, route, project id, and current path identify what should disappear.
2. Locate the component(s) that render those selected strings. If source strings are not exact matches because typography transforms casing, search by nearby phrases, component names, routes, and page files.
3. Remove only the selected presentation elements/copy. Preserve underlying inputs, buttons, actions, and app state unless they were explicitly selected.
4. When removing optional page/section headers, ensure the shared layout can render without empty header wrappers. Add optional-title/header guards in the reusable layout rather than leaving blank spacing.
5. For selected text/link/alert removal, verify with a DOM-level check against the actual route:
   - assert removed strings/roles/links are absent,
   - assert core remaining controls are still present,
   - include route-specific authentication/debug-login only as needed.
6. In UI Mode live preview, do not assume hot reload. If Play serves built assets, run the client build, revert only incidental generated source diffs, and verify the served route or chunk.

## Pitfalls

- MUI often uppercases button/overline text; DOM assertions should be case-insensitive for labels while still checking exact roles/links where useful.
- Selected elements can span parent containers and child text nodes. Removing both is only appropriate when the user selected both; otherwise keep parent controls intact.
- A successful source grep is not enough for UI Mode tasks. Prefer a browser DOM check on the live preview route before reporting completion.
