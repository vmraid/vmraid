# -*- coding: utf-8 -*-
# Copyright (c) 2017, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import json

import vmraid
import vmraid.utils
from vmraid import _
from vmraid.model.document import Document
from vmraid.utils.jinja import validate_template
from vmraid.utils.weasyprint import download_pdf, get_html


class PrintFormat(Document):
	def onload(self):
		templates = vmraid.db.get_all(
			"Print Format Field Template",
			fields=["template", "field", "name"],
			filters={"document_type": self.doc_type},
		)
		self.set_onload("print_templates", templates)

	def get_html(self, docname, letterhead=None):
		return get_html(self.doc_type, docname, self.name, letterhead)

	def download_pdf(self, docname, letterhead=None):
		return download_pdf(self.doc_type, docname, self.name, letterhead)

	def validate(self):
		if (
			self.standard == "Yes"
			and not vmraid.local.conf.get("developer_mode")
			and not (vmraid.flags.in_import or vmraid.flags.in_test)
		):

			vmraid.throw(vmraid._("Standard Print Format cannot be updated"))

		# old_doc_type is required for clearing item cache
		self.old_doc_type = vmraid.db.get_value("Print Format", self.name, "doc_type")

		self.extract_images()

		if not self.module:
			self.module = vmraid.db.get_value("DocType", self.doc_type, "module")

		if self.html and self.print_format_type != "JS":
			validate_template(self.html)

		if self.custom_format and self.raw_printing and not self.raw_commands:
			vmraid.throw(
				_("{0} are required").format(vmraid.bold(_("Raw Commands"))), vmraid.MandatoryError
			)

		if self.custom_format and not self.html and not self.raw_printing:
			vmraid.throw(_("{0} is required").format(vmraid.bold(_("HTML"))), vmraid.MandatoryError)

	def extract_images(self):
		from vmraid.core.doctype.file.file import extract_images_from_html

		if self.print_format_builder_beta:
			return

		if self.format_data:
			data = json.loads(self.format_data)
			for df in data:
				if df.get("fieldtype") and df["fieldtype"] in ("HTML", "Custom HTML") and df.get("options"):
					df["options"] = extract_images_from_html(self, df["options"])
			self.format_data = json.dumps(data)

	def on_update(self):
		if hasattr(self, "old_doc_type") and self.old_doc_type:
			vmraid.clear_cache(doctype=self.old_doc_type)
		if self.doc_type:
			vmraid.clear_cache(doctype=self.doc_type)

		self.export_doc()

	def after_rename(self, old: str, new: str, *args, **kwargs):
		if self.doc_type:
			vmraid.clear_cache(doctype=self.doc_type)

		# update property setter default_print_format if set
		vmraid.db.set_value(
			"Property Setter",
			{
				"doctype_or_field": "DocType",
				"doc_type": self.doc_type,
				"property": "default_print_format",
				"value": old,
			},
			"value",
			new,
		)

	def export_doc(self):
		from vmraid.modules.utils import export_module_json

		export_module_json(self, self.standard == "Yes", self.module)

	def on_trash(self):
		if self.doc_type:
			vmraid.clear_cache(doctype=self.doc_type)


@vmraid.whitelist()
def make_default(name):
	"""Set print format as default"""
	vmraid.has_permission("Print Format", "write")

	print_format = vmraid.get_doc("Print Format", name)

	if (vmraid.conf.get("developer_mode") or 0) == 1:
		# developer mode, set it default in doctype
		doctype = vmraid.get_doc("DocType", print_format.doc_type)
		doctype.default_print_format = name
		doctype.save()
	else:
		# customization
		vmraid.make_property_setter(
			{
				"doctype_or_field": "DocType",
				"doctype": print_format.doc_type,
				"property": "default_print_format",
				"value": name,
			}
		)

	vmraid.msgprint(
		vmraid._("{0} is now default print format for {1} doctype").format(
			vmraid.bold(name), vmraid.bold(print_format.doc_type)
		)
	)
