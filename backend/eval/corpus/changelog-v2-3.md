# Release notes for version 2.3

Version 2.3.0 (March)
New: shared drafts let several people edit a page at once with live cursors. New: project templates can be saved and reused across the workspace. New: the search bar now finds text inside PDF and Office documents. Improved: uploads of many small files are up to three times faster. Improved: the mobile app opens large folders without freezing. Changed: the default share link expiry is now 30 days instead of never; existing links are not affected.

Version 2.3.1 (April)
Fixed: files with accents or emoji in their names failed to sync on Windows. Fixed: the sync client sometimes reported ERR_CONN_RESET after waking from sleep; it now reconnects quietly. Fixed: single sign-on users were shown E-4013 when their clock was slightly ahead; we now accept a skew of five minutes. Fixed: invoice PDFs showed the wrong tax number for some European customers. Security: updated a third-party library used for image previews.

Upgrading. The web app updates automatically. Desktop clients download v2.3.1 in the background and ask you to restart. Administrators can pause updates for up to 30 days in Settings, Devices.

Known issue. In version 2.3.0 the Linux client may fail to start on distributions that ship an older graphics library; v2.3.1 includes a workaround and the fix is planned for the next minor release.
