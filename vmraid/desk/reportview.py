# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

"""build query for doclistview and return results"""

import json
from io import StringIO

import vmraid
import vmraid.permissions
from vmraid import _
from vmraid.core.doctype.access_log.access_log import make_access_log
from vmraid.model import child_table_fields, default_fields, optional_fields
from vmraid.model.base_document import get_controller
from vmraid.model.db_query import DatabaseQuery
from vmraid.utils import add_user_info, cstr, format_duration


@vmraid.whitelist()
@vmraid.read_only()
def get():
	args = get_form_params()
	# If virtual doctype get data from controller het_list method
	if is_virtual_doctype(args.doctype):
		controller = get_controller(args.doctype)
		data = compress(controller(args.doctype).get_list(args))
	else:
		data = compress(execute(**args), args=args)
	return data


@vmraid.whitelist()
@vmraid.read_only()
def get_list():
	args = get_form_params()

	if is_virtual_doctype(args.doctype):
		controller = get_controller(args.doctype)
		data = controller(args.doctype).get_list(args)
	else:
		# uncompressed (refactored from vmraid.model.db_query.get_list)
		data = execute(**args)

	return data


@vmraid.whitelist()
@vmraid.read_only()
def get_count():
	args = get_form_params()

	if is_virtual_doctype(args.doctype):
		controller = get_controller(args.doctype)
		data = controller(args.doctype).get_count(args)
	else:
		distinct = "distinct " if args.distinct == "true" else ""
		args.fields = [f"count({distinct}`tab{args.doctype}`.name) as total_count"]
		data = execute(**args)[0].get("total_count")

	return data


def execute(doctype, *args, **kwargs):
	return DatabaseQuery(doctype).execute(*args, **kwargs)


def get_form_params():
	"""Stringify GET request parameters."""
	data = vmraid._dict(vmraid.local.form_dict)
	clean_params(data)
	validate_args(data)
	return data


def validate_args(data):
	parse_json(data)
	setup_group_by(data)

	validate_fields(data)
	if data.filters:
		validate_filters(data, data.filters)
	if data.or_filters:
		validate_filters(data, data.or_filters)

	data.strict = None

	return data


def validate_fields(data):
	wildcard = update_wildcard_field_param(data)

	for field in data.fields or []:
		fieldname = extract_fieldname(field)
		if is_standard(fieldname):
			continue

		meta, df = get_meta_and_docfield(fieldname, data)

		if not df:
			if wildcard:
				continue
			else:
				raise_invalid_field(fieldname)

		# remove the field from the query if the report hide flag is set and current view is Report
		if df.report_hide and data.view == "Report":
			data.fields.remove(field)
			continue

		if df.fieldname in [_df.fieldname for _df in meta.get_high_permlevel_fields()]:
			if df.get("permlevel") not in meta.get_permlevel_access(parenttype=data.doctype):
				data.fields.remove(field)


def validate_filters(data, filters):
	if isinstance(filters, list):
		# filters as list
		for condition in filters:
			if len(condition) == 3:
				# [fieldname, condition, value]
				fieldname = condition[0]
				if is_standard(fieldname):
					continue
				meta, df = get_meta_and_docfield(fieldname, data)
				if not df:
					raise_invalid_field(condition[0])
			else:
				# [doctype, fieldname, condition, value]
				fieldname = condition[1]
				if is_standard(fieldname):
					continue
				meta = vmraid.get_meta(condition[0])
				if not meta.get_field(fieldname):
					raise_invalid_field(fieldname)

	else:
		for fieldname in filters:
			if is_standard(fieldname):
				continue
			meta, df = get_meta_and_docfield(fieldname, data)
			if not df:
				raise_invalid_field(fieldname)


