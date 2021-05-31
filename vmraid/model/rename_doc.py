# Copyright (c) 2015, VMRaid Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

from __future__ import print_function, unicode_literals

import vmraid
from vmraid import _, bold
from vmraid.model.dynamic_links import get_dynamic_link_map
from vmraid.model.naming import validate_name
from vmraid.model.utils.user_settings import sync_user_settings, update_user_settings_data
from vmraid.utils import cint
from vmraid.utils.password import rename_password


@vmraid.whitelist()
def update_document_title(doctype, docname, title_field=None, old_title=None, new_title=None, new_name=None, merge=False):
	"""
		Update title from header in form view
	"""
	if docname and new_name and not docname == new_name:
		docname = rename_doc(doctype=doctype, old=docname, new=new_name, merge=merge)

	if old_title and new_title and not old_title == new_title:
		try:
			vmraid.db.set_value(doctype, docname, title_field, new_title)
			vmraid.msgprint(_('Saved'), alert=True, indicator='green')
		except Exception as e:
			if vmraid.db.is_duplicate_entry(e):
				vmraid.throw(
					_("{0} {1} already exists").format(doctype, vmraid.bold(docname)),
					title=_("Duplicate Name"),
					exc=vmraid.DuplicateEntryError
				)

	return docname

def rename_doc(doctype, old, new, force=False, merge=False, ignore_permissions=False, ignore_if_exists=False, show_alert=True):
	"""
		Renames a doc(dt, old) to doc(dt, new) and
		updates all linked fields of type "Link"
	"""
	if not vmraid.db.exists(doctype, old):
		return

	if ignore_if_exists and vmraid.db.exists(doctype, new):
		return

	if old==new:
		vmraid.msgprint(_('Please select a new name to rename'))
		return

	force = cint(force)
	merge = cint(merge)
	meta = vmraid.get_meta(doctype)

	# call before_rename
	old_doc = vmraid.get_doc(doctype, old)
	out = old_doc.run_method("before_rename", old, new, merge) or {}
	new = (out.get("new") or new) if isinstance(out, dict) else (out or new)
	new = validate_rename(doctype, new, meta, merge, force, ignore_permissions)

	if not merge:
		rename_parent_and_child(doctype, old, new, meta)
	else:
		update_assignments(old, new, doctype)

	# update link fields' values
	link_fields = get_link_fields(doctype)
	update_link_field_values(link_fields, old, new, doctype)

	rename_dynamic_links(doctype, old, new)

	# save the user settings in the db
	update_user_settings(old, new, link_fields)

	if doctype=='DocType':
		rename_doctype(doctype, old, new, force)

	update_attachments(doctype, old, new)

	rename_versions(doctype, old, new)

	# call after_rename
	new_doc = vmraid.get_doc(doctype, new)

	# copy any flags if required
	new_doc._local = getattr(old_doc, "_local", None)

	new_doc.run_method("after_rename", old, new, merge)

	if not merge:
		rename_password(doctype, old, new)

	# update user_permissions
	vmraid.db.sql("""UPDATE `tabDefaultValue` SET `defvalue`=%s WHERE `parenttype`='User Permission'
		AND `defkey`=%s AND `defvalue`=%s""", (new, doctype, old))

	if merge:
		new_doc.add_comment('Edit', _("merged {0} into {1}").format(vmraid.bold(old), vmraid.bold(new)))
	else:
		new_doc.add_comment('Edit', _("renamed from {0} to {1}").format(vmraid.bold(old), vmraid.bold(new)))

	if merge:
		vmraid.delete_doc(doctype, old)

	vmraid.clear_cache()
	vmraid.enqueue('vmraid.utils.global_search.rebuild_for_doctype', doctype=doctype)

	if show_alert:
		vmraid.msgprint(_('Document renamed from {0} to {1}').format(bold(old), bold(new)), alert=True, indicator='green')

	return new

def update_assignments(old, new, doctype):
	old_assignments = vmraid.parse_json(vmraid.db.get_value(doctype, old, '_assign')) or []
	new_assignments = vmraid.parse_json(vmraid.db.get_value(doctype, new, '_assign')) or []
	common_assignments = list(set(old_assignments).intersection(new_assignments))

	for user in common_assignments:
		# delete todos linked to old doc
		todos = vmraid.db.get_all('ToDo',
			{
				'owner': user,
				'reference_type': doctype,
				'reference_name': old,
			},
			['name', 'description']
		)

		for todo in todos:
			vmraid.delete_doc('ToDo', todo.name)

	unique_assignments = list(set(old_assignments + new_assignments))
	vmraid.db.set_value(doctype, new, '_assign', vmraid.as_json(unique_assignments, indent=0))

