# Third-party notices

PiPhotos is licensed under the MIT License (see `LICENSE`). This file lists the third-party work it builds on.

## Code adapted into this repository

### osxphotos

`scripts/migrate/photos_catalog.py`, function `face_region`: the handling of the Apple Photos orientation cases and the scaling of the face size are adapted from the `FaceInfo` class of osxphotos.

- Project: https://github.com/RhetTbull/osxphotos
- License: MIT

```
MIT License

Copyright (c) 2019-2026 Rhet Turnbull

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Software used but not included

The tools in this repository call the following software. None of its code is included here. Each is used under its own license.

| Software | Use | License |
|---|---|---|
| Immich | the photo server; the tools use its HTTP API and read its database schema | AGPL-3.0 |
| tinytuya | Python library that the backup tools import to switch a Tuya smart plug on the LAN; installed into a virtual environment by `scripts/backup/install.sh` | MIT |
| Docker and Docker Compose | run Immich and the machine-learning containers | Apache-2.0 |
| Tailscale | remote access | BSD-3-Clause |
| rsync | the backup copy | GPL-3.0 |
| smartmontools (`smartctl`) | disk health | GPL-2.0 |
| e2fsprogs (`badblocks`, `mkfs.ext4`, `tune2fs`) | disk surface read and file systems | GPL-2.0 |
| udisks2 (`udisksctl`) | safe detach of the backup disk | GPL-2.0 or later |
| ExifTool, ffmpeg | run inside the Immich container for metadata and video probing | Artistic/GPL, LGPL/GPL |
| PostgreSQL | Immich's database, queried read-only through `psql` | PostgreSQL License |

## Standards and documentation followed

- The XMP sidecars use the Metadata Working Group regions schema (`mwg-rs`), the digiKam `TagsList` namespace, and the XMP, EXIF and Dublin Core namespaces.
- The Tuya cloud request signing in `scripts/backup/tuya_cloud_key.py` follows Tuya's public OpenAPI documentation.
- The writing style follows the principles of ASD-STE100 Simplified Technical English. No text from the standard or from any guide to it is reproduced.