def setup_group_by(data):
	"""Add columns for aggregated values e.g. count(name)"""
	if data.group_by and data.aggregate_function:
		if data.aggregate_function.lower() not in ("count", "sum", "avg"):
			vmraid.throw(_("Invalid aggregate function"))

		if vmraid.db.has_column(data.aggregate_on_doctype, data.aggregate_on_field):
			data.fields.append(
				"{aggregate_function}(`tab{aggregate_on_doctype}`.`{aggregate_on_field}`) AS _aggregate_column".format(
					**data
				)
			)
			if data.aggregate_on_field:
				data.fields.append(f"`tab{data.aggregate_on_doctype}`.`{data.aggregate_on_field}`")
		else:
			raise_invalid_field(data.aggregate_on_field)

		data.pop("aggregate_on_doctype")
		data.pop("aggregate_on_field")
		data.pop("aggregate_function")


def raise_invalid_field(fieldname):
	vmraid.throw(_("Field not permitted in query") + ": {0}".format(fieldname), vmraid.DataError)


def is_standard(fieldname):
	if "." in fieldname:
		parenttype, fieldname = get_parenttype_and_fieldname(fieldname, None)
	return (
		fieldname in default_fields or fieldname in optional_fields or fieldname in child_table_fields
	)


def extract_fieldname(field):
	for text in (",", "/*", "#"):
		if text in field:
			raise_invalid_field(field)

	fieldname = field
	for sep in (" as ", " AS "):
		if sep in fieldname:
			fieldname = fieldname.split(sep)[0]

	# certain functions allowed, extract the fieldname from the function
	if fieldname.startswith("count(") or fieldname.startswith("sum(") or fieldname.startswith("avg("):
		if not fieldname.strip().endswith(")"):
			raise_invalid_field(field)
		fieldname = fieldname.split("(", 1)[1][:-1]

	return fieldname


def get_meta_and_docfield(fieldname, data):
	parenttype, fieldname = get_parenttype_and_fieldname(fieldname, data)
	meta = vmraid.get_meta(parenttype)
	df = meta.get_field(fieldname)
	return meta, df


def update_wildcard_field_param(data):
	if (isinstance(data.fields, str) and data.fields == "*") or (
		isinstance(data.fields, (list, tuple)) and len(data.fields) == 1 and data.fields[0] == "*"
	):
		data.fields = vmraid.db.get_table_columns(data.doctype)
		return True

	return False


def clean_params(data):
	for param in ("cmd", "data", "ignore_permissions", "view", "user", "csrf_token", "join"):
		data.pop(param, None)


def parse_json(data):
	if isinstance(data.get("filters"), str):
		data["filters"] = json.loads(data["filters"])
	if isinstance(data.get("or_filters"), str):
		data["or_filters"] = json.loads(data["or_filters"])
	if isinstance(data.get("fields"), str):
		data["fields"] = json.loads(data["fields"])
	if isinstance(data.get("docstatus"), str):
		data["docstatus"] = json.loads(data["docstatus"])
	if isinstance(data.get("save_user_settings"), str):
		data["save_user_settings"] = json.loads(data["save_user_settings"])
	else:
		data["save_user_settings"] = True


def get_parenttype_and_fieldname(field, data):
	if "." in field:
		parenttype, fieldname = field.split(".")[0][4:-1], field.split(".")[1].strip("`")
	else:
		parenttype = data.doctype
		fieldname = field.strip("`")

	return parenttype, fieldname


def compress(data, args=None):
	"""separate keys and values"""
	from vmraid.desk.query_report import add_total_row

	user_info = {}

	if not data:
		return data
	if args is None:
		args = {}
	values = []
	keys = list(data[0])
	for row in data:
		new_row = []
		for key in keys:
			new_row.append(row.get(key))
		values.append(new_row)

		# add user info for assignments (avatar)
		if row._assign:
			for user in json.loads(row._assign):
				add_user_info(user, user_info)

	if args.get("add_total_row"):
		meta = vmraid.get_meta(args.doctype)
		values = add_total_row(values, keys, meta)

	return {"keys": keys, "values": values, "user_info": user_info}


