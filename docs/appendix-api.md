# Appendix: Immich API routes and tables the tools use

For agents and for anyone who extends the tools. Immich 3.3. Routes move between major versions: the running server publishes its own OpenAPI document, and the server log lists every mapped route at start-up (`docker logs immich_server | grep Mapped`). Check there before you trust this page on another version.

All calls carry the header `x-api-key: <key>` and `Content-Type: application/json`. Keys belong to one user. Writes to another user's assets or people need that user's key.

## Server and user

| Call | Notes |
|---|---|
| `GET /api/server/ping` | `{"res":"pong"}` |
| `GET /api/server/version` | pin tools to the major version |
| `GET /api/server/media-types` | which extensions upload; no audio formats |
| `GET /api/users/me` | the key's user, with `id` |
| `GET /api/admin/users` | admin key; every user with `clusterGroupId` |

## Assets

| Call | Notes |
|---|---|
| `POST /api/assets` | multipart: `assetData`, `deviceAssetId`, `deviceId`, `fileCreatedAt`, `fileModifiedAt`, optional `isFavorite`, `visibility`, `livePhotoVideoId`, `duration`, `sidecarData`. Header `x-immich-checksum` with the SHA-1 lets the server skip a file it has. Reply `{"id","status":"created"|"duplicate"}`. A 0-byte file is refused. |
| `POST /api/assets/bulk-upload-check` | `{"assets":[{"id":"any","checksum":"<sha1 hex>"}]}`; 500 per call worked |
| `GET /api/assets/{id}` | `exifInfo`, `localDateTime`, `livePhotoVideoId`, `stack`, `people`, `tags`, `checksum` (base64) |
| `PUT /api/assets/{id}` | `dateTimeOriginal` as ISO with offset: Immich stores the zone, rewrites the XMP sidecar, re-reads the metadata and moves the file into the new date folder. Also `isFavorite`, `visibility`, `description`. |
| `DELETE /api/assets` | `{"ids":[...],"force":false}` moves to the trash, 30 days |
| `POST /api/assets/jobs` | `{"assetIds":[...],"name":"refresh-metadata"|"transcode-video"|"regenerate-thumbnail"|...}` per-asset jobs; 200 to 500 ids per call |
| `POST /api/search/metadata` | `{"page","size","withExif":true,"model","takenAfter","takenBefore",...}`; reply `assets.items` and `assets.nextPage` |

## Albums, stacks, tags

| Call | Notes |
|---|---|
| `GET /api/albums`, `POST /api/albums` | `{"albumName","assetIds"}` |
| `PUT /api/albums/{id}/assets` | `{"ids":[...]}`, 500 per call |
| `POST /api/stacks` | `{"assetIds":[...]}`, first id on top |
| `PUT /api/tags` | `{"tags":["Parent/Leaf"]}` upserts a hierarchy; the reply may omit part of it, so follow with `GET /api/tags` |
| `PUT` and `DELETE /api/tags/{id}/assets` | `{"ids":[...]}`, 500 per call. Every tag change rewrites the asset's sidecar. |

## People

| Call | Notes |
|---|---|
| `GET /api/people?size=1000&page=N&withHidden=true` | `people`, `total`, `hidden`; the UI hides people under the "minimum faces" preference |
| `PUT /api/people/{id}` | `{"name":"..."}` |
| `POST /api/people/{id}/merge` | `{"ids":[...]}` merges others into `{id}`; 50 per call |
| `POST /api/people/merge` | `{"ids":[host, guest]}` links a person across users; must run with the key of the user whose person is merged away, or it is skipped silently |
| `PUT /api/people/users` | `{"personIds","sharedWithIds","role":"write"}` shares people with another user |
| `PUT /api/cluster-groups/{id}/requests`, `GET /api/cluster-groups/requests`, `POST /api/cluster-groups/requests/{id}/accept`, `GET /api/cluster-groups/{id}/users` | one person set for several users |

## Jobs and settings

| Call | Notes |
|---|---|
| `GET /api/jobs` | per queue: `jobCounts` (active, waiting, delayed, failed, paused) and `queueStatus` (isActive, isPaused). Counts restart at zero when the stack restarts: the queue is not persistent. |
| `PUT /api/jobs/{queue}` | `{"command":"start"|"pause"|"resume"|"empty","force":false}`. `start` with `force:false` is the "missing" mode. While a queue is active the server answers 400 "Job is already running": retry every 10 s. |
| `PUT /api/jobs/backupDatabase` | `{"command":"start","force":false}` makes a database dump; watch `media/backups/` for the new file |
| `GET /api/system-config`, `PUT /api/system-config` | read and write the whole object; `GET /api/system-config/defaults` for the defaults |
| `POST /api/admin/notifications/test-email` | 3.3: body is the `smtp` object and `transport.secure` is required; sends to the caller's address |

## Database tables, read-only through `psql`

`docker exec immich_postgres psql -U postgres -d immich -At -F $'\t' -c "..."` (no `-i` inside a script that reads stdin).

| Table | Columns the tools use |
|---|---|
| `asset` | `id`, `ownerId`, `originalPath` (`/data/...`), `originalFileName`, `checksum` (SHA-1, `encode(checksum,'hex')`), `type`, `visibility` (`timeline`, `archive`, `hidden` for Live clips), `deletedAt`, `localDateTime`, `createdAt`, `duration` in ms, `stackId`, `livePhotoVideoId`. There is no queryable `deviceId`. |
| `asset_exif` | `dateTimeOriginal`, `timeZone`, `fileSizeInByte`, `exifImageWidth`, `exifImageHeight`, `make`, `model`, `description` |
| `asset_file` | `type` in `thumbnail`, `preview`, `fullsize`, `sidecar`, `encoded_video`; `path`; `isEdited` |
| `asset_face` | `assetId`, `personGroupId`, `sourceType` (`exif` for imported regions, else machine learning), `imageWidth`, `imageHeight`, bounding box columns, `deletedAt` |
| `person` | `personGroupId`, `ownerId`, `name`, `thumbnailPath`; one row per user per linked person |
| `face_search`, `smart_search` | embeddings; cosine distance with `<=>`; 0.01 is Immich's own duplicate threshold |
| `tag`, `tag_asset`, `album`, `album_asset`, `user` | as named |

## Traps we hit

- "Missing" on a job page while a backlog is queued doubles the queue.
- Re-queued jobs do not chain into the next stage.
- A restart of the stack discards the queue.
- "Delete reports" on stale integrity rows can trash assets.
- The untracked-file scan lists the disk when queued and compares later: moved files show as untracked.
- `docker exec -i` inside a `bash -s` script eats the rest of the script.
