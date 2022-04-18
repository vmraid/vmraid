# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def get_context(context):
	token = vmraid.local.form_dict.token

	if token:
		vmraid.db.set_value("Integration Request", token, "status", "Cancelled")
		vmraid.db.commit()
