---
name: piphotos
description: Set up, migrate to, operate and back up a self-hosted Immich photo server on a Raspberry Pi 5, from Apple Photos, with machine learning on a GPU machine, Tailscale remote access and a plug-controlled backup disk. Use when the user asks for any of these, names Immich on a Pi, or asks to migrate an Apple Photos library.
---

# PiPhotos

This skill is the agent entry point of the PiPhotos handbook in this repository.

## Procedure

1. Read `AGENTS.md` at the repository root. Its hard rules apply to every step.
2. Find the task in this table and open the runbook. Read the matching chapter in `docs/` when the runbook refers to it.

| Task | Runbook |
|---|---|
| choose or check hardware | `agent/runbooks/01-hardware.md` |
| install the OS, Docker and Immich | `agent/runbooks/02-install.md` |
| apply the settings | `agent/runbooks/03-configure.md` |
| machine learning on a GPU machine | `agent/runbooks/04-ml-offload.md` |
| migrate an Apple Photos library | `agent/runbooks/05-migrate-apple-photos.md` |
| faces, names, duplicates, dates, videos | `agent/runbooks/06-cleanup.md` |
| Tailscale and the phone shortcut | `agent/runbooks/07-remote-access.md` |
| backup disk, plug, weekly job, email | `agent/runbooks/08-backup.md` |
| a disk died, a file is corrupt | `agent/runbooks/09-recovery.md` |

3. Collect the site values the runbook lists under "Needs" before the first command. Ask the person for the ones you cannot read from the machine.
4. Run the steps in order. Run every check. Stop on a failed check or a stop condition and report.
5. Append what you did to `RECORD.md` in the person's project folder.

## Tools in this repository

- `scripts/migrate/`: the Apple Photos migration tool.
- `scripts/post/`: machine-learning stages, face reconciliation, names, duplicates, videos.
- `scripts/dates/`: camera clock calibration and date shifts.
- `scripts/ml/`: compose file for the GPU machine, settings tool, benchmark.
- `scripts/backup/`: the backup disk, the plug, the weekly job, email.
- `scripts/checks/`: disk health and standby test.
- `docs/appendix-api.md`: the Immich routes and tables the tools use. `docs/appendix-numbers.md`: measured rates for planning. `agent/RECORD-template.md`: the record format.

Every tool is a dry run unless `--apply` is given, or it asks for confirmation before it erases anything.
