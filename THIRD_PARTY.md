# Source provenance

This is an independent source snapshot maintained in `sksdiw3/hint-ladder-verl`.
It is not a GitHub fork and does not carry the upstream Git history.

## Framework baseline

- Source: https://github.com/liujunzhuo/SMRC-SD
- Baseline commit: `1a0996ba133527b70beb47d01df3899175893a90`
- Included: `verl/`, `agent_system/`, package metadata and dependency files.
- The baseline itself incorporates verl and verl-agent. Original copyright
  headers, the root Apache-2.0 license and `Notice.txt` are retained.
- The bundled WebShop license remains at
  `agent_system/environments/env_package/webshop/webshop/LICENSE.md`.
  Other bundled third-party source retains the notices present in the baseline.

## Hint Ladder additions

The local working tree adds `hintladder/`, experiment configurations, tests,
fixed game lists, documentation, `verl/trainer/main_hint_ladder.py`, and
`verl/trainer/ppo/hint_ladder_ray_trainer.py`.
The existing `verl/trainer/config/ppo_trainer.yaml` gains the
`algorithm.hint_ladder` group. The `env_manager.py` change passes and validates
the per-worker `gamefile` natural key. The remaining included framework source
is copied from the baseline.

The research design also references OPD (https://github.com/dwy57c/OPD) and the
local OPD-hinter project for ladder and audit contracts. These are provenance
references; this repository is a separate project under the owner's account.
The original design is preserved in `docs/hintladder/design.md` with the later
decision to defer Hinter reward and GRPO called out in the current README.

## Export boundaries

This export omits the original Git history, CI workflows, historical papers,
example launchers, runtime environments, private credentials and endpoints,
datasets downloaded during experiments, generated banks, run logs, model
weights and checkpoints. Fixed game lists and a four-game smoke level map are
included as small experiment inputs.

Vendored PNG/JPEG/PDF/font assets, notebooks, shell scripts and WebShop's bundled
`chromedriver` binary are omitted. Small ALFWorld layout and grammar resources
remain because they are part of the upstream environment implementation.
Other environment sources are retained for context; their optional assets and
dependencies must be obtained separately. Hint Ladder support is currently
limited to ALFWorld.

Export-only changes rename the package metadata, replace the private hint
endpoint with an example address, remove a credential-shaped example from a
vendored WebShop installation document, move the fixed smoke level map under
`configs/smoke/`, and provide repository-specific documentation and ignores.
No credentials or experiment artifacts are included in this history.
