# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	vmraid.delete_doc_if_exists("DocType", "User Permission for Page and Report")
