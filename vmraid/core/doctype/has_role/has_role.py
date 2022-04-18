# -*- coding: utf-8 -*-
# Copyright (c) 2015, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid.model.document import Document


class HasRole(Document):
	def before_insert(self):
		if vmraid.db.exists("Has Role", {"parent": self.parent, "role": self.role}):
			vmraid.throw(vmraid._("User '{0}' already has the role '{1}'").format(self.parent, self.role))