def update_user_settings(old, new, link_fields):
	'''
		Update the user settings of all the linked doctypes while renaming.
	'''

	# store the user settings data from the redis to db
	sync_user_settings()

	if not link_fields: return

	# find the user settings for the linked doctypes
	linked_doctypes = set([d.parent for d in link_fields if not d.issingle])
	user_settings_details = vmraid.db.sql('''SELECT `user`, `doctype`, `data`
			FROM `__UserSettings`
			WHERE `data` like %s
			AND `doctype` IN ('{doctypes}')'''.format(doctypes="', '".join(linked_doctypes)), (old), as_dict=1)

	# create the dict using the doctype name as key and values as list of the user settings
	from collections import defaultdict
	user_settings_dict = defaultdict(list)
	for user_setting in user_settings_details:
		user_settings_dict[user_setting.doctype].append(user_setting)

	# update the name in linked doctype whose user settings exists
	for fields in link_fields:
		user_settings = user_settings_dict.get(fields.parent)
		if user_settings:
			for user_setting in user_settings:
				update_user_settings_data(user_setting, "value", old, new, "docfield", fields.fieldname)
		else:
			continue


def update_attachments(doctype, old, new):
	try:
		if old != "File Data" and doctype != "DocType":
			vmraid.db.sql("""update `tabFile` set attached_to_name=%s
				where attached_to_name=%s and attached_to_doctype=%s""", (new, old, doctype))
	except vmraid.db.ProgrammingError as e:
		if not vmraid.db.is_column_missing(e):
			raise

def rename_versions(doctype, old, new):
	vmraid.db.sql("""UPDATE `tabVersion` SET `docname`=%s WHERE `ref_doctype`=%s AND `docname`=%s""",
		(new, doctype, old))

def rename_parent_and_child(doctype, old, new, meta):
	# rename the doc
	vmraid.db.sql("UPDATE `tab{0}` SET `name`={1} WHERE `name`={1}".format(doctype, '%s'), (new, old))
	update_autoname_field(doctype, new, meta)
	update_child_docs(old, new, meta)

def update_autoname_field(doctype, new, meta):
	# update the value of the autoname field on rename of the docname
	if meta.get('autoname'):
		field = meta.get('autoname').split(':')
		if field and field[0] == "field":
			vmraid.db.sql("UPDATE `tab{0}` SET `{1}`={2} WHERE `name`={2}".format(doctype, field[1], '%s'), (new, new))

def validate_rename(doctype, new, meta, merge, force, ignore_permissions):
	# using for update so that it gets locked and someone else cannot edit it while this rename is going on!
	exists = vmraid.db.sql("select name from `tab{doctype}` where name=%s for update".format(doctype=doctype), new)
	exists = exists[0][0] if exists else None

	if merge and not exists:
		vmraid.msgprint(_("{0} {1} does not exist, select a new target to merge").format(doctype, new), raise_exception=1)

	if exists and exists != new:
		# for fixing case, accents
		exists = None

	if (not merge) and exists:
		vmraid.msgprint(_("Another {0} with name {1} exists, select another name").format(doctype, new), raise_exception=1)

	if not (ignore_permissions or vmraid.permissions.has_permission(doctype, "write", raise_exception=False)):
		vmraid.msgprint(_("You need write permission to rename"), raise_exception=1)

	if not (force or ignore_permissions) and not meta.allow_rename:
		vmraid.msgprint(_("{0} not allowed to be renamed").format(_(doctype)), raise_exception=1)

	# validate naming like it's done in doc.py
	new = validate_name(doctype, new, merge=merge)

	return new

def rename_doctype(doctype, old, new, force=False):
	# change options for fieldtype Table, Table MultiSelect and Link
	fields_with_options = ("Link",) + vmraid.model.table_fields

	for fieldtype in fields_with_options:
		update_options_for_fieldtype(fieldtype, old, new)

	# change options where select options are hardcoded i.e. listed
	select_fields = get_select_fields(old, new)
	update_link_field_values(select_fields, old, new, doctype)
	update_select_field_values(old, new)

	# change parenttype for fieldtype Table
	update_parenttype_values(old, new)

def update_child_docs(old, new, meta):
	# update "parent"
	for df in meta.get_table_fields():
		vmraid.db.sql("update `tab%s` set parent=%s where parent=%s" \
			% (df.options, '%s', '%s'), (new, old))

