# Runbook 07: remote access

Chapter: `docs/07-remote-access.md`.

## Needs
- A Tailscale account. The person's phone in their hands.

## Steps
1. On the Pi: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`. Give the person the login URL it prints.
2. Ask the person to disable key expiry for the Pi in the admin console, and to enable HTTPS certificates under DNS.
3. `sudo tailscale serve --bg --https=443 http://127.0.0.1:2283`. Check `tailscale serve status` shows `(tailnet only)`.
4. Put the address into Immich: Administration, Settings, Server, External domain, or through the settings API.
5. Phones: Tailscale app installed and logged in. Immich app, Settings, Networking: automatic URL switching on, local network = home Wi-Fi name with `http://<pi>.local:2283/api`, external = the Tailscale address.
6. Shortcut on iPhone, as in chapter 7.4. Give the person the exact action list. They build it; you cannot.

## Checks
- `tailscale status` lists the phones.
- `curl -sI https://<pi>.<tailnet>.ts.net | head -1` prints a 200.
- The person opens Immich on mobile data: the Tailscale icon appears and photos load.

## Stop conditions
- Funnel is on. Turn it off; Immich must not be public.

## Record
The Tailscale address, the serve configuration, the date key expiry was disabled.
