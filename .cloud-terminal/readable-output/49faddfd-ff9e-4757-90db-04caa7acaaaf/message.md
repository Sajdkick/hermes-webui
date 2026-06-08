# Restart required

Yes, but only Hermes.

## What to restart

- Use the normal **Restart Hermes** button once.
- You do **not** need to restart the whole Cloud Terminal service for the Hermes-side fix.

## Why

- The fix was in Hermes Python code, so the running Hermes process needs one restart to load it.
- The broader Cloud Terminal proxy can stay up; your immediate update error should be fixed after the Hermes restart.

## Extra note

- I also prepared a separate Cloud Terminal proxy-side hardening patch outside this repo. That one would require a Cloud Terminal service restart to become active, but it is not required for the current Hermes fix.
