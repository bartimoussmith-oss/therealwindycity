# windycity-agent on a Chromebook

A Chromebook is the easiest *client* in this fleet, and it can be a host too.
Pick the row that matches what your Chromebook will let you do:

| Situation | What to do | Why it works |
|---|---|---|
| Plain ChromeOS, no Linux | Run the agent on your **phone (Termux)** or your **Windows PC**, then open its LAN URL in Chrome and choose **Install app** | ChromeOS installs any PWA; the compute stays on the other device |
| ChromeOS with Linux (Crostini) | Open the Terminal app → `bash agent/install/linux.sh` → `wyagent serve` | Crostini is Debian; the runtime is stdlib Python, so no pip needed |
| Newer Chromebook where "Linux development environment" has been retired | Use the **Android app** route: install Termux from F-Droid on your phone, or run the host on the PC and use the PWA | Nothing in this stack requires Crostini — it is a browser client either way |
| No other device at all | Chromebook + PWA against a cloud box, or Google Colab as a temporary host | The runtime is one folder; `wyagent export` moves state anywhere |

## Client setup (the 2-minute path)

1. On the host device: `wyagent serve --port 8765`
2. Look at the host's screen for the LAN URL it printed (e.g. `http://192.168.1.24:8765`)
3. On the Chromebook: open that URL in Chrome
4. Chrome menu (⋮) → **Cast, save, and share** → **Install page as app**, or the install icon in the omnibox
5. Optional: `wyagent pair --name chromebook` and open the URL with `?token=…` for a portable token

The console then lives in the shelf, launches in its own window, and works offline as a shell
(the service worker caches the UI; task execution still happens on the host).

## Away from home

Put the host and the Chromebook on the same **Tailscale** network (free, no port-forwarding):
`curl -fsSL https://tailscale.com/install.sh | sh` on the host, install the Tailscale Android/ChromeOS
app on the client, then use the host's Tailscale IP in the URL.
