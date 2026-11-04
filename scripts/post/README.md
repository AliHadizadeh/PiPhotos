# Post-processing and cleanup tools

Read [chapter 6](../../docs/06-cleanup.md) first. Copy `owners.example.json` to `owners.json` and fill in your users. Every tool is a dry run unless you pass `--apply`.

| File | Does |
|---|---|
| `common.py` | owners file, database queries through the Postgres container, API calls |
| `post_stages.sh` | the machine-learning stages after a migration, in the right order |
| `reconcile_faces.py` | merges Immich's unnamed face clusters into the named people imported from Photos |
| `propose_names.py` | proposes names for unnamed clusters from the other user's named people |
| `link_people.py` | one cluster group for two users, people shared both ways, same person linked across the libraries |
| `cross_dup_tags.py` | tags duplicates across two users: identical file, same shot, looks identical |
| `probe_videos.py` | ffprobe census of every unconverted video, classed as transcode, remux or fine |
| `queue_transcodes.py` | queues transcode jobs only for the transcode and remux classes |
| `embed_edited.sh` | computes a missing search embedding for an asset with an edited preview (version-specific bug) |
| `migration_monitor.sh` | one-screen status of running migrations, Docker, job queues and the Pi |

Database queries are read-only. Every change goes through the Immich API with the owner's key.
