# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import json
from typing import Dict, List, Union
from urllib.parse import quote

import vmraid
import vmraid.defaults
import vmraid.desk.form.meta
import vmraid.share
import vmraid.utils
from vmraid import _, _dict
from vmraid.desk.form.document_follow import is_document_followed
from vmraid.model.utils.user_settings import get_user_settings
from vmraid.permissions import get_doc_permissions
from vmraid.utils.data import cstr


@vmraid.whitelist()
def getdoc(doctype, name, user=None):
	"""
	Loads a doclist for a given document. This method is called directly from the client.
	Requries "doctype", "name" as form variables.
	Will also call the "onload" method on the document.
	"""

	if not (doctype and name):
		raise Exception("doctype and name required!")

	if not name:
		name = doctype

	if not vmraid.db.exists(doctype, name):
		return []

	try:
		doc = vmraid.get_doc(doctype, name)
		run_onload(doc)

		if not doc.has_permission("read"):
			vmraid.flags.error_message = _("Insufficient Permission for {0}").format(
				vmraid.bold(doctype + " " + name)
			)
			raise vmraid.PermissionError(("read", doctype, name))

		doc.apply_fieldlevel_read_permissions()

		# add file list
		doc.add_viewed()
		get_docinfo(doc)

	except Exception:
		vmraid.errprint(vmraid.utils.get_traceback())
		raise

	doc.add_seen()
	set_link_titles(doc)
	if vmraid.response.docs is None:
		vmraid.local.response = _dict({"docs": []})
	vmraid.response.docs.append(doc)


@vmraid.whitelist()
def getdoctype(doctype, with_parent=False, cached_timestamp=None):
	"""load doctype"""

	docs = []
	parent_dt = None

	# with parent (called from report builder)
	if with_parent:
		parent_dt = vmraid.model.meta.get_parent_dt(doctype)
		if parent_dt:
			docs = get_meta_bundle(parent_dt)
			vmraid.response["parent_dt"] = parent_dt

	if not docs:
		docs = get_meta_bundle(doctype)

	vmraid.response["user_settings"] = get_user_settings(parent_dt or doctype)

	if cached_timestamp and docs[0].modified == cached_timestamp:
		return "use_cache"

	vmraid.response.docs.extend(docs)


def get_meta_bundle(doctype):
	bundle = [vmraid.desk.form.meta.get_meta(doctype)]
	for df in bundle[0].fields:
		if df.fieldtype in vmraid.model.table_fields:
			bundle.append(vmraid.desk.form.meta.get_meta(df.options, not vmraid.conf.developer_mode))
	return bundle


@vmraid.whitelist()
def get_docinfo(doc=None, doctype=None, name=None):
	if not doc:
		doc = vmraid.get_doc(doctype, name)
		if not doc.has_permission("read"):
			raise vmraid.PermissionError

	all_communications = _get_communications(doc.doctype, doc.name)
	automated_messages = [
		msg for msg in all_communications if msg["communication_type"] == "Automated Message"
	]
	communications_except_auto_messages = [
		msg for msg in all_communications if msg["communication_type"] != "Automated Message"
	]

	docinfo = vmraid._dict(user_info={})

	add_comments(doc, docinfo)

	docinfo.update(
		{
			"attachments": get_attachments(doc.doctype, doc.name),
			"communications": communications_except_auto_messages,
			"automated_messages": automated_messages,
			"total_comments": len(json.loads(doc.get("_comments") or "[]")),
			"versions": get_versions(doc),
			"assignments": get_assignments(doc.doctype, doc.name),
			"permissions": get_doc_permissions(doc),
			"shared": vmraid.share.get_users(doc.doctype, doc.name),
			"views": get_view_logs(doc.doctype, doc.name),
			"energy_point_logs": get_point_logs(doc.doctype, doc.name),
			"additional_timeline_content": get_additional_timeline_content(doc.doctype, doc.name),
			"milestones": get_milestones(doc.doctype, doc.name),
			"is_document_followed": is_document_followed(doc.doctype, doc.name, vmraid.session.user),
			"tags": get_tags(doc.doctype, doc.name),
			"document_email": get_document_email(doc.doctype, doc.name),
		}
	)

	update_user_info(docinfo)

	vmraid.response["docinfo"] = docinfo


def add_comments(doc, docinfo):
	# divide comments into separate lists
	docinfo.comments = []
	docinfo.shared = []
	docinfo.assignment_logs = []
	docinfo.attachment_logs = []
	docinfo.info_logs = []
	docinfo.like_logs = []
	docinfo.workflow_logs = []

	comments = vmraid.get_all(
		"Comment",
		fields=["name", "creation", "content", "owner", "comment_type"],
		filters={"reference_doctype": doc.doctype, "reference_name": doc.name},
	)

	for c in comments:
		if c.comment_type == "Comment":
			c.content = vmraid.utils.markdown(c.content)
			docinfo.comments.append(c)

		elif c.comment_type in ("Shared", "Unshared"):
			docinfo.shared.append(c)

		elif c.comment_type in ("Assignment Completed", "Assigned"):
			docinfo.assignment_logs.append(c)

		elif c.comment_type in ("Attachment", "Attachment Removed"):
			docinfo.attachment_logs.append(c)

		elif c.comment_type in ("Info", "Edit", "Label"):
			docinfo.info_logs.append(c)

		elif c.comment_type == "Like":
			docinfo.like_logs.append(c)

		elif c.comment_type == "Workflow":
			docinfo.workflow_logs.append(c)

		vmraid.utils.add_user_info(c.owner, docinfo.user_info)

	return comments


