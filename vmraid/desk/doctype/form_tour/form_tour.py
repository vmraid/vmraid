# Copyright (c) 2021, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid.model.document import Document
from vmraid.modules.export_file import export_to_files


class FormTour(Document):
	def before_save(self):
		meta = vmraid.get_meta(self.reference_doctype)
		for step in self.steps:
			if step.is_table_field and step.parent_fieldname:
				parent_field_df = meta.get_field(step.parent_fieldname)
				step.child_doctype = parent_field_df.options

				field_df = vmraid.get_meta(step.child_doctype).get_field(step.fieldname)
				step.label = field_df.label
				step.fieldtype = field_df.fieldtype
			else:
				field_df = meta.get_field(step.fieldname)
				step.label = field_df.label
				step.fieldtype = field_df.fieldtype

	def on_update(self):
		if vmraid.conf.developer_mode and self.is_standard:
			export_to_files([["Form Tour", self.name]], self.module)
