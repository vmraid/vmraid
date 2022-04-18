# Copyright (c) 2022, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid.deferred_insert import deferred_insert as _deferred_insert
from vmraid.model.document import Document
from vmraid.query_builder import DocType
from vmraid.query_builder.functions import Count


class RouteHistory(Document):
	pass


def flush_old_route_records():
	"""Deletes all route records except last 500 records per user"""
	records_to_keep_limit = 500
	RouteHistory = DocType("Route History")

	users = (
		vmraid.qb.from_(RouteHistory)
		.select(RouteHistory.user)
		.groupby(RouteHistory.user)
		.having(Count(RouteHistory.name) > records_to_keep_limit)
	).run(pluck=True)

	for user in users:
		last_record_to_keep = vmraid.get_all(
			"Route History",
			filters={"user": user},
			limit_start=500,
			fields=["modified"],
			order_by="modified desc",
			limit=1,
		)

		vmraid.db.delete(
			"Route History",
			{"modified": ("<=", last_record_to_keep[0].modified), "user": user},
		)


@vmraid.whitelist()
def deferred_insert(routes):
	routes = [
		{
			"user": vmraid.session.user,
			"route": route.get("route"),
			"creation": route.get("creation"),
		}
		for route in vmraid.parse_json(routes)
	]

	_deferred_insert("Route History", routes)


@vmraid.whitelist()
def frequently_visited_links():
	return vmraid.get_all(
		"Route History",
		fields=["route", "count(name) as count"],
		filters={"user": vmraid.session.user},
		group_by="route",
		order_by="count desc",
		limit=5,
	)
