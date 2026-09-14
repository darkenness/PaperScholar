# Provider and pipeline maintenance acceptance gates

This maintenance branch preserves the existing default Planner and Stylist prompts. New layout exploration is opt-in and retains an unmodified baseline candidate. Original image bytes and every successful iteration must remain available even when review, editing, cancellation, or a later candidate fails.

Required checks before release:

- Install the locked backend dependencies and validate the actual Google GenAI SDK surface.
- Exercise OpenAI-compatible Chat Completions and Images generation/edit protocols with HTTP-level mocks, including invalid responses and upstream errors.
- Test cancellation, zero critic rounds, partial candidate failures, event replay, and saved artifacts against real database/session behavior.
- Type-check and build the frontend; exercise provider configuration and model selection persistence in browser tests.
- Do not claim measured visual improvement from mock tests. A paired live-image comparison requires model credentials and manual inspection. Preserve the default baseline and expose both original and revised versions until this gate is completed.

No production API key or environment file may be committed or printed in CI logs. CI must not call paid image models.
