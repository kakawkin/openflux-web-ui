# 🚀 OpenFlux Web UI & Multi-User Panel

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/OpenFlux-Go%20Core-00ADD8?style=for-the-badge&logo=go" alt="Go">
  <img src="https://img.shields.io/badge/TailwindCSS-v3-38B2AC?style=for-the-badge&logo=tailwind-css" alt="Tailwind">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="MIT License">
</p>

A modern management web panel and multi-user gateway for **[OpenFlux](https://github.com/p1neappleXpress/OpenFlux)**. Turns OpenFlux into a production-ready, multi-user system with automated process management, cryptographic keys, `openflux://` links, QR codes, cookie synchronization, and traffic monitoring.

---

## 💡 Overview & Architecture

Original **OpenFlux** exit nodes are architected strictly for **one client per node**:
* If multiple clients connect to a single exit node simultaneously, they conflict and reset each other's sessions.

### Solution: «Instance-per-User» Pattern
This panel implements isolated process pools:
* Each user gets an independent OpenFlux systemd service: `openflux@<username>.service`.
* Each user is provisioned with their own AES-256 key, document channel URL, and dedicated direct TCP port.
* Real-time metrics and hot cookie injection communicate via Unix IPC domain sockets (`/run/openflux/<username>.sock`).
* **Resource footprint:** each OpenFlux process consumes only **~20–30 MB RAM**, easily allowing dozens of concurrent users on a 1 GB VPS.

---

## ⚡ Quick 1-Command Automated Installation

Run on your Ubuntu 22.04 / 24.04 or Debian 11 / 12 server:

```bash
git clone https://github.com/kakawkin/openflux-web-ui.git /opt/openflux-web-ui
cd /opt/openflux-web-ui
sudo bash install.sh
```

The installer will:
1. Detect your public server IP / domain.
2. Prompt for your preferred admin password.
3. Install system prerequisites (Python 3, venv, pip, curl, ufw, systemd).
4. Install the precompiled OpenFlux binary into `/usr/local/bin/openflux`.
5. Set up Python venv and install dependencies.
6. Configure systemd services (`openflux-ui` and template `openflux@`).
7. Open direct TCP ports `8440-8500` in UFW firewall.
8. Install global CLI commands: `openflux-qr` and `openflux-mode`.

---

## 🚚 Supported Transports

| Transport | Obfuscation Protocol | Speed | Description |
|---|---|---|---|
| **Yandex Telemost** (`telemost`) | WebRTC SFU / Media stream (`StripedTransport`) | **Up to 40+ Mbps** | 🏆 **Recommended.** Highest download speed. Direct WebRTC meeting link via `telemost.yandex.ru`, no disk files required. |
| **Yandex Docs** (`yandex`) | WebSocket / Live edit | Up to 10–15 Mbps | Classic bypass over public editable text doc or sheet on Yandex Disk. |
| **Yandex Volga** (`vyandex`) | HTTP Relay + WebSocket | Up to 10 Mbps | Volga transport over Yandex Disk with HTTP polling. |
| **Mail.ru Docs** (`mailru`) | WebSocket Cloud Office | Up to 10–15 Mbps | Live collaborative editing in Cloud Mail.ru. |
| **Avito Code** (`avito`) | ShareDB / OT stream | Up to 5–10 Mbps | Collaborative code session on `code.avito.ru`. |
| **Yandex Boards** (`boards`) | WebSocket | Up to 5–10 Mbps | Public online whiteboard on `boards.yandex.ru`. |
| **Cups.online** (`cupsonline`) | Centrifugo WebSocket | Up to 5–10 Mbps | Interview rooms on `cups.online`. |

---

## 🔀 Two Operating Modes: Classic vs Session

* 🟢 **Classic (Cloud Docs Only):**
  Traffic flows stealthily solely through cloud document WebSockets or WebRTC without opening any inbound TCP ports.
* 🔵 **Session (Direct TCP Port / Cookies):**
  Opens a direct TCP port (e.g. `8441`). Enables the client to pass Yandex SmartCaptcha with the server's IP and automatically sync valid cookies back to the node.

---

## 🛡️ User Roles & Personal Portal

* **Admin Portal (`/dashboard`):**
  Add, rename, delete profiles across all 7 transports; monitor active processes, live traffic metrics, VPS RAM, and view real-time system logs. Manage global host/domain and admin credentials. Includes an interactive modal guide for configuring transports.
* **User Portal (`/my`):**
  Users log in with their assigned credentials. They can:
  - View dynamic QR codes and copy official `openflux://v1/...` links.
  - Download preconfigured `client.conf`.
  - **Change transport protocol & connection URL** directly from their cabinet (old cookies are automatically purged upon transport switch).
  - Access an **in-cabinet interactive setup guide** for all supported transports.
  - Toggle Classic ↔ Session modes and restart their personal service.
  - Set a custom cabinet password.
* **Zero-CDN Architecture:**
  Tailwind CSS and Lucide icons are bundled locally in `app/static/`, making the web panel 100% resilient to external CDN blocks or air-gapped environments.

---

## 📟 CLI Commands

* **Display terminal ASCII QR code:**
  ```bash
  openflux-qr <username>
  ```
* **Switch user mode:**
  ```bash
  openflux-mode <username> session
  openflux-mode <username> classic
  ```
* **Manage panel service:**
  ```bash
  systemctl status openflux-ui
  journalctl -u openflux-ui -f
  ```

---

## 📜 License & Credits

* Released under the [MIT License](LICENSE).
* Network engine powered by [OpenFlux](https://github.com/p1neappleXpress/OpenFlux).
