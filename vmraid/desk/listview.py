# Copyright (c) 2019, VMRaid and Contributors
# License: MIT. See LICENSE
import vmraid


@vmraid.whitelist()
def get_list_settings(doctype):
	try:
		return vmraid.get_cached_doc("List View Settings", doctype)
	except vmraid.DoesNotExistError:
		vmraid.clear_messages()


@vmraid.whitelist()
def set_list_settings(doctype, values):
	try:
		doc = vmraid.get_doc("List View Settings", doctype)
	except vmraid.DoesNotExistError:
		doc = vmraid.new_doc("List View Settings")
		doc.name = doctype
		vmraid.clear_messages()
	doc.update(vmraid.parse_json(values))
	doc.save()


@vmraid.whitelist()
def get_group_by_count(doctype, current_filters, field):
	current_filters = vmraid.parse_json(current_filters)
	subquery_condition = ""

	subquery = vmraid.get_all(doctype, filters=current_filters, run=False)
	if field == "assigned_to":
		subquery_condition = " and `tabToDo`.reference_name in ({subquery})".format(subquery=subquery)
		return vmraid.db.sql(
			"""select `tabToDo`.allocated_to as name, count(*) as count
			from
				`tabToDo`, `tabUser`
			where
				`tabToDo`.status!='Cancelled' and
				`tabToDo`.allocated_to = `tabUser`.name and
				`tabUser`.user_type = 'System User'
				{subquery_condition}
			group by
				`tabToDo`.allocated_to
			order by
				count desc
			limit 50""".format(
				subquery_condition=subquery_condition
			),
			as_dict=True,
		)
	else:
		return vmraid.db.get_list(
			doctype,
			filters=current_filters,
			group_by="`tab{0}`.{1}".format(doctype, field),
			fields=["count(*) as count", "`{}` as name".format(field)],
			order_by="count desc",
			limit=50,
		)
