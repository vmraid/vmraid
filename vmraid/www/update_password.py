# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
from vmraid import _

no_cache = 1


def get_context(context):
	context.no_breadcrumbs = True
	context.parents = [{"name": "me", "title": _("My Account")}]
