# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import json

import vmraid


@vmraid.whitelist()
def update_task(args, field_map):
	"""Updates Doc (called via gantt) based on passed `field_map`"""
	args = vmraid._dict(json.loads(args))
	field_map = vmraid._dict(json.loads(field_map))
	d = vmraid.get_doc(args.doctype, args.name)
	d.set(field_map.start, args.start)
	d.set(field_map.end, args.end)
	d.save()
