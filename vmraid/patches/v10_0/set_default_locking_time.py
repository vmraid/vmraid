# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	vmraid.reload_doc("core", "doctype", "system_settings")
	vmraid.db.set_value("System Settings", None, "allow_login_after_fail", 60)