@vmraid.whitelist()
def save_report(name, doctype, report_settings):
	"""Save reports of type Report Builder from Report View"""

	if vmraid.db.exists("Report", name):
		report = vmraid.get_doc("Report", name)
		if report.is_standard == "Yes":
			vmraid.throw(_("Standard Reports cannot be edited"))

		if report.report_type != "Report Builder":
			vmraid.throw(_("Only reports of type Report Builder can be edited"))

		if report.owner != vmraid.session.user and not vmraid.has_permission("Report", "write"):
			vmraid.throw(_("Insufficient Permissions for editing Report"), vmraid.PermissionError)
	else:
		report = vmraid.new_doc("Report")
		report.report_name = name
		report.ref_doctype = doctype

	report.report_type = "Report Builder"
	report.json = report_settings
	report.save(ignore_permissions=True)
	vmraid.msgprint(
		_("Report {0} saved").format(vmraid.bold(report.name)),
		indicator="green",
		alert=True,
	)
	return report.name


@vmraid.whitelist()
def delete_report(name):
	"""Delete reports of type Report Builder from Report View"""

	report = vmraid.get_doc("Report", name)
	if report.is_standard == "Yes":
		vmraid.throw(_("Standard Reports cannot be deleted"))

	if report.report_type != "Report Builder":
		vmraid.throw(_("Only reports of type Report Builder can be deleted"))

	if report.owner != vmraid.session.user and not vmraid.has_permission("Report", "delete"):
		vmraid.throw(_("Insufficient Permissions for deleting Report"), vmraid.PermissionError)

	report.delete(ignore_permissions=True)
	vmraid.msgprint(
		_("Report {0} deleted").format(vmraid.bold(report.name)),
		indicator="green",
		alert=True,
	)


@vmraid.whitelist()
@vmraid.read_only()
def export_query():
	"""export from report builder"""
	title = vmraid.form_dict.title
	vmraid.form_dict.pop("title", None)

	form_params = get_form_params()
	form_params["limit_page_length"] = None
	form_params["as_list"] = True
	doctype = form_params.doctype
	add_totals_row = None
	file_format_type = form_params["file_format_type"]
	title = title or doctype

	del form_params["doctype"]
	del form_params["file_format_type"]

	if "add_totals_row" in form_params and form_params["add_totals_row"] == "1":
		add_totals_row = 1
		del form_params["add_totals_row"]

	vmraid.permissions.can_export(doctype, raise_exception=True)

	if "selected_items" in form_params:
		si = json.loads(vmraid.form_dict.get("selected_items"))
		form_params["filters"] = {"name": ("in", si)}
		del form_params["selected_items"]

	make_access_log(
		doctype=doctype,
		file_type=file_format_type,
		report_name=form_params.report_name,
		filters=form_params.filters,
	)

	db_query = DatabaseQuery(doctype)
	ret = db_query.execute(**form_params)

	if add_totals_row:
		ret = append_totals_row(ret)

	data = [[_("Sr")] + get_labels(db_query.fields, doctype)]
	for i, row in enumerate(ret):
		data.append([i + 1] + list(row))

	data = handle_duration_fieldtype_values(doctype, data, db_query.fields)

	if file_format_type == "CSV":

		# convert to csv
		import csv

		from vmraid.utils.xlsxutils import handle_html

		f = StringIO()
		writer = csv.writer(f)
		for r in data:
			# encode only unicode type strings and not int, floats etc.
			writer.writerow([handle_html(vmraid.as_unicode(v)) if isinstance(v, str) else v for v in r])

		f.seek(0)
		vmraid.response["result"] = cstr(f.read())
		vmraid.response["type"] = "csv"
		vmraid.response["doctype"] = title

	elif file_format_type == "Excel":

		from vmraid.utils.xlsxutils import make_xlsx

		xlsx_file = make_xlsx(data, doctype)

		vmraid.response["filename"] = title + ".xlsx"
		vmraid.response["filecontent"] = xlsx_file.getvalue()
		vmraid.response["type"] = "binary"


def append_totals_row(data):
	if not data:
		return data
	data = list(data)
	totals = []
	totals.extend([""] * len(data[0]))

	for row in data:
		for i in range(len(row)):
			if isinstance(row[i], (float, int)):
				totals[i] = (totals[i] or 0) + row[i]

	if not isinstance(totals[0], (int, float)):
		totals[0] = "Total"

	data.append(totals)

	return data


