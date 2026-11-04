# 2. Install Immich

Time: 2 hours. Result: Immich runs on the Pi, with the photos on the USB disk and the database on the NVMe.

## 2.1 Operating system

1. Flash Raspberry Pi OS Lite (64-bit) to the NVMe with Raspberry Pi Imager. Set the hostname, a user, an SSH key and your time zone in the Imager's settings.
2. Boot the Pi. Log in over SSH.
3. Give the Pi a fixed address. Set a DHCP reservation in your router.
4. Update the system:

```bash
sudo apt update && sudo apt full-upgrade -y && sudo reboot
```

5. Install the tools this handbook uses:

```bash
sudo apt install -y git rsync smartmontools curl jq
```

## 2.2 Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

Log out and in again. Check:

```bash
docker info | grep -E 'Server Version|Operating System'
```

## 2.3 The photo disk

1. Find the disk:

```bash
lsblk -o NAME,SIZE,MODEL,TRAN,FSTYPE,MOUNTPOINT
```

2. Create one GPT partition and an ext4 file system. **This erases the disk. Check the device name twice.**

```bash
sudo wipefs -a /dev/sdX
printf 'label: gpt\nname="immich", type=L\n' | sudo sfdisk /dev/sdX
sudo mkfs.ext4 -L immich -m 0 /dev/sdX1
```

3. Mount it by label, with options that let the Pi boot when the disk is missing:

```bash
sudo mkdir -p /mnt/immich
echo 'LABEL=immich  /mnt/immich  ext4  defaults,noatime,nofail,x-systemd.device-timeout=20  0  2' | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
sudo mount /mnt/immich
```

4. Make Docker wait for the disk. Without this, Docker can start Immich before the disk is mounted, and Immich then writes into the empty mount point on the NVMe.

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
printf '[Unit]\nRequiresMountsFor=/mnt/immich\n' | sudo tee /etc/systemd/system/docker.service.d/immich-mount.conf
sudo systemctl daemon-reload
```

## 2.4 Immich

1. Get the release files:

```bash
sudo mkdir -p /opt/immich && cd /opt/immich
sudo curl -fsSLO https://github.com/immich-app/immich/releases/latest/download/docker-compose.yml
sudo curl -fsSL -o .env https://github.com/immich-app/immich/releases/latest/download/example.env
```

2. Edit `.env`. Set these values:

```
UPLOAD_LOCATION=/mnt/immich/media
DB_DATA_LOCATION=/opt/immich/db
TZ=Your/Timezone
IMMICH_VERSION=v3          # pin a version; read the release notes before you change it
DB_PASSWORD=<random letters and digits, 32 characters>
```

3. Start it:

```bash
cd /opt/immich && sudo docker compose up -d
sudo docker compose ps
```

All four containers must show `healthy` after a minute.

4. Open `http://<pi-address>:2283`. Create the admin account. Create one account per family member.

## 2.5 API keys

Scripts in this handbook talk to Immich with an API key. Create one per user in Account Settings, API Keys. Save each key in a file that only you can read, and never paste it into a chat or a document:

```bash
umask 077
mkdir -p ~/.config/immich-tools
cat > ~/.config/immich-tools/<user>.key
```

Type the key, then press Ctrl-D.

## 2.6 Checks

```bash
curl -s http://localhost:2283/api/server/ping        # {"res":"pong"}
df -h /mnt/immich /opt/immich                         # the media folder is on the USB disk, the database on the NVMe
ls /mnt/immich/media                                  # backups encoded-video library profile thumbs upload
```

## 2.7 Habits

- Upgrade Immich only after you read the release notes. Pin the version in `.env`.
- Keep the `docker-compose.yml` from the release unchanged. Put your values in `.env`.
- Never run `docker compose down -v`. The `-v` deletes the machine-learning model cache.
