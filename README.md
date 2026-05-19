NOTE: The Windows client can be found under the files section on the main page. 


# Proxmox Spice Manager

A utility for accessing SPICE consoles via API or password.

Built for Fedora/Debian OS, purely vibe coded. I had a need, Claude helped me make it real. Feel free to modify as you see fit.

---

## Getting Started

Download the script to a location of your choosing, then make it executable:

```bash
chmod +x proxmox-spice-manager.py
```
**FEDORA** <br>
Run the script. A prerequisite check should appear on first launch.

<img width="665" height="579" alt="image" src="https://github.com/user-attachments/assets/51df513d-68b8-412e-a8c7-de87e238b8ff" />

Click to install anything that is missing. A password prompt will appear.

<img width="1508" height="616" alt="image" src="https://github.com/user-attachments/assets/05cced05-acf3-4c57-bf2d-823081a5249c" />

After the recheck completes, the window will close and the app should pop up. To "install" the app, use the **Install To App Menu** option in the upper right. You can choose a bundled icon or use a custom one.

<img width="1039" height="704" alt="image" src="https://github.com/user-attachments/assets/ced942a2-0759-4b86-8576-88b9a471bd45" />

<img width="393" height="328" alt="image" src="https://github.com/user-attachments/assets/c0343bab-4da4-4577-83f6-daf41fc45c88" />

You can then search for it and pin it to your taskbar.

<img width="672" height="162" alt="image" src="https://github.com/user-attachments/assets/c94002fd-3258-4252-ae0e-768e198c29a3" /> <br>

**DEBIAN** <br>

Debian desktop doesn't include the user in sudoers by default so the logic changes a bit. <br>
Running the script directly will provide this error: <br>
<img width="660" height="173" alt="image" src="https://github.com/user-attachments/assets/937ac173-666f-4928-88ff-bd3cc95ea283" /> <br>


<img width="518" height="83" alt="image" src="https://github.com/user-attachments/assets/50bd7ec1-5db4-497b-806e-159746a3510c" /> 
Install the file, and then run the script again. <br>

You'll then get the setup install screen to whatever else may be missing.
<img width="1029" height="625" alt="image" src="https://github.com/user-attachments/assets/86a3141d-2cb4-4c6b-9e8a-aeddc30a5400" />



---

## Proxmox Setup

You can use an existing user/password or a user/API token. API tokens are recommended. Here is how to set that up.

### User

From the Datacenter section, go to **Users** and create a new user. Use the **Proxmox VE** auth type and set a secure password.

### Role

Create a minimal role with only the permissions that are needed. Create a new role and select `VM.PowerMgmt` `VM.Audit` `VM.Snapshot.Rollback` `VM.Console` `Pool.Audit` `VM.Snapshot`

<img width="412" height="161" alt="image" src="https://github.com/user-attachments/assets/6bb496db-c912-40e2-bf56-492bed073d0e" />

### API Token

Create a token and keep **Privilege Separation** checked. Make note of the API key, as this is the only time you will see it.

<img width="649" height="224" alt="image" src="https://github.com/user-attachments/assets/bf14f201-348c-428e-a9e8-b88466974539" />

### Permissions

You will need two permission entries: one for the user and one for the API token. Choose the role you created for both. Privilege Separation makes this necessary and is a safety feature.

<img width="1939" height="78" alt="image" src="https://github.com/user-attachments/assets/3af82e64-1413-4124-9c80-159fcc41774f" />

---

## Spice Manager Setup

Go back to PSM and choose **Add** from the lower left.

Enter the name, any of the hosts in the cluster, and the token ID and secret. Take note of the format of the token ID.

<img width="508" height="518" alt="image" src="https://github.com/user-attachments/assets/3cec87b4-500d-4c79-9303-0bc8afae8f98" />

Choose the cluster and hit **Refresh**. Any VM with the display set to SPICE will show up here.

<img width="998" height="674" alt="image" src="https://github.com/user-attachments/assets/3bd7169e-c7b1-4a5c-b9fc-ab7dd83d19fd" />

You can launch console sessions from here or export them to the desktop in the same way you installed the app.

<img width="788" height="279" alt="image" src="https://github.com/user-attachments/assets/58c46e71-edba-4821-a977-2c527bbc138d" />

<img width="656" height="133" alt="image" src="https://github.com/user-attachments/assets/7ca80959-040b-4525-994c-6e65a1bcaedd" />
