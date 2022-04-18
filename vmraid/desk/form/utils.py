# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import json

import vmraid
import vmraid.desk.form.load
import vmraid.desk.form.meta
from vmraid import _
from vmraid.core.doctype.file.file import extract_images_from_html
from vmraid.desk.form.document_follow import follow_document


@vmraid.whitelist()
def remove_attach():
	"""remove attachment"""
	fid = vmraid.form_dict.get("fid")
	file_name = vmraid.form_dict.get("file_name")
	vmraid.delete_doc("File", fid)


@vmraid.whitelist()
def add_comment(reference_doctype, reference_name, content, comment_email, comment_by):
	"""allow any logged user to post a comment"""
	doc = vmraid.get_doc(
		dict(
			doctype="Comment",
			reference_doctype=reference_doctype,
			reference_name=reference_name,
			comment_email=comment_email,
			comment_type="Comment",
			comment_by=comment_by,
		)
	)
	reference_doc = vmraid.get_doc(reference_doctype, reference_name)
	doc.content = extract_images_from_html(reference_doc, content, is_private=True)
	doc.insert(ignore_permissions=True)
	if vmraid.get_cached_value("User", vmraid.session.user, "follow_commented_documents"):
		follow_document(doc.reference_doctype, doc.reference_name, vmraid.session.user)
	return doc.as_dict()


@vmraid.whitelist()
def update_comment(name, content):
	"""allow only owner to update comment"""
	doc = vmraid.get_doc("Comment", name)

	if vmraid.session.user not in ["Administrator", doc.owner]:
		vmraid.throw(_("Comment can only be edited by the owner"), vmraid.PermissionError)

	doc.content = content
	doc.save(ignore_permissions=True)


@vmraid.whitelist()
def get_next(doctype, value, prev, filters=None, sort_order="desc", sort_field="modified"):

	prev = int(prev)
	if not filters:
		filters = []
	if isinstance(filters, str):
		filters = json.loads(filters)

	# # condition based on sort order
	condition = ">" if sort_order.lower() == "asc" else "<"

	# switch the condition
	if prev:
		sort_order = "asc" if sort_order.lower() == "desc" else "desc"
		condition = "<" if condition == ">" else ">"

	# # add condition for next or prev item
	filters.append([doctype, sort_field, condition, vmraid.get_value(doctype, value, sort_field)])

	res = vmraid.get_list(
		doctype,
		fields=["name"],
		filters=filters,
		order_by="`tab{0}`.{1}".format(doctype, sort_field) + " " + sort_order,
		limit_start=0,
		limit_page_length=1,
		as_list=True,
	)

	if not res:
		vmraid.msgprint(_("No further records"))
		return None
	else:
		return res[0][0]


def get_pdf_link(doctype, docname, print_format="Standard", no_letterhead=0):
	return "/api/method/vmraid.utils.print_format.download_pdf?doctype={doctype}&name={docname}&format={print_format}&no_letterhead={no_letterhead}".format(
		doctype=doctype, docname=docname, print_format=print_format, no_letterhead=no_letterhead
	)