def update_link_field_values(link_fields, old, new, doctype):
	for field in link_fields:
		if field['issingle']:
			try:
				single_doc = vmraid.get_doc(field['parent'])
				if single_doc.get(field['fieldname'])==old:
					single_doc.set(field['fieldname'], new)
					# update single docs using ORM rather then query
					# as single docs also sometimes sets defaults!
					single_doc.flags.ignore_mandatory = True
					single_doc.save(ignore_permissions=True)
			except ImportError:
				# fails in patches where the doctype has been renamed
				# or no longer exists
				pass
		else:
			parent = field['parent']
			docfield = field["fieldname"]

			# Handles the case where one of the link fields belongs to
			# the DocType being renamed.
			# Here this field could have the current DocType as its value too.

			# In this case while updating link field value, the field's parent
			# or the current DocType table name hasn't been renamed yet,
			# so consider it's old name.
			if parent == new and doctype == "DocType":
				parent = old

			vmraid.db.set_value(parent, {docfield: old}, docfield, new)

		# update cached link_fields as per new
		if doctype=='DocType' and field['parent'] == old:
			field['parent'] = new

def get_link_fields(doctype):
	# get link fields from tabDocField
	if not vmraid.flags.link_fields:
		vmraid.flags.link_fields = {}

	if not doctype in vmraid.flags.link_fields:
		link_fields = vmraid.db.sql("""\
			select parent, fieldname,
				(select issingle from tabDocType dt
				where dt.name = df.parent) as issingle
			from tabDocField df
			where
				df.options=%s and df.fieldtype='Link'""", (doctype,), as_dict=1)

		# get link fields from tabCustom Field
		custom_link_fields = vmraid.db.sql("""\
			select dt as parent, fieldname,
				(select issingle from tabDocType dt
				where dt.name = df.dt) as issingle
			from `tabCustom Field` df
			where
				df.options=%s and df.fieldtype='Link'""", (doctype,), as_dict=1)

		# add custom link fields list to link fields list
		link_fields += custom_link_fields

		# remove fields whose options have been changed using property setter
		property_setter_link_fields = vmraid.db.sql("""\
			select ps.doc_type as parent, ps.field_name as fieldname,
				(select issingle from tabDocType dt
				where dt.name = ps.doc_type) as issingle
			from `tabProperty Setter` ps
			where
				ps.property_type='options' and
				ps.field_name is not null and
				ps.value=%s""", (doctype,), as_dict=1)

		link_fields += property_setter_link_fields

		vmraid.flags.link_fields[doctype] = link_fields

	return vmraid.flags.link_fields[doctype]

def update_options_for_fieldtype(fieldtype, old, new):
	if vmraid.conf.developer_mode:
		for name in vmraid.get_all("DocField", filters={"options": old}, pluck="parent"):
			doctype = vmraid.get_doc("DocType", name)
			save = False
			for f in doctype.fields:
				if f.options == old:
					f.options = new
					save = True
			if save:
				doctype.save()
	else:
		vmraid.db.sql("""update `tabDocField` set options=%s
			where fieldtype=%s and options=%s""", (new, fieldtype, old))

	vmraid.db.sql("""update `tabCustom Field` set options=%s
		where fieldtype=%s and options=%s""", (new, fieldtype, old))

	vmraid.db.sql("""update `tabProperty Setter` set value=%s
		where property='options' and value=%s""", (new, old))

def get_select_fields(old, new):
	"""
		get select type fields where doctype's name is hardcoded as
		new line separated list
	"""
	# get link fields from tabDocField
	select_fields = vmraid.db.sql("""
		select parent, fieldname,
			(select issingle from tabDocType dt
			where dt.name = df.parent) as issingle
		from tabDocField df
		where
			df.parent != %s and df.fieldtype = 'Select' and
			df.options like {0} """.format(vmraid.db.escape('%' + old + '%')), (new,), as_dict=1)

	# get link fields from tabCustom Field
	custom_select_fields = vmraid.db.sql("""
		select dt as parent, fieldname,
			(select issingle from tabDocType dt
			where dt.name = df.dt) as issingle
		from `tabCustom Field` df
		where
			df.dt != %s and df.fieldtype = 'Select' and
			df.options like {0} """ .format(vmraid.db.escape('%' + old + '%')), (new,), as_dict=1)

	# add custom link fields list to link fields list
	select_fields += custom_select_fields

	# remove fields whose options have been changed using property setter
	property_setter_select_fields = vmraid.db.sql("""
		select ps.doc_type as parent, ps.field_name as fieldname,
			(select issingle from tabDocType dt
			where dt.name = ps.doc_type) as issingle
		from `tabProperty Setter` ps
		where
			ps.doc_type != %s and
			ps.property_type='options' and
			ps.field_name is not null and
			ps.value like {0} """.format(vmraid.db.escape('%' + old + '%')), (new,), as_dict=1)

	select_fields += property_setter_select_fields

	return select_fields