def get_labels(fields, doctype):
	"""get column labels based on column names"""
	labels = []
	for key in fields:
		key = key.split(" as ")[0]

		if key.startswith(("count(", "sum(", "avg(")):
			continue

		if "." in key:
			parenttype, fieldname = key.split(".")[0][4:-1], key.split(".")[1].strip("`")
		else:
			parenttype = doctype
			fieldname = fieldname.strip("`")

		if parenttype == doctype and fieldname == "name":
			label = _("ID", context="Label of name column in report")
		else:
			df = vmraid.get_meta(parenttype).get_field(fieldname)
			label = _(df.label if df else fieldname.title())
			if parenttype != doctype:
				# If the column is from a child table, append the child doctype.
				# For example, "Item Code (Sales Invoice Item)".
				label += f" ({ _(parenttype) })"

		labels.append(label)

	return labels


def handle_duration_fieldtype_values(doctype, data, fields):
	for field in fields:
		key = field.split(" as ")[0]

		if key.startswith(("count(", "sum(", "avg(")):
			continue

		if "." in key:
			parenttype, fieldname = key.split(".")[0][4:-1], key.split(".")[1].strip("`")
		else:
			parenttype = doctype
			fieldname = field.strip("`")

		df = vmraid.get_meta(parenttype).get_field(fieldname)

		if df and df.fieldtype == "Duration":
			index = fields.index(field) + 1
			for i in range(1, len(data)):
				val_in_seconds = data[i][index]
				if val_in_seconds:
					duration_val = format_duration(val_in_seconds, df.hide_days)
					data[i][index] = duration_val
	return data


@vmraid.whitelist()
def delete_items():
	"""delete selected items"""
	import json

	items = sorted(json.loads(vmraid.form_dict.get("items")), reverse=True)
	doctype = vmraid.form_dict.get("doctype")

	if len(items) > 10:
		vmraid.enqueue("vmraid.desk.reportview.delete_bulk", doctype=doctype, items=items)
	else:
		delete_bulk(doctype, items)


def delete_bulk(doctype, items):
	for i, d in enumerate(items):
		try:
			vmraid.delete_doc(doctype, d)
			if len(items) >= 5:
				vmraid.publish_realtime(
					"progress",
					dict(progress=[i + 1, len(items)], title=_("Deleting {0}").format(doctype), description=d),
					user=vmraid.session.user,
				)
			# Commit after successful deletion
			vmraid.db.commit()
		except Exception:
			# rollback if any record failed to delete
			# if not rollbacked, queries get committed on after_request method in app.py
			vmraid.db.rollback()


@vmraid.whitelist()
@vmraid.read_only()
def get_sidebar_stats(stats, doctype, filters=None):
	if filters is None:
		filters = []

	if is_virtual_doctype(doctype):
		controller = get_controller(doctype)
		args = {"stats": stats, "filters": filters}
		data = controller(doctype).get_stats(args)
	else:
		data = get_stats(stats, doctype, filters)

	return {"stats": data}


@vmraid.whitelist()
@vmraid.read_only()
def get_stats(stats, doctype, filters=None):
	"""get tag info"""
	import json

	if filters is None:
		filters = []
	tags = json.loads(stats)
	if filters:
		filters = json.loads(filters)
	stats = {}

	try:
		columns = vmraid.db.get_table_columns(doctype)
	except (vmraid.db.InternalError, vmraid.db.ProgrammingError):
		# raised when _user_tags column is added on the fly
		# raised if its a virtual doctype
		columns = []

	for tag in tags:
		if tag not in columns:
			continue
		try:
			tag_count = vmraid.get_list(
				doctype,
				fields=[tag, "count(*)"],
				filters=filters + [[tag, "!=", ""]],
				group_by=tag,
				as_list=True,
				distinct=1,
			)

			if tag == "_user_tags":
				stats[tag] = scrub_user_tags(tag_count)
				no_tag_count = vmraid.get_list(
					doctype,
					fields=[tag, "count(*)"],
					filters=filters + [[tag, "in", ("", ",")]],
					as_list=True,
					group_by=tag,
					order_by=tag,
				)

				no_tag_count = no_tag_count[0][1] if no_tag_count else 0

				stats[tag].append([_("No Tags"), no_tag_count])
			else:
				stats[tag] = tag_count

		except vmraid.db.SQLError:
			pass
		except vmraid.db.InternalError as e:
			# raised when _user_tags column is added on the fly
			pass

	return stats


