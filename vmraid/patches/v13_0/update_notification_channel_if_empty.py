# Copyright (c) 2020, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():

	vmraid.reload_doc("Email", "doctype", "Notification")

	notifications = vmraid.get_all("Notification", {"is_standard": 1}, {"name", "channel"})
	for notification in notifications:
		if not notification.channel:
			vmraid.db.set_value(
				"Notification", notification.name, "channel", "Email", update_modified=False
			)
			vmraid.db.commit()
