# -*- coding: utf-8 -*-
# Copyright (c) 2019, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid.model.document import Document


class Milestone(Document):
	pass


def on_doctype_update():
	vmraid.db.add_index("Milestone", ["reference_type", "reference_name"])
