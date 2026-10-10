# Hackathon integration — work in progress

The repository's `main` contains the baseline import at `75268eafa0faaa7d3e9b589dbcb187bf9ff382c0`. New feature work is staged on `codex/hackathon-integration` for draft review. It is not release-qualified.

| Input | Frozen source checkpoint | Current disposition |
| --- | --- | --- |
| Catch | `960df0336bcdda0a38763a717f1c4308e676e23e` | Imported without product-file conflicts. Builder reports 398 focused checks and 28 native-contract checks passed; complete simulation, destination CI and independent acceptance remain pending. |
| iPhone foundation | `45e042563fdd79821ceaa404be115e9620947b70` | Imported without conflicts; changes are confined to `ios/`. Builder reports core tests and simulator compilation passed. No device installation, simulator app launch or model inference was performed. |
| Mac workflow20 | Pending builder checkpoint | Not yet imported. The builder retains product-file ownership and will provide a clean coherent checkpoint for a later update to this same draft branch. |

The iPhone checkpoint is foundation plumbing, not completion of the twenty workflows: its contract runner recorded all 597 observations as unsupported, with zero effects and no inference. Those observations are not successful workflow outcomes.

Import verification covered Git ancestry, exact source blobs and modes, preservation of the initial hackathon README and license, clean staged merges and whitespace checks. No product tests, model inference or native execution were run by the importer. Source-checkpoint results do not qualify the combined branch. Destination CI and any required independent review and specialist QA must be evaluated against the eventual combined commit before a ready-to-ship claim.

The original Wisp repository's `main` remains unchanged. Paused PR174/full-model-led routing work and private PR160 proposals were not imported into this feature branch.
