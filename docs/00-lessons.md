# Lessons we learned the hard way

Six rules. Each one cost us data, days, or both. Read them before chapter 1.

1. **Never open the source Photos library in Photos.app during the migration.** Mount its disk read-only. Photos rewrites its database when it opens, and the migration reads that database.
2. **Verify by checksum, not by file count.** Immich stores a SHA-1 for every original. A count hides a truncated file.
3. **Keep the database on the NVMe. Keep the photos on the big disk. Keep the database dumps on both.** The database holds albums, people, tags and stacks. They exist nowhere else.
4. **Do not press "Missing" or "All" on a job page while a backlog is queued.** It adds the whole library again. On Video Conversion, never press them at all.
5. **Decide the search model before the first machine-learning pass.** A change later means a full re-run over every photo.
6. **A backup that nobody checks is not a backup.** Verify it against the checksums, and get an email when it fails.

Where each rule comes from: 1 and 2 in [chapter 5](05-migrate-apple-photos.md), 3 in [chapter 2](02-install.md), 4 and 5 in [chapter 3](03-configure.md), 6 in [chapter 8](08-backup.md).
