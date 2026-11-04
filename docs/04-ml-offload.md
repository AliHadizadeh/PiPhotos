# 4. Machine learning on a GPU machine

Optional. Time: 1 hour. Result: face detection, smart search and OCR run on a computer with an NVIDIA GPU. The Pi keeps thumbnails, metadata and video transcoding, and falls back to its own container when the GPU machine is off.

## 4.1 Why

Measured on a Titan Xp against a loaded Pi 5:

| Task | GPU machine | Pi 5 |
|---|---|---|
| Smart search embedding, one photo | 26 ms | 1.1 s |
| Face detection and recognition, one photo | 40 ms | 2 s |
| Search text encoding | 70 to 90 ms | 400 to 560 ms |

The first pass over 100,000 photos takes one night with the GPU and two weeks without it.

## 4.2 The GPU machine

Any Windows or Linux machine with an NVIDIA card with 8 GB or more of VRAM. Our notes are for Windows 11 with Docker Desktop.

1. Install the NVIDIA driver. For Pascal cards such as the Titan Xp use the 580 series, the last branch that supports them. Check:

```
nvidia-smi
```

2. Install WSL 2, then Docker Desktop with the WSL 2 engine. GPU access is built in. Check:

```
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

3. Create a folder, copy `scripts/ml/docker-compose.gpu-machine.yml` into it as `docker-compose.yml`, and start it:

```
docker compose up -d
docker compose logs -f
```

The first start downloads about 4 GB. Wait for "Application startup complete".

4. Check locally:

```
curl.exe http://localhost:3003/ping
```

Expect `pong`.

## 4.3 Two containers, not one

The compose file starts two containers:

- **GPU container, port 3003**: face detection and smart search.
- **CPU container, port 3004**: OCR.

OCR on CUDA crashed the GPU container when search and faces also ran, and 18 % of requests failed. A separate CPU container fixed it.

## 4.4 Make it reachable from the Pi

1. Give the machine a fixed address in the router.
2. Open the firewall. Docker Desktop opens its ports for the Public profile only. On a home network Windows uses the Private profile, and the Pi's requests time out. Add one rule in an administrator PowerShell:

```powershell
New-NetFirewallRule -DisplayName "Immich ML 3003-3004" -Direction Inbound -Protocol TCP -LocalPort 3003,3004 -Action Allow -Profile Any
```

3. Stop the machine from sleeping while the first pass runs:

```powershell
powercfg /change standby-timeout-ac 0
```

4. Check from the Pi:

```bash
curl http://<gpu-machine>:3003/ping
curl http://<gpu-machine>:3004/ping
```

## 4.5 Tell Immich

Put the GPU machine first and keep the Pi's own container as the last entry. Immich tries the addresses in order and skips a dead one.

```bash
python3 scripts/ml/set_remote_ml.py --api-key-file ~/.config/immich-tools/admin.key \
  --add-url http://<gpu-machine>:3003 --add-url http://<gpu-machine>:3004 \
  --concurrency faceDetection=4 --concurrency smartSearch=4 --concurrency ocr=6
```

The URL order after that: 3004 (OCR on CPU), 3003 (GPU), then `http://immich-machine-learning:3003` (the Pi).

Check in the GPU container's log that "Available ORT providers" lists `CUDAExecutionProvider` when the first job arrives.

## 4.6 Security

The containers have no authentication. They receive a preview of every photo. Keep the ports on the home network. Never forward them on the router.

## 4.7 Pitfalls we met

- **Sleep loops.** Immich pings the machine-learning addresses. A sleeping Windows machine with "wake on pattern match" wakes up for the ping, sleeps again, and loops. Either keep it awake during the pass, or turn off wake on pattern match in the network adapter's power settings.
- **"fetch failed" lines** in the Immich log a few times an hour under load. These are keep-alive races with the CPU container. Immich retries on the next address. Harmless.
- **Model choice is final.** Pick the search model before the first pass ([chapter 3](03-configure.md)).
- **Version lock.** Upgrade the machine-learning image on the GPU machine together with Immich on the Pi. Same version tag.

## 4.8 When the GPU machine is off

Nothing breaks. Searches and new uploads use the Pi's own container. It is slow but correct. Embeddings from both agree to six decimals.
