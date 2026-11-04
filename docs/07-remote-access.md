# 7. Remote access

Time: 1 hour. Result: the Immich app works at home and away, over Tailscale, with HTTPS and no open ports on your router.

## 7.1 Why Tailscale

- No port forwarding. Nothing on the internet can reach the Pi.
- HTTPS with a real certificate, through `tailscale serve`.
- No request size limit. Cloudflare's tunnel caps requests at 100 MB, too small for videos.

## 7.2 On the Pi

1. Install Tailscale and log in:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

2. In the Tailscale admin console, open the Pi's machine and **disable key expiry**. Otherwise the Pi drops off the VPN after a few months. The trade-off: the Pi stays signed in for good. If the Pi is ever lost or stolen, remove it from the tailnet in the admin console at once.

3. Enable HTTPS certificates for your tailnet in the admin console under DNS.

4. Publish Immich on the tailnet only:

```bash
sudo tailscale serve --bg --https=443 http://127.0.0.1:2283
tailscale serve status
```

Expect `https://<pi-name>.<tailnet>.ts.net (tailnet only)`. Keep Funnel off. Funnel would publish Immich to the whole internet.

5. Put that address into Immich under Administration, Settings, Server, External domain.

## 7.3 On the phones

1. Install Tailscale from the App Store. Log in with the same account or an invited one.
2. In the Immich app open Settings, Networking, and turn on **Automatic URL switching**:
   - Local network: your home Wi-Fi name, and the server endpoint `http://<pi-name>.local:2283/api`. "Use current connection" fills it in while you are at home.
   - External network: `https://<pi-name>.<tailnet>.ts.net/`.
3. At home the app talks to the Pi directly. Anywhere else it uses the Tailscale address, which works only while Tailscale is connected. The shortcut below takes care of that.

## 7.4 iPhone shortcut: VPN only when needed

Tailscale on all the time drains some battery and routes everything through the tailnet. This automation connects the VPN only when the Immich app opens away from home, and disconnects when the app closes.

In the Shortcuts app, create an Automation:

1. **Trigger**: When the app **Immich** is **Opened or Closed**. Set it to run immediately, without asking.
2. **Actions**:

```
Get Current app
If  Current App  is  Immich
    Get Wi-Fi network's Name
    If  Network Details  is not  <your home Wi-Fi name>
        Connect to Tailscale
    Otherwise if  Network Details  does not have any value
        Connect to Tailscale
    End If
Otherwise
    Disconnect from Tailscale
End If
```

Notes:

- "Does not have any value" covers mobile data, where there is no Wi-Fi name.
- The Tailscale actions "Connect" and "Disconnect" come from the Tailscale app. Update the app if they are missing.
- At home the VPN stays off and the app uses the local endpoint from 7.3.
- Test it: close Immich, turn off Wi-Fi, open Immich. The Tailscale icon appears in the status bar. Close Immich. The icon goes away.

## 7.5 Checks

```bash
tailscale status                 # the phones appear as online when connected
tailscale serve status           # the Immich proxy is listed
curl -sI https://<pi-name>.<tailnet>.ts.net | head -1    # HTTP/2 200
```
