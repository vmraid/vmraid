# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid

no_cache = True


def get_context(context):
	token = vmraid.local.form_dict.token
	doc = vmraid.get_doc(vmraid.local.form_dict.doctype, vmraid.local.form_dict.docname)

	context.payment_message = ""
	if hasattr(doc, "get_payment_success_message"):
		context.payment_message = doc.get_payment_success_message()
