# -*- coding: utf-8 -*-
# Copyright (c) 2019, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import os

import vmraid
from vmraid import _
from vmraid.core.doctype.data_import.exporter import Exporter
from vmraid.core.doctype.data_import.importer import Importer
from vmraid.model.document import Document
from vmraid.modules.import_file import import_file_by_path
from vmraid.utils.background_jobs import enqueue
from vmraid.utils.csvutils import validate_google_sheets_url


class DataImport(Document):
	def validate(self):
		doc_before_save = self.get_doc_before_save()
		if (
			not (self.import_file or self.google_sheets_url)
			or (doc_before_save and doc_before_save.import_file != self.import_file)
			or (doc_before_save and doc_before_save.google_sheets_url != self.google_sheets_url)
		):
			self.template_options = ""
			self.template_warnings = ""

		self.validate_import_file()
		self.validate_google_sheets_url()
		self.set_payload_count()

	def validate_import_file(self):
		if self.import_file:
			# validate template
			self.get_importer()

	def validate_google_sheets_url(self):
		if not self.google_sheets_url:
			return
		validate_google_sheets_url(self.google_sheets_url)

	def set_payload_count(self):
		if self.import_file:
			i = self.get_importer()
			payloads = i.import_file.get_payloads_for_import()
			self.payload_count = len(payloads)

	@vmraid.whitelist()
	def get_preview_from_template(self, import_file=None, google_sheets_url=None):
		if import_file:
			self.import_file = import_file

		if google_sheets_url:
			self.google_sheets_url = google_sheets_url

		if not (self.import_file or self.google_sheets_url):
			return

		i = self.get_importer()
		return i.get_data_for_import_preview()

	def start_import(self):
		from vmraid.core.page.background_jobs.background_jobs import get_info
		from vmraid.utils.scheduler import is_scheduler_inactive

		if is_scheduler_inactive() and not vmraid.flags.in_test:
			vmraid.throw(_("Scheduler is inactive. Cannot import data."), title=_("Scheduler Inactive"))

		enqueued_jobs = [d.get("job_name") for d in get_info()]

		if self.name not in enqueued_jobs:
			enqueue(
				start_import,
				queue="default",
				timeout=10000,
				event="data_import",
				job_name=self.name,
				data_import=self.name,
				now=vmraid.conf.developer_mode or vmraid.flags.in_test,
			)
			return True

		return False

	def export_errored_rows(self):
		return self.get_importer().export_errored_rows()

	def download_import_log(self):
		return self.get_importer().export_import_log()

	def get_importer(self):
		return Importer(self.reference_doctype, data_import=self)


@vmraid.whitelist()
def get_preview_from_template(data_import, import_file=None, google_sheets_url=None):
	return vmraid.get_doc("Data Import", data_import).get_preview_from_template(
		import_file, google_sheets_url
	)


@vmraid.whitelist()
def form_start_import(data_import):
	return vmraid.get_doc("Data Import", data_import).start_import()


def start_import(data_import):
	"""This method runs in background job"""
	data_import = vmraid.get_doc("Data Import", data_import)
	try:
		i = Importer(data_import.reference_doctype, data_import=data_import)
		i.import_data()
	except Exception:
		vmraid.db.rollback()
		data_import.db_set("status", "Error")
		vmraid.log_error(title=data_import.name)
	finally:
		vmraid.flags.in_import = False

	vmraid.publish_realtime("data_import_refresh", {"data_import": data_import.name})


@vmraid.whitelist()
def download_template(
	doctype, export_fields=None, export_records=None, export_filters=None, file_type="CSV"
):
	"""
	Download template from Exporter
	        :param doctype: Document Type
	        :param export_fields=None: Fields to export as dict {'Sales Invoice': ['name', 'customer'], 'Sales Invoice Item': ['item_code']}
	        :param export_records=None: One of 'all', 'by_filter', 'blank_template'
	        :param export_filters: Filter dict
	        :param file_type: File type to export into
	"""

	export_fields = vmraid.parse_json(export_fields)
	export_filters = vmraid.parse_json(export_filters)
	export_data = export_records != "blank_template"

	e = Exporter(
		doctype,
		export_fields=export_fields,
		export_data=export_data,
		export_filters=export_filters,
		file_type=file_type,
		export_page_length=5 if export_records == "5_records" else None,
	)
	e.build_response()


