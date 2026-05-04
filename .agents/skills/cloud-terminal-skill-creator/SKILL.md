---
name: cloud-terminal-skill-creator
description: Use this skill when creating or updating a shared Cloud Terminal skill. Put the skill in the Cloud Terminal project's `.agents/skills/<skill-name>/` source so it is copied into project sessions like the ct-runtime-related skills, add `SKILL.md` and `agents/openai.yaml`, and keep the metadata aligned with the skill body.
---

# Cloud Terminal Skill Creator

Use this skill when the user wants a skill that should work like the built-in Cloud Terminal shared skills.

If the goal is a shared Cloud Terminal skill, the source of truth is this repository's `.agents/skills/<skill-name>/` folder. Do not only add it to another project's `.agents/skills` folder, and do not only add it to `~/.codex/skills`, because that will not make it behave like the ct-runtime-related shared skills.

## Workflow

1. Confirm the scope:
   - Use a shared Cloud Terminal skill when the user wants the skill to be available across project sessions through Cloud Terminal's shared-skill sync.
   - Use `~/.codex/skills` only when the user explicitly wants a host-level personal skill instead.
2. For a shared Cloud Terminal skill, create or update:
   - `.agents/skills/<skill-name>/SKILL.md`
   - `.agents/skills/<skill-name>/agents/openai.yaml`
3. Write concise `SKILL.md` frontmatter:
   - `name`
   - `description`
4. Keep the `SKILL.md` body focused on the exact workflow the agent should follow. Do not add extra docs like `README.md`, `CHANGELOG.md`, or setup notes unless the user explicitly asks for them.
5. Add or update `agents/openai.yaml` so it matches the skill:
   - `display_name`
   - `short_description`
   - `default_prompt`
6. Make the metadata and body agree. If the skill says it handles shared Cloud Terminal behavior, the prompt and description should say the same thing.
7. If you add a new shared skill, update coverage that lists shared skills so regressions are visible.
8. Tell the user about rollout:
   - The skill is immediately present in this working tree.
   - Other project sessions only see it after the Cloud Terminal runtime is updated from this repo and the target project session is created or resynced so shared-skill sync runs.

## Content Guidance

- Prefer names that match the existing shared skill style, usually with a `cloud-terminal-` prefix.
- Keep metadata specific enough that the skill triggers for the right tasks.
- Keep the body short and procedural. Put only the rules the agent actually needs in the skill.
- Mirror the existing shared skill layout instead of inventing a new structure.
- If you need generic skill-writing guidance, read `~/.codex/skills/.system/skill-creator/SKILL.md`.

## Example Shape

```text
.agents/skills/cloud-terminal-example-skill/
├── SKILL.md
└── agents/
    └── openai.yaml
```
