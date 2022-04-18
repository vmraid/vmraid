# -*- coding: utf-8 -*-
# Copyright (c) 2017, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid.model.document import Document


class PrintStyle(Document):
	def validate(self):
		if (
			self.standard == 1
			and not vmraid.local.conf.get("developer_mode")
			and not (vmraid.flags.in_import or vmraid.flags.in_test)
		):

			vmraid.throw(vmraid._("Standard Print Style cannot be changed. Please duplicate to edit."))

	def on_update(self):
		self.export_doc()

	def export_doc(self):
		# export
		from vmraid.modules.utils import export_module_json

		export_module_json(self, self.standard == 1, "Printing")