@vmraid.whitelist()
def get_filter_dashboard_data(stats, doctype, filters=None):
	"""get tags info"""
	import json

	tags = json.loads(stats)
	filters = json.loads(filters or [])
	stats = {}

	columns = vmraid.db.get_table_columns(doctype)
	for tag in tags:
		if not tag["name"] in columns:
			continue
		tagcount = []
		if tag["type"] not in ["Date", "Datetime"]:
			tagcount = vmraid.get_list(
				doctype,
				fields=[tag["name"], "count(*)"],
				filters=filters + ["ifnull(`%s`,'')!=''" % tag["name"]],
				group_by=tag["name"],
				as_list=True,
			)

		if tag["type"] not in [
			"Check",
			"Select",
			"Date",
			"Datetime",
			"Int",
			"Float",
			"Currency",
			"Percent",
		] and tag["name"] not in ["docstatus"]:
			stats[tag["name"]] = list(tagcount)
			if stats[tag["name"]]:
				data = [
					"No Data",
					vmraid.get_list(
						doctype,
						fields=[tag["name"], "count(*)"],
						filters=filters + ["({0} = '' or {0} is null)".format(tag["name"])],
						as_list=True,
					)[0][1],
				]
				if data and data[1] != 0:

					stats[tag["name"]].append(data)
		else:
			stats[tag["name"]] = tagcount

	return stats


def scrub_user_tags(tagcount):
	"""rebuild tag list for tags"""
	rdict = {}
	tagdict = dict(tagcount)
	for t in tagdict:
		if not t:
			continue
		alltags = t.split(",")
		for tag in alltags:
			if tag:
				if tag not in rdict:
					rdict[tag] = 0

				rdict[tag] += tagdict[t]

	rlist = []
	for tag in rdict:
		rlist.append([tag, rdict[tag]])

	return rlist


# used in building query in queries.py
def get_match_cond(doctype, as_condition=True):
	cond = DatabaseQuery(doctype).build_match_conditions(as_condition=as_condition)
	if not as_condition:
		return cond

	return ((" and " + cond) if cond else "").replace("%", "%%")


def build_match_conditions(doctype, user=None, as_condition=True):
	match_conditions = DatabaseQuery(doctype, user=user).build_match_conditions(
		as_condition=as_condition
	)
	if as_condition:
		return match_conditions.replace("%", "%%")
	else:
		return match_conditions


def get_filters_cond(
	doctype, filters, conditions, ignore_permissions=None, with_match_conditions=False
):
	if isinstance(filters, str):
		filters = json.loads(filters)

	if filters:
		flt = filters
		if isinstance(filters, dict):
			filters = filters.items()
			flt = []
			for f in filters:
				if isinstance(f[1], str) and f[1][0] == "!":
					flt.append([doctype, f[0], "!=", f[1][1:]])
				elif isinstance(f[1], (list, tuple)) and f[1][0] in (
					">",
					"<",
					">=",
					"<=",
					"!=",
					"like",
					"not like",
					"in",
					"not in",
					"between",
				):

					flt.append([doctype, f[0], f[1][0], f[1][1]])
				else:
					flt.append([doctype, f[0], "=", f[1]])

		query = DatabaseQuery(doctype)
		query.filters = flt
		query.conditions = conditions

		if with_match_conditions:
			query.build_match_conditions()

		query.build_filter_conditions(flt, conditions, ignore_permissions)

		cond = " and " + " and ".join(query.conditions)
	else:
		cond = ""
	return cond


def is_virtual_doctype(doctype):
	return vmraid.db.get_value("DocType", doctype, "is_virtual")
