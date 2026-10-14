# Installing the desktop client

The desktop client is available for Windows 10 and 11, macOS 12 and newer, and Linux (Debian, Ubuntu and Fedora packages).

Windows. Download the installer from Settings, Devices, and run it. If your organisation restricts software installation, an administrator can deploy the MSI package silently with msiexec. After installation sign in and choose the folder to sync; the default is Acme Cloud in your user folder. If the installer stops with error 0x80070005, the account does not have permission to write to the target folder. Run the installer as an administrator or pick a folder you own, and make sure antivirus software is not blocking the installer.

macOS. Open the disk image and drag Acme Cloud into Applications. The first time you start it, macOS asks for permission to access files and, on newer versions, to enable the file provider extension. Allow both in System Settings, Privacy and Security.

Linux. Install the package with your package manager, for example sudo apt install ./acme-cloud.deb, then start the client from the application menu. A graphical desktop is required.

System requirements. 4 GB of memory, 500 MB of free disk space for the program and enough space for the folders you sync.

To uninstall, remove the program in the normal way; your synced files stay in place.
