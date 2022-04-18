import vmraid
from vmraid.model.rename_doc import rename_doc


def execute():
	if vmraid.db.exists("DocType", "Google Maps") and not vmraid.db.exists(
		"DocType", "Google Maps Settings"
	):
		rename_doc("DocType", "Google Maps", "Google Maps Settings")
