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

<img width="665" height="579" alt="image" src="https://github.com/user-attachments/assets/51df513d-68b8-412e-a8c7-de87e238b8ff" />

Click to install anything that is missing. A password prompt will appear.

<img width="1508" height="616" alt="image" src="https://github.com/user-attachments/assets/05cced05-acf3-4c57-bf2d-823081a5249c" />

After the recheck completes, the window will close and the app should pop up. To "install" the app, use the **Install To App Menu** option in the upper right. You can choose a bundled icon or use a custom one.

<img width="1039" height="704" alt="image" src="https://github.com/user-attachments/assets/ced942a2-0759-4b86-8576-88b9a471bd45" />

<img width="393" height="328" alt="image" src="https://github.com/user-attachments/assets/c0343bab-4da4-4577-83f6-daf41fc45c88" />

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

<img width="1029" height="625" alt="image" src="https://github.com/user-attachments/assets/86a3141d-2cb4-4c6b-9e8a-aeddc30a5400" />

---

Once the app is running, continue with [proxmox-setup.md](proxmox-setup.md) to configure your Proxmox connection.
