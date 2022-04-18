import vmraid
from vmraid.model.rename_doc import rename_doc


def execute():
	if vmraid.db.exists("DocType", "Client Script"):
		return

	vmraid.flags.ignore_route_conflict_validation = True
	rename_doc("DocType", "Custom Script", "Client Script")
	vmraid.flags.ignore_route_conflict_validation = False

	vmraid.reload_doctype("Client Script", force=True)
