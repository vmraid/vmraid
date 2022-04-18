# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
import vmraid

no_cache = 1


def get_context(context):
	if vmraid.flags.in_migrate:
		return
	context.http_status_code = 500

	print(vmraid.get_traceback())
	return {"error": vmraid.get_traceback().replace("<", "&lt;").replace(">", "&gt;")}
