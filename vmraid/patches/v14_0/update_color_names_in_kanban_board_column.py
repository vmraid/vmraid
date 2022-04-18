# Copyright (c) 2021, VMRaid and Contributors
# MIT License. See license.txt

from __future__ import unicode_literals

import vmraid


def execute():
	indicator_map = {
		"blue": "Blue",
		"orange": "Orange",
		"red": "Red",
		"green": "Green",
		"darkgrey": "Gray",
		"gray": "Gray",
		"purple": "Purple",
		"yellow": "Yellow",
		"lightblue": "Light Blue",
	}
	for d in vmraid.db.get_all("Kanban Board Column", fields=["name", "indicator"]):
		color_name = indicator_map.get(d.indicator, "Gray")
		vmraid.db.set_value("Kanban Board Column", d.name, "indicator", color_name)
