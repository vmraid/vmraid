# Copyright (c) 2021, VMRaid Technologies and contributors
# For license information, please see license.txt

import vmraid
from vmraid import _
from vmraid.model.document import Document


class PrintFormatFieldTemplate(Document):
	def validate(self):
		if self.standard and not (vmraid.conf.developer_mode or vmraid.flags.in_patch):
			vmraid.throw(_("Enable developer mode to create a standard Print Template"))

	def before_insert(self):
		self.validate_duplicate()

	def on_update(self):
		self.validate_duplicate()
		self.export_doc()

	def validate_duplicate(self):
		if not self.standard:
			return
		if not self.field:
			return

		filters = {"document_type": self.document_type, "field": self.field}
		if not self.is_new():
			filters.update({"name": ("!=", self.name)})
		result = vmraid.db.get_all("Print Format Field Template", filters=filters, limit=1)
		if result:
			vmraid.throw(
				_("A template already exists for field {0} of {1}").format(
					vmraid.bold(self.field), vmraid.bold(self.document_type)
				),
				vmraid.DuplicateEntryError,
				title=_("Duplicate Entry"),
			)

	def export_doc(self):
		from vmraid.modules.utils import export_module_json

		export_module_json(self, self.standard, self.module)
