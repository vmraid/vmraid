# -*- coding: utf-8 -*-
# Copyright (c) 2015, VMRaid and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid.model.document import Document


class UnhandledEmail(Document):
	pass


def remove_old_unhandled_emails():
	vmraid.db.delete(
		"Unhandled Email", {"creation": ("<", vmraid.utils.add_days(vmraid.utils.nowdate(), -30))}
	)
