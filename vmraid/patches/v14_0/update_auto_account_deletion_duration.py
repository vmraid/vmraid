import vmraid


def execute():
	days = vmraid.db.get_single_value("Website Settings", "auto_account_deletion")
	vmraid.db.set_value("Website Settings", None, "auto_account_deletion", days * 24)
