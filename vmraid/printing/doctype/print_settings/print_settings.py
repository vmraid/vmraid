# -*- coding: utf-8 -*-
# Copyright (c) 2018, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid import _
from vmraid.model.document import Document
from vmraid.utils import cint


class PrintSettings(Document):
	def validate(self):
		if self.pdf_page_size == "Custom" and not (self.pdf_page_height and self.pdf_page_width):
			vmraid.throw(_("Page height and width cannot be zero"))

	def on_update(self):
		vmraid.clear_cache()


@vmraid.whitelist()
def is_print_server_enabled():
	if not hasattr(vmraid.local, "enable_print_server"):
		vmraid.local.enable_print_server = cint(
			vmraid.db.get_single_value("Print Settings", "enable_print_server")
		)

	return vmraid.local.enable_print_server
