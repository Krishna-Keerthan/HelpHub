# Storage quotas and what happens when you run out

Each member of a paid plan contributes storage to a pool shared by the whole workspace. A Team workspace with ten members has 1 TB of pooled space, and a Business workspace with ten members has 10 TB. Free workspaces have a flat 5 GB.

Checking usage. Settings, Storage shows total usage, the biggest folders and the members who upload the most. Usage counts the current version of every file plus old versions kept for history. The trash counts too, until it is emptied or the 30-day retention ends.

Warnings. At 80 percent owners receive an email. At 95 percent every member sees a banner.

Quota exceeded. When the pool is full the API and the apps return error E-5001 on upload. Existing files remain available and nothing is deleted. To continue you can delete files and empty the trash, shorten version history from 100 to 10 versions, upgrade the plan, or buy a storage add-on.

Add-ons. SKU AB-1234-XL adds 50 TB and is the largest standard pack; smaller packs are listed on the pricing page. Capacity is available immediately after purchase.

Version history keeps up to 100 versions of each file for 180 days on Business and 30 days on Team. Deleting a project moves its files to the trash, where they stay for 30 days.
