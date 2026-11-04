# Runbook 02: install Immich

Chapter: `docs/02-install.md`.

## Needs
- Pi with Raspberry Pi OS Lite 64-bit on the NVMe, SSH, sudo.
- The photo disk's by-id name. The person's time zone. A fixed address for the Pi.

## Steps
1. Update and install tools:
   `sudo apt update && sudo apt full-upgrade -y && sudo apt install -y git rsync smartmontools curl jq`
2. Install Docker: `curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker "$USER"`. Reconnect. Check `docker info | grep 'Server Version'`.
3. Format the photo disk. **Destructive. Confirm the device with the person first.** Resolve it: `readlink -e /dev/disk/by-id/<name>`. Then:
   `sudo wipefs -a /dev/sdX && printf 'label: gpt\nname="immich", type=L\n' | sudo sfdisk /dev/sdX && sudo mkfs.ext4 -L immich -m 0 /dev/sdX1`
4. Mount by label with `nofail`:
   `sudo mkdir -p /mnt/immich && echo 'LABEL=immich /mnt/immich ext4 defaults,noatime,nofail,x-systemd.device-timeout=20 0 2' | sudo tee -a /etc/fstab && sudo systemctl daemon-reload && sudo mount /mnt/immich`
5. Make Docker wait for the mount:
   `sudo mkdir -p /etc/systemd/system/docker.service.d && printf '[Unit]\nRequiresMountsFor=/mnt/immich\n' | sudo tee /etc/systemd/system/docker.service.d/immich-mount.conf && sudo systemctl daemon-reload`
6. Fetch the Immich release files into `/opt/immich` and write `.env` with `UPLOAD_LOCATION=/mnt/immich/media`, `DB_DATA_LOCATION=/opt/immich/db`, `TZ`, a pinned `IMMICH_VERSION`, a random `DB_PASSWORD`. Generate the password with `tr -dc A-Za-z0-9 </dev/urandom | head -c 32`. Do not print it.
7. `cd /opt/immich && sudo docker compose up -d`. Wait a minute. `sudo docker compose ps` must show four healthy containers.
8. Ask the person to create the admin account and the users in the web app. Ask them to create one API key per user and to store each in `~/.config/immich-tools/<user>.key` with mode 600 on the Pi. Do not ask them to paste keys into the chat.

## Checks
- `curl -s http://localhost:2283/api/server/ping` returns `{"res":"pong"}`.
- `findmnt /mnt/immich` shows the photo disk. `ls /mnt/immich/media` shows Immich's folders.
- `df -h /opt/immich` is on the NVMe.

## Stop conditions
- The device for step 3 resolves to the NVMe or to a disk with data the person did not say to erase.
- Containers not healthy after five minutes: read `sudo docker compose logs --tail 50`, report.

## Record
Immich version, disk label and UUID (`blkid`), mount options, the fact that the compose file is the release file unchanged.