def update_select_field_values(old, new):
	vmraid.db.sql("""
		update `tabDocField` set options=replace(options, %s, %s)
		where
			parent != %s and fieldtype = 'Select' and
			(options like {0} or options like {1})"""
			.format(vmraid.db.escape('%' + '\n' + old + '%'), vmraid.db.escape('%' + old + '\n' + '%')), (old, new, new))

	vmraid.db.sql("""
		update `tabCustom Field` set options=replace(options, %s, %s)
		where
			dt != %s and fieldtype = 'Select' and
			(options like {0} or options like {1})"""
			.format(vmraid.db.escape('%' + '\n' + old + '%'), vmraid.db.escape('%' + old + '\n' + '%')), (old, new, new))

	vmraid.db.sql("""
		update `tabProperty Setter` set value=replace(value, %s, %s)
		where
			doc_type != %s and field_name is not null and
			property='options' and
			(value like {0} or value like {1})"""
			.format(vmraid.db.escape('%' + '\n' + old + '%'), vmraid.db.escape('%' + old + '\n' + '%')), (old, new, new))

def update_parenttype_values(old, new):
	child_doctypes = vmraid.db.get_all('DocField',
		fields=['options', 'fieldname'],
		filters={
			'parent': new,
			'fieldtype': ['in', vmraid.model.table_fields]
		}
	)

	custom_child_doctypes = vmraid.db.get_all('Custom Field',
		fields=['options', 'fieldname'],
		filters={
			'dt': new,
			'fieldtype': ['in', vmraid.model.table_fields]
		}
	)

	child_doctypes += custom_child_doctypes
	fields = [d['fieldname'] for d in child_doctypes]

	property_setter_child_doctypes = vmraid.get_all(
		"Property Setter",
		filters={
			"doc_type": new,
			"property": "options",
			"field_name": ("in", fields)
		},
		pluck="value"
	)

	child_doctypes = list(d['options'] for d in child_doctypes)
	child_doctypes += property_setter_child_doctypes

	for doctype in child_doctypes:
		vmraid.db.sql(f"update `tab{doctype}` set parenttype=%s where parenttype=%s", (new, old))

def rename_dynamic_links(doctype, old, new):
	for df in get_dynamic_link_map().get(doctype, []):
		# dynamic link in single, just one value to check
		if vmraid.get_meta(df.parent).issingle:
			refdoc = vmraid.db.get_singles_dict(df.parent)
			if refdoc.get(df.options)==doctype and refdoc.get(df.fieldname)==old:

				vmraid.db.sql("""update tabSingles set value=%s where
					field=%s and value=%s and doctype=%s""", (new, df.fieldname, old, df.parent))
		else:
			# because the table hasn't been renamed yet!
			parent = df.parent if df.parent != new else old
			vmraid.db.sql("""update `tab{parent}` set {fieldname}=%s
				where {options}=%s and {fieldname}=%s""".format(parent = parent,
					fieldname=df.fieldname, options=df.options), (new, doctype, old))

def bulk_rename(doctype, rows=None, via_console = False):
	"""Bulk rename documents

	:param doctype: DocType to be renamed
	:param rows: list of documents as `((oldname, newname), ..)`"""
	if not rows:
		vmraid.throw(_("Please select a valid csv file with data"))

	if not via_console:
		max_rows = 500
		if len(rows) > max_rows:
			vmraid.throw(_("Maximum {0} rows allowed").format(max_rows))

	rename_log = []
	for row in rows:
		# if row has some content
		if len(row) > 1 and row[0] and row[1]:
			try:
				if rename_doc(doctype, row[0], row[1]):
					msg = _("Successful: {0} to {1}").format(row[0], row[1])
					vmraid.db.commit()
				else:
					msg = _("Ignored: {0} to {1}").format(row[0], row[1])
			except Exception as e:
				msg = _("** Failed: {0} to {1}: {2}").format(row[0], row[1], repr(e))
				vmraid.db.rollback()

			if via_console:
				print(msg)
			else:
				rename_log.append(msg)

	vmraid.enqueue('vmraid.utils.global_search.rebuild_for_doctype', doctype=doctype)

	if not via_console:
		return rename_log

def update_linked_doctypes(doctype, docname, linked_to, value, ignore_doctypes=None):
	from vmraid.model.utils.rename_doc import update_linked_doctypes
	show_deprecation_warning("update_linked_doctypes")

	return update_linked_doctypes(
		doctype=doctype,
		docname=docname,
		linked_to=linked_to,
		value=value,
		ignore_doctypes=ignore_doctypes,
	)


def get_fetch_fields(doctype, linked_to, ignore_doctypes=None):
	from vmraid.model.utils.rename_doc import get_fetch_fields
	show_deprecation_warning("get_fetch_fields")

	return get_fetch_fields(
		doctype=doctype, linked_to=linked_to, ignore_doctypes=ignore_doctypes
	)

def show_deprecation_warning(funct):
	from click import secho
	message = (
		f"Function vmraid.model.rename_doc.{funct} has been deprecated and "
		"moved to the vmraid.model.utils.rename_doc"
	)
	secho(message, fg="yellow")
