# Copyright (c) 2020, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	vmraid.reload_doc("website", "doctype", "web_page_block")
	# remove unused templates
	vmraid.delete_doc("Web Template", "Navbar with Links on Right", force=1)
	vmraid.delete_doc("Web Template", "Footer Horizontal", force=1)
