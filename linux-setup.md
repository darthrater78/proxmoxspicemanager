# Linux Setup

A walkthrough for installing and running Proxmox SPICE Manager on Fedora and Debian/Ubuntu. For Proxmox server configuration and first-run app setup, see [proxmox-setup.md](proxmox-setup.md).

---

## Getting Started

Download the script to a location of your choosing, then make it executable:

```bash
chmod +x proxmox-spice-manager.py
```

**FEDORA**

Run the script. A prerequisite check should appear on first launch.

![The prerequisite check on Fedora, listing virt-viewer and python3-keyring as not found, each with an Install button and its dnf command](docs/screenshots/linux-prereqs-fedora.png)

Click to install anything that is missing. A password prompt will appear.

<img width="1508" height="616" alt="image" src="https://github.com/user-attachments/assets/05cced05-acf3-4c57-bf2d-823081a5249c" />

After the recheck completes, the window will close and the app should pop up. To "install" the app, open **Settings** (bottom left) and choose **Install to app menu…**. You can choose a bundled icon or use a custom one.

![The Settings menu, with Install to app menu near the bottom](docs/screenshots/linux-settings.png)

![The icon picker: ten system icons, or a custom icon file](docs/screenshots/linux-icon-picker.png)

You can then search for it and pin it to your taskbar.

<img width="672" height="162" alt="image" src="https://github.com/user-attachments/assets/c94002fd-3258-4252-ae0e-768e198c29a3" />

---

**DEBIAN**

Debian desktop doesn't include the user in sudoers by default so the logic changes a bit.

Running the script directly will provide this error:

<img width="660" height="173" alt="image" src="https://github.com/user-attachments/assets/937ac173-666f-4928-88ff-bd3cc95ea283" />

<img width="518" height="83" alt="image" src="https://github.com/user-attachments/assets/50bd7ec1-5db4-497b-806e-159746a3510c" />

The app will display the exact install command it needs — copy it, run it in your terminal, then run the script again.

You'll then get the setup install screen for whatever else may be missing.

![The prerequisite check on Debian, where the install commands use su -c instead of sudo](docs/screenshots/linux-prereqs-debian.png)

---

Once the app is running, continue with [proxmox-setup.md](proxmox-setup.md) to configure your Proxmox connection.
