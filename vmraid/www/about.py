# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid

sitemap = 1


def get_context(context):
	context.doc = vmraid.get_doc("About Us Settings", "About Us Settings")

	return context