def get_milestones(doctype, name):
	return vmraid.db.get_all(
		"Milestone",
		fields=["creation", "owner", "track_field", "value"],
		filters=dict(reference_type=doctype, reference_name=name),
	)


def get_attachments(dt, dn):
	return vmraid.get_all(
		"File",
		fields=["name", "file_name", "file_url", "is_private"],
		filters={"attached_to_name": dn, "attached_to_doctype": dt},
	)


def get_versions(doc):
	return vmraid.get_all(
		"Version",
		filters=dict(ref_doctype=doc.doctype, docname=doc.name),
		fields=["name", "owner", "creation", "data"],
		limit=10,
		order_by="creation desc",
	)


@vmraid.whitelist()
def get_communications(doctype, name, start=0, limit=20):
	doc = vmraid.get_doc(doctype, name)
	if not doc.has_permission("read"):
		raise vmraid.PermissionError

	return _get_communications(doctype, name, start, limit)


def get_comments(
	doctype: str, name: str, comment_type: Union[str, List[str]] = "Comment"
) -> List[vmraid._dict]:
	if isinstance(comment_type, list):
		comment_types = comment_type

	elif comment_type == "share":
		comment_types = ["Shared", "Unshared"]

	elif comment_type == "assignment":
		comment_types = ["Assignment Completed", "Assigned"]

	elif comment_type == "attachment":
		comment_types = ["Attachment", "Attachment Removed"]

	else:
		comment_types = [comment_type]

	comments = vmraid.get_all(
		"Comment",
		fields=["name", "creation", "content", "owner", "comment_type"],
		filters={
			"reference_doctype": doctype,
			"reference_name": name,
			"comment_type": ["in", comment_types],
		},
	)

	# convert to markdown (legacy ?)
	for c in comments:
		if c.comment_type == "Comment":
			c.content = vmraid.utils.markdown(c.content)

	return comments


def get_point_logs(doctype, docname):
	return vmraid.db.get_all(
		"Energy Point Log",
		filters={"reference_doctype": doctype, "reference_name": docname, "type": ["!=", "Review"]},
		fields=["*"],
	)


def _get_communications(doctype, name, start=0, limit=20):
	communications = get_communication_data(doctype, name, start, limit)
	for c in communications:
		if c.communication_type == "Communication":
			c.attachments = json.dumps(
				vmraid.get_all(
					"File",
					fields=["file_url", "is_private"],
					filters={"attached_to_doctype": "Communication", "attached_to_name": c.name},
				)
			)

	return communications


def get_communication_data(
	doctype, name, start=0, limit=20, after=None, fields=None, group_by=None, as_dict=True
):
	"""Returns list of communications for a given document"""
	if not fields:
		fields = """
			C.name, C.communication_type, C.communication_medium,
			C.comment_type, C.communication_date, C.content,
			C.sender, C.sender_full_name, C.cc, C.bcc,
			C.creation AS creation, C.subject, C.delivery_status,
			C._liked_by, C.reference_doctype, C.reference_name,
			C.read_by_recipient, C.rating, C.recipients
		"""

	conditions = ""
	if after:
		# find after a particular date
		conditions += """
			AND C.creation > {0}
		""".format(
			after
		)

	if doctype == "User":
		conditions += """
			AND NOT (C.reference_doctype='User' AND C.communication_type='Communication')
		"""

	# communications linked to reference_doctype
	part1 = """
		SELECT {fields}
		FROM `tabCommunication` as C
		WHERE C.communication_type IN ('Communication', 'Feedback', 'Automated Message')
		AND (C.reference_doctype = %(doctype)s AND C.reference_name = %(name)s)
		{conditions}
	""".format(
		fields=fields, conditions=conditions
	)

	# communications linked in Timeline Links
	part2 = """
		SELECT {fields}
		FROM `tabCommunication` as C
		INNER JOIN `tabCommunication Link` ON C.name=`tabCommunication Link`.parent
		WHERE C.communication_type IN ('Communication', 'Feedback', 'Automated Message')
		AND `tabCommunication Link`.link_doctype = %(doctype)s AND `tabCommunication Link`.link_name = %(name)s
		{conditions}
	""".format(
		fields=fields, conditions=conditions
	)

	communications = vmraid.db.sql(
		"""
		SELECT *
		FROM (({part1}) UNION ({part2})) AS combined
		{group_by}
		ORDER BY creation DESC
		LIMIT %(limit)s
		OFFSET %(start)s
	""".format(
			part1=part1, part2=part2, group_by=(group_by or "")
		),
		dict(doctype=doctype, name=name, start=vmraid.utils.cint(start), limit=limit),
		as_dict=as_dict,
	)

	return communications


