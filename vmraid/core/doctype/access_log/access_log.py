# Copyright (c) 2021, VMRaid Technologies and contributors
# License: MIT. See LICENSE
from tenacity import retry, retry_if_exception_type, stop_after_attempt

import vmraid
from vmraid.model.document import Document
from vmraid.utils import cstr


class AccessLog(Document):
	pass


@vmraid.whitelist()
def make_access_log(
	doctype=None,
	document=None,
	method=None,
	file_type=None,
	report_name=None,
	filters=None,
	page=None,
	columns=None,
):
	_make_access_log(
		doctype,
		document,
		method,
		file_type,
		report_name,
		filters,
		page,
		columns,
	)


@vmraid.write_only()
@retry(stop=stop_after_attempt(3), retry=retry_if_exception_type(vmraid.DuplicateEntryError))
def _make_access_log(
	doctype=None,
	document=None,
	method=None,
	file_type=None,
	report_name=None,
	filters=None,
	page=None,
	columns=None,
):
	user = vmraid.session.user
	in_request = vmraid.request and vmraid.request.method == "GET"

	vmraid.get_doc(
		{
			"doctype": "Access Log",
			"user": user,
			"export_from": doctype,
			"reference_document": document,
			"file_type": file_type,
			"report_name": report_name,
			"page": page,
			"method": method,
			"filters": cstr(filters) or None,
			"columns": columns,
		}
	).db_insert()

	# `vmraid.db.commit` added because insert doesnt `commit` when called in GET requests like `printview`
	# dont commit in test mode. It must be tempting to put this block along with the in_request in the
	# whitelisted method...yeah, don't do it. That part would be executed possibly on a read only DB conn
	if not vmraid.flags.in_test or in_request:
		vmraid.db.commit()
