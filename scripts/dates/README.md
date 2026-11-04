# Date tools

- `calibrate_offset.py` finds a camera's clock error from a trip that a second camera also photographed.
- `shift_dates.py` shifts the capture date of assets by N days, or applies a plan file, through the Immich API. Immich rewrites the sidecar, re-reads the metadata and moves the file into the new date folder. Dry run first. The log makes a run resumable. `--verify` reads the result back.

See [chapter 6](../../docs/06-cleanup.md), sections 6.5 and 6.6.
