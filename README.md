# Proxmox Spice Manager
Utility For Accessing SPICE console via API or password. 
<br> This was made for Fedora OS, PURELY vibe coded. I had a need, Claude helped me to make it real. Feel free modify as you see fit.


**Steps:**

Download script to a location of your choosing, and then change to executable. 
<br> **chmod +x proxmox-spice-manager.py**

Run Script, and a pre-req check should appear.

<img width="665" height="579" alt="image" src="https://github.com/user-attachments/assets/51df513d-68b8-412e-a8c7-de87e238b8ff" />

Click to install what's misisng and a password prompt will appear. 

<img width="1508" height="616" alt="image" src="https://github.com/user-attachments/assets/05cced05-acf3-4c57-bf2d-823081a5249c" />

Recheck will then close the window, and the app should pop up. To "install" the app in the upper right there is a "Install To App Menu" option. You can choose an icon or use a custom one. 

<img width="1039" height="704" alt="image" src="https://github.com/user-attachments/assets/ced942a2-0759-4b86-8576-88b9a471bd45" />

<img width="393" height="328" alt="image" src="https://github.com/user-attachments/assets/c0343bab-4da4-4577-83f6-daf41fc45c88" />

You can then search for it, and add pin it to the taskbar.

<img width="672" height="162" alt="image" src="https://github.com/user-attachments/assets/c94002fd-3258-4252-ae0e-768e198c29a3" />



**Proxmox Setup**

You can use an existing user/password or user/api token. I recommend API. Here's how to set that up.

USER
From the datacenter section, go to users and create a new user. Use the Proxmox VE auth type, and set a secure password. 

ROLE
Let's make this only for what is absolutely needed. Create a new role, and choose vm.audit, Pool.Audit, and VM.Console

<img width="412" height="161" alt="image" src="https://github.com/user-attachments/assets/6bb496db-c912-40e2-bf56-492bed073d0e" />

API Token

Create a token, keep Privilege Seperation checked. Make note of the API key, this is the only time you'll need it.
<img width="649" height="224" alt="image" src="https://github.com/user-attachments/assets/bf14f201-348c-428e-a9e8-b88466974539" />

Permissions

You'll need two entries. One for the user, and one for the API. Choose the role yuou created for both. (Privilege Seperation makes this necessary and is a safety feature)

<img width="1939" height="78" alt="image" src="https://github.com/user-attachments/assets/3af82e64-1413-4124-9c80-159fcc41774f" />

**Spice Manager Setup**

Go back to PSM, and chose "add" from the lower left.

Enter the name, any of the hosts in the cluster, and the token ID and secret. Take note of the format of the token ID. 

<img width="508" height="518" alt="image" src="https://github.com/user-attachments/assets/3cec87b4-500d-4c79-9303-0bc8afae8f98" />

Choose the cluster and hit "refresh". Any VM with the display set to SPICE will show up here. 

<img width="998" height="674" alt="image" src="https://github.com/user-attachments/assets/3bd7169e-c7b1-4a5c-b9fc-ab7dd83d19fd" />

<br>

You can launch the console sessions from here or export them to the desktop in the same way we did for the app. 
<br>

<img width="788" height="279" alt="image" src="https://github.com/user-attachments/assets/58c46e71-edba-4821-a977-2c527bbc138d" />
<br>

<img width="656" height="133" alt="image" src="https://github.com/user-attachments/assets/7ca80959-040b-4525-994c-6e65a1bcaedd" />







