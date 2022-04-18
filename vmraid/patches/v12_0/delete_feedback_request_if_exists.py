import vmraid


def execute():
	vmraid.db.delete("DocType", {"name": "Feedback Request"})