def get_assignments(dt, dn):
	return vmraid.get_all(
		"ToDo",
		fields=["name", "allocated_to as owner", "description", "status"],
		filters={
			"reference_type": dt,
			"reference_name": dn,
			"status": ("!=", "Cancelled"),
			"allocated_to": ("is", "set"),
		},
	)


@vmraid.whitelist()
def get_badge_info(doctypes, filters):
	filters = json.loads(filters)
	doctypes = json.loads(doctypes)
	filters["docstatus"] = ["!=", 2]
	out = {}
	for doctype in doctypes:
		out[doctype] = vmraid.db.get_value(doctype, filters, "count(*)")

	return out


def run_onload(doc):
	doc.set("__onload", vmraid._dict())
	doc.run_method("onload")


def get_view_logs(doctype, docname):
	"""get and return the latest view logs if available"""
	logs = []
	if hasattr(vmraid.get_meta(doctype), "track_views") and vmraid.get_meta(doctype).track_views:
		view_logs = vmraid.get_all(
			"View Log",
			filters={
				"reference_doctype": doctype,
				"reference_name": docname,
			},
			fields=["name", "creation", "owner"],
			order_by="creation desc",
		)

		if view_logs:
			logs = view_logs
	return logs


def get_tags(doctype, name):
	tags = [
		tag.tag
		for tag in vmraid.get_all(
			"Tag Link", filters={"document_type": doctype, "document_name": name}, fields=["tag"]
		)
	]

	return ",".join(tags)


def get_document_email(doctype, name):
	email = get_automatic_email_link()
	if not email:
		return None

	email = email.split("@")
	return "{0}+{1}+{2}@{3}".format(email[0], quote(doctype), quote(cstr(name)), email[1])


def get_automatic_email_link():
	return vmraid.db.get_value(
		"Email Account", {"enable_incoming": 1, "enable_automatic_linking": 1}, "email_id"
	)


def get_additional_timeline_content(doctype, docname):
	contents = []
	hooks = vmraid.get_hooks().get("additional_timeline_content", {})
	methods_for_all_doctype = hooks.get("*", [])
	methods_for_current_doctype = hooks.get(doctype, [])

	for method in methods_for_all_doctype + methods_for_current_doctype:
		contents.extend(vmraid.get_attr(method)(doctype, docname) or [])

	return contents


def set_link_titles(doc):
	link_titles = {}
	link_titles.update(get_title_values_for_link_and_dynamic_link_fields(doc))
	link_titles.update(get_title_values_for_table_and_multiselect_fields(doc))

	send_link_titles(link_titles)


def get_title_values_for_link_and_dynamic_link_fields(doc, link_fields=None):
	link_titles = {}

	if not link_fields:
		meta = vmraid.get_meta(doc.doctype)
		link_fields = meta.get_link_fields() + meta.get_dynamic_link_fields()

	for field in link_fields:
		if not doc.get(field.fieldname):
			continue

		doctype = field.options if field.fieldtype == "Link" else doc.get(field.options)

		meta = vmraid.get_meta(doctype)
		if not meta or not (meta.title_field and meta.show_title_field_in_link):
			continue

		link_title = vmraid.db.get_value(doctype, doc.get(field.fieldname), meta.title_field, cache=True)
		link_titles.update({doctype + "::" + doc.get(field.fieldname): link_title})

	return link_titles


def get_title_values_for_table_and_multiselect_fields(doc, table_fields=None):
	link_titles = {}

	if not table_fields:
		meta = vmraid.get_meta(doc.doctype)
		table_fields = meta.get_table_fields()

	for field in table_fields:
		if not doc.get(field.fieldname):
			continue

		for value in doc.get(field.fieldname):
			link_titles.update(get_title_values_for_link_and_dynamic_link_fields(value))

	return link_titles


def send_link_titles(link_titles):
	"""Append link titles dict in `vmraid.local.response`."""
	if "_link_titles" not in vmraid.local.response:
		vmraid.local.response["_link_titles"] = {}

	vmraid.local.response["_link_titles"].update(link_titles)


def update_user_info(docinfo):
	for d in docinfo.communications:
		vmraid.utils.add_user_info(d.sender, docinfo.user_info)

	for d in docinfo.shared:
		vmraid.utils.add_user_info(d.user, docinfo.user_info)

	for d in docinfo.assignments:
		vmraid.utils.add_user_info(d.owner, docinfo.user_info)

	for d in docinfo.views:
		vmraid.utils.add_user_info(d.owner, docinfo.user_info)


@vmraid.whitelist()
def get_user_info_for_viewers(users):
	user_info = {}
	for user in json.loads(users):
		vmraid.utils.add_user_info(user, user_info)

	return user_info
