# Copyright (c) 2020, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	vmraid.delete_doc("DocType", "Package Publish Tool", ignore_missing=True)
	vmraid.delete_doc("DocType", "Package Document Type", ignore_missing=True)
	vmraid.delete_doc("DocType", "Package Publish Target", ignore_missing=True)
