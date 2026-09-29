# Proxmox & App Setup

This guide covers configuring Proxmox VE and connecting it to the SPICE Manager app. These steps apply to both Linux and Windows.

---

## Proxmox Setup

You can use an existing user/password or a user/API token. API tokens are recommended.

### User

From the Datacenter section, go to **Users** and create a new user. Use the **Proxmox VE** auth type and set a secure password.

### Role

Create a minimal role with only the permissions needed. Select `VM.PowerMgmt` `VM.Audit` `VM.Snapshot.Rollback` `VM.Console` `Pool.Audit` `VM.Snapshot` `VM.GuestAgent.Audit`

> **Note:** `VM.GuestAgent.Audit` is optional — it enables the live IP address column. Without it, the IP column will be blank but everything else works normally.

<img width="412" height="161" alt="image" src="https://github.com/user-attachments/assets/6bb496db-c912-40e2-bf56-492bed073d0e" />

### API Token

Create a token and keep **Privilege Separation** checked. Make note of the API key — this is the only time you will see it.

<img width="649" height="224" alt="image" src="https://github.com/user-attachments/assets/bf14f201-348c-428e-a9e8-b88466974539" />

### Permissions

You will need two permission entries: one for the user and one for the API token. Choose the role you created for both. Privilege Separation makes this necessary and is a safety feature.

<img width="1939" height="78" alt="image" src="https://github.com/user-attachments/assets/3af82e64-1413-4124-9c80-159fcc41774f" />

### VM Display Configuration

> **SPICE is for graphical (GUI) operating systems only.** Headless or CLI-only VMs won't benefit from a SPICE console — use SSH for those instead.

For a VM to appear in the app, set its display to **SPICE (qxl)** under Hardware → Display in the Proxmox web UI.

SPICE sessions will open but won't function correctly without guest drivers installed inside the VM:

- **Windows guests** — install the [VirtIO drivers](https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso) (`virtio-win-guest-tools.exe`) and [SPICE guest tools](https://www.spice-space.org/download.html)
- **Linux guests** — install `spice-vdagent` (`sudo dnf install spice-vdagent` or `sudo apt install spice-vdagent`)

---

## App Setup

Open the SPICE Manager and choose **Add cluster** from the lower left.

Enter the name, any of the hosts in the cluster, and the token ID and secret. Take note of the format of the token ID: `user@realm!tokenname`.

| Windows | Linux |
|---|---|
| ![The Add Cluster dialog on Windows, filled in with a name, host URL, token ID and secret](docs/screenshots/windows-add-cluster.png) | ![The Add Cluster dialog on Linux, filled in the same way](docs/screenshots/linux-add-cluster.png) |

Choose the cluster and hit **Refresh**. Any VM with the display set to SPICE will show up here.

![The main window listing the cluster's SPICE VMs, grouped by node](docs/screenshots/windows-main.png)

You can launch console sessions directly from the app, or on Linux you can export individual VM sessions as desktop shortcuts to launch them without opening the app. Select the VM, open **Settings**, and choose **Export .desktop for selected VM…**:

![The Linux Settings menu, with Export .desktop for selected VM at the bottom](docs/screenshots/linux-settings.png)

![The confirmation that the launcher was saved in ~/.local/share/applications](docs/screenshots/linux-export-desktop.png)