@vmraid.whitelist()
def download_errored_template(data_import_name):
	data_import = vmraid.get_doc("Data Import", data_import_name)
	data_import.export_errored_rows()


@vmraid.whitelist()
def download_import_log(data_import_name):
	data_import = vmraid.get_doc("Data Import", data_import_name)
	data_import.download_import_log()


@vmraid.whitelist()
def get_import_status(data_import_name):
	import_status = {}

	logs = vmraid.get_all(
		"Data Import Log",
		fields=["count(*) as count", "success"],
		filters={"data_import": data_import_name},
		group_by="success",
	)

	total_payload_count = vmraid.db.get_value("Data Import", data_import_name, "payload_count")

	for log in logs:
		if log.get("success"):
			import_status["success"] = log.get("count")
		else:
			import_status["failed"] = log.get("count")

	import_status["total_records"] = total_payload_count

	return import_status


def import_file(doctype, file_path, import_type, submit_after_import=False, console=False):
	"""
	Import documents in from CSV or XLSX using data import.

	:param doctype: DocType to import
	:param file_path: Path to .csv, .xls, or .xlsx file to import
	:param import_type: One of "Insert" or "Update"
	:param submit_after_import: Whether to submit documents after import
	:param console: Set to true if this is to be used from command line. Will print errors or progress to stdout.
	"""

	data_import = vmraid.new_doc("Data Import")
	data_import.submit_after_import = submit_after_import
	data_import.import_type = (
		"Insert New Records" if import_type.lower() == "insert" else "Update Existing Records"
	)

	i = Importer(doctype=doctype, file_path=file_path, data_import=data_import, console=console)
	i.import_data()


def import_doc(path, pre_process=None):
	if os.path.isdir(path):
		files = [os.path.join(path, f) for f in os.listdir(path)]
	else:
		files = [path]

	for f in files:
		if f.endswith(".json"):
			vmraid.flags.mute_emails = True
			import_file_by_path(
				f, data_import=True, force=True, pre_process=pre_process, reset_permissions=True
			)
			vmraid.flags.mute_emails = False
			vmraid.db.commit()
		else:
			raise NotImplementedError("Only .json files can be imported")


def export_json(doctype, path, filters=None, or_filters=None, name=None, order_by="creation asc"):
	def post_process(out):
		# Note on Tree DocTypes:
		# The tree structure is maintained in the database via the fields "lft"
		# and "rgt". They are automatically set and kept up-to-date. Importing
		# them would destroy any existing tree structure. For this reason they
		# are not exported as well.
		del_keys = ("modified_by", "creation", "owner", "idx", "lft", "rgt")
		for doc in out:
			for key in del_keys:
				if key in doc:
					del doc[key]
			for k, v in doc.items():
				if isinstance(v, list):
					for child in v:
						for key in del_keys + ("docstatus", "doctype", "modified", "name"):
							if key in child:
								del child[key]

	out = []
	if name:
		out.append(vmraid.get_doc(doctype, name).as_dict())
	elif vmraid.db.get_value("DocType", doctype, "issingle"):
		out.append(vmraid.get_doc(doctype).as_dict())
	else:
		for doc in vmraid.get_all(
			doctype,
			fields=["name"],
			filters=filters,
			or_filters=or_filters,
			limit_page_length=0,
			order_by=order_by,
		):
			out.append(vmraid.get_doc(doctype, doc.name).as_dict())
	post_process(out)

	dirname = os.path.dirname(path)
	if not os.path.exists(dirname):
		path = os.path.join("..", path)

	with open(path, "w") as outfile:
		outfile.write(vmraid.as_json(out))


def export_csv(doctype, path):
	from vmraid.core.doctype.data_export.exporter import export_data

	with open(path, "wb") as csvfile:
		export_data(doctype=doctype, all_doctypes=True, template=True, with_data=True)
		csvfile.write(vmraid.response.result.encode("utf-8"))
