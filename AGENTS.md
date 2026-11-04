# AGENTS.md

Instructions for an agent (Claude Code or similar) that sets up or operates an Immich server on a Raspberry Pi for a person, with this handbook.

## Start here

1. Read the chapter in `docs/` for the task. Then open the matching runbook in `agent/runbooks/`. The runbook has the commands, the checks and the stop conditions.
2. Collect the site values before the first command: the Pi's address and user, the disks by `/dev/disk/by-id/`, the Immich address, the users, where the API keys are. Write them down in your working notes. Never guess a device name.
3. Work in small steps. After each step run the check the runbook gives. Do not continue on a failed check.
4. Keep a record. Append what you did, with timestamps and numbers, to `RECORD.md` in the person's project folder, with the headings of `agent/RECORD-template.md`. The person reads it later. Future agents read it too.

## Hard rules

These come from mistakes that cost data or days. Do not bend them.

1. **The source photo library is read-only.** Never open it in Photos.app. Mount its disk read-only. Never write to it, not even a sidecar.
2. **Confirm every destructive step with the person, in their words, right before you run it.** Formatting a disk, deleting assets, emptying a queue, deleting reports, rewriting dates for thousands of assets. A plan approved earlier does not cover the command now.
3. **Check the device name twice before any disk command.** Resolve it from `/dev/disk/by-id/`. Refuse if it resolves to the disk behind `/mnt/immich`.
4. **Never cut the power to a mounted disk.** Unmount, then `udisksctl power-off`, then confirm the device node is gone, then the plug.
5. **Secrets stay in files with mode 600.** API keys, passwords, SMTP credentials, the plug's local key. Never print them, never put them in a chat message, a log, a commit or a document. If the person pastes one into the chat, store it and say that it should be rotated later.
6. **Verify by checksum.** A file count is not a verification. Immich stores a SHA-1 for every original. Use it.
7. **Never press "Missing" or "All" on a job page while a queue has a backlog.** It adds the whole library again. Never "Missing" or "All" on Video Conversion at all.
8. **Never "Delete reports" on stale integrity rows.** It can trash the assets behind missing-file reports.
9. **Never "Regenerate people"** on a shared person group.
10. **Long jobs run detached**, with `nohup setsid`, with a log on the NVMe, resumable. An SSH session dies. Your session ends.
11. **Never overwrite a running shell script in place.** Bash reads a script while it runs. Write a new file and rename it over the old one.
12. **Never use `pkill -f` with a pattern that appears elsewhere in the same command.** It kills your own shell. Use `[s]pattern` bracket tricks and keep the kill and the restart in separate commands.
13. **A plan approved by the person is not the same as results.** Report what happened, with the numbers from the check, including what failed or was skipped.

## How to work on the Pi

- Use `ssh <pi>` with a key. Run scripts through `ssh <pi> bash -s < script.sh`, never by pasting long quoted commands. Inside such a script never use `docker exec -i`: it eats the rest of the script from stdin.
- `sudo` without a password is assumed. Tools in `/usr/sbin` are not in the PATH of a non-login shell: use `sudo /usr/sbin/smartctl`, or `export PATH=$PATH:/usr/sbin`.
- The journal on Raspberry Pi OS is volatile. Anything you need after a reboot must be in a file.
- The Immich API is at `http://localhost:2283/api` on the Pi. The OpenAPI spec of the running version is served by the server; routes change between major versions. Check the route before you use it.
- Read-only database queries go through `docker exec immich_postgres psql -U postgres -d immich -At -c "..."`. Never write to the database. Every change goes through the API.

## Facts about Immich 3.x that are not in its documentation

The routes, bodies and tables the tools use are in `docs/appendix-api.md`. Measured rates are in `docs/appendix-numbers.md`.

- Face import from XMP sidecars needs the "face import" metadata setting. The imported regions become named people. Immich's own detection then creates unnamed duplicates unless you reconcile them (chapter 6).
- A tag change rewrites the asset's XMP sidecar and re-reads the metadata. Originals are untouched.
- Setting `dateTimeOriginal` through the API rewrites the sidecar, re-reads the metadata and moves the file to the new date folder. Nothing else to do.
- Jobs chain only after an upload's thumbnail job. Re-queued jobs do not chain.
- The "required" transcode policy also transcodes 10-bit video.
- A merge of two named persons of different users is skipped silently unless it runs with the key of the user whose person is merged away.
- The job queue lives in Valkey without a volume. A restart of the stack discards queued jobs.
- The test-email route in 3.3 is `POST /api/admin/notifications/test-email` and needs `transport.secure`.

## When to stop and ask

- Any destructive step (rule 2).
- A check fails twice.
- A choice the person has not made: which disk, which users, retention, schedule, email provider.
- The person's data looks different from what they described: more libraries, hidden folders with unique content, a trash with hundreds of gigabytes.

## Reporting

Lead with the result. Give the numbers from the checks. Name what is not done and what is not verified. Keep code out of prose. One idea per sentence.
