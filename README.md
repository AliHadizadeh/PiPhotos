# PiPhotos

A practical, agent-friendly guide to moving your Apple Photos library to [Immich](https://immich.app/) and running your own photo server on a Raspberry Pi 5.

I built PiPhotos to move my 2+ TB library out of Apple Photos without losing the things that matter: albums, folders, keywords, named faces, favorites, dates and time zones, GPS, Live Photos, edits, RAW pairs, and bursts. The result is a self-hosted photo library for iPhone and Android, with private accounts, optional sharing, and storage limited by your own hardware.

**Follow the steps yourself or let a coding agent help.** The repository includes a handbook, scripts, and agent runbooks developed and tested against a real setup. If you do it yourself, read the chapters in [`docs/`](docs/) in order. If an agent does it, point it at [`AGENTS.md`](AGENTS.md).

**Start here:** [Hardware](docs/01-hardware.md) · [Agent instructions](AGENTS.md)

## What you get

- **Apple Photos migration:** Preserve library structure, metadata, faces, Live Photos, edits, and RAW pairs. The migration tool never writes to the source library.
- **A Pi 5 photo server:** Run Immich with its database on NVMe and photos on a USB disk.
- **Phone backup and private accounts:** Back up from iOS and Android into separate user accounts, with optional partner sharing.
- **Local search and AI:** Face recognition and text search on your own hardware, with optional machine-learning offload to a second computer with a GPU. The Pi takes over when that computer is off.
- **Cleanup tools:** Fix camera clock errors, tag duplicates across users, merge faces, and selectively transcode videos.
- **Remote access:** Connect securely with Tailscale without exposing a port, plus an iPhone shortcut that turns the VPN on only away from home.
- **Verified backups:** Back up weekly to a second disk that is powered only during backups, with checksum verification and email reports.

## Follow the guide

| Step | Chapter | Estimated time |
| --- | --- | --- |
| 1 | [Hardware](docs/01-hardware.md) | 1 h to choose, 1 h to assemble |
| 2 | [Install Immich](docs/02-install.md) | 2 h |
| 3 | [Configure Immich](docs/03-configure.md) | 1 h |
| 4 | [ML offload to a GPU machine](docs/04-ml-offload.md) (optional) | 1 h |
| 5 | [Migrate from Apple Photos](docs/05-migrate-apple-photos.md) | ~1 day/TB, unattended |
| 6 | [Clean up the library](docs/06-cleanup.md) | Depends on the library |
| 7 | [Remote access](docs/07-remote-access.md) | 1 h |
| 8 | [Backup](docs/08-backup.md) | 2 h plus one night |
| 9 | [Recovery](docs/09-recovery.md) | Read before you need it |

More details: [Lessons learned](docs/00-lessons.md) · [Performance measurements](docs/appendix-numbers.md) · [API routes for scripts and agents](docs/appendix-api.md)

## Why I made this

I used Apple Photos on my Mac for years. My library grew to 2+ TB, and at that size Photos was slow and laggy. Three other problems pushed me out.

- **The library was locked to a macOS version.** Once a Mac with a newer macOS opens the library, a Mac with an older macOS can no longer open it. I wanted to switch between machines as my photo server. When Apple stops updates for a Mac, you have to choose: keep that Mac and never open the library on a newer one, or move to the newer one and stop using the older Mac for photos.
- **Shared albums now count against iCloud storage.** Shared albums used to sit outside iCloud storage. So I kept all my photos in shared albums and had them on every device. Shared albums created on a newer macOS count against that storage, so this option is gone. Keeping my photos on my devices, or sharing them with my partner, would now need a more expensive iCloud plan.
- **Phone backup was manual and unreliable.** With a 2+ TB library, iCloud Photos would have been unnecessarily expensive in the long run. So I plugged my iPhone into the Mac and copied the photos onto the external disk that held the library. It was slow, and it often failed on long videos.

Immich addressed those problems for my setup. Another unexpected benefit was being able to use Claude or another coding agent to help organize photos, repair timestamps, and extend the workflow. That became part of the project itself.

## Built with an agent

I developed this setup iteratively with Claude: describe a goal, try an approach, measure and check the result, fix what failed, and document what worked. This is **one tested setup**, not a survey of every possible configuration.

**Tested in November 2026** with Immich v3.3.5, Raspberry Pi OS 64-bit (kernel 6.18), Docker 29 / Compose v5, Tailscale 1.104, tinytuya 1.20, and Python 3.13 on the Pi / 3.14 on the Mac.

## Layout

```
AGENTS.md   instructions for agents: start here
docs/       the chapters, in order, the lessons and the appendices
scripts/    the tools, grouped by task, each with a config file or clear arguments
agent/      one runbook per chapter, and the template for the work record
skills/     a Claude Code skill that loads the runbooks
```

## License and credits

MIT licensed. See [LICENSE](LICENSE). The migration tool adapts one function from [osxphotos](https://github.com/RhetTbull/osxphotos) (MIT). See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for third-party acknowledgments and licenses.
