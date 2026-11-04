# Runbook 03: configure Immich

Chapter: `docs/03-configure.md`. Do it before the first upload.

## Needs
- The admin API key file. The Tailscale address if chapter 7 is done. Whether a GPU machine exists.

## Steps
1. Export the current settings and the defaults, keep both:
   `KEY=$(cat ~/.config/immich-tools/admin.key); curl -s -H "x-api-key: $KEY" http://localhost:2283/api/system-config > settings-before.json; curl -s -H "x-api-key: $KEY" http://localhost:2283/api/system-config/defaults > defaults.json`
2. Ask the person to set in the web app, Administration, Settings: storage template on with `{{y}}/{{MM}}/{{dd}}/{{filename}}`; metadata face import on; accepted video codecs h264 and hevc; accepted containers plus mp4; external domain when known. Or do it through the API: read the config, change the fields, `PUT /api/system-config` with the whole object.
3. Set the search model and concurrency with the tool, dry run first:
   `python3 scripts/ml/set_remote_ml.py --api-key-file ~/.config/immich-tools/admin.key --clip-model ViT-B-16-SigLIP2__webli --concurrency faceDetection=4 --concurrency smartSearch=4 --dry-run`
   Without a GPU machine use 1 and 1.
4. Each user: Account Settings, Features: tags on, folders on, ratings as wanted, people from 3 faces. Partner sharing between family members with "show in timeline" off. This is the person's job in the web app; give them the list.
5. Phone app settings as in chapter 3.4. Give the person the list.
6. Export the settings again as `settings-after.json`. Diff them.

## Checks
- `python3 -c "import json;c=json.load(open('settings-after.json'));print(c['storageTemplate']['enabled'],c['metadata']['faces']['import'],c['machineLearning']['clip']['modelName'])'` prints `True True ViT-B-16-SigLIP2__webli`.

## Stop conditions
- Uploads already happened with the storage template off. Turning it on now moves every file. Ask the person before you do.

## Record
The diff of settings-before and settings-after, in words.
