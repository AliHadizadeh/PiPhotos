# Runbook 04: machine learning on a GPU machine

Chapter: `docs/04-ml-offload.md`. Optional.

## Needs
- A machine with an NVIDIA GPU, Docker with GPU access, a fixed address. SSH or the person's hands on it.
- The Immich version on the Pi (`curl -s http://localhost:2283/api/server/version`).

## Steps
1. On the GPU machine: `nvidia-smi` lists the card. `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` lists it inside a container.
2. Copy `scripts/ml/docker-compose.gpu-machine.yml` to a folder as `docker-compose.yml`. Set the image tags to the Pi's version. Set `device_ids` to the cards to use. `docker compose up -d`.
3. `curl http://localhost:3003/ping` and `:3004/ping` on the machine return `pong`.
4. Firewall on Windows: add an inbound rule for TCP 3003 and 3004 on all profiles. Docker Desktop's own rules cover the Public profile only.
5. From the Pi: `curl -m 5 http://<gpu-machine>:3003/ping` and `:3004/ping` return `pong`.
6. Point Immich at it, Pi container last:
   `python3 scripts/ml/set_remote_ml.py --api-key-file ~/.config/immich-tools/admin.key --add-url http://<gpu-machine>:3003 --add-url http://<gpu-machine>:3004 --concurrency faceDetection=4 --concurrency smartSearch=4 --concurrency ocr=6`
7. Benchmark once: `scripts/ml/bench_ml.sh http://<gpu-machine>:3003 /path/to/a.jpg 20 6`. Record the numbers.

## Checks
- The GPU container's log shows `CUDAExecutionProvider` when the first job arrives.
- `docker logs immich_server --since 10m | grep -c 'fetch failed'` stays small (a few per hour under load is normal).

## Stop conditions
- Ports time out from the Pi after the firewall rule: the network profile or a router isolation setting. Report.
- OCR fails on the GPU container: keep OCR on the CPU container, as the compose file does.

## Record
GPU model, driver, image tags, the URL order, the benchmark numbers.
