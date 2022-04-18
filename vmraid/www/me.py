# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid
import vmraid.www.list
from vmraid import _

no_cache = 1


def get_context(context):
	if vmraid.session.user == "Guest":
		vmraid.throw(_("You need to be logged in to access this page"), vmraid.PermissionError)

	context.current_user = vmraid.get_doc("User", vmraid.session.user)
