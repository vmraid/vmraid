# -*- coding: utf-8 -*-
# Copyright (c) 2020, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import json

import vmraid
from vmraid.model.document import Document
from vmraid.utils.safe_exec import read_sql, safe_exec


class SystemConsole(Document):
	def run(self):
		vmraid.only_for("System Manager")
		try:
			vmraid.local.debug_log = []
			if self.type == "Python":
				safe_exec(self.console)
				self.output = "\n".join(vmraid.debug_log)
			elif self.type == "SQL":
				self.output = vmraid.as_json(read_sql(self.console, as_dict=1))
		except:  # noqa: E722
			self.output = vmraid.get_traceback()

		if self.commit:
			vmraid.db.commit()
		else:
			vmraid.db.rollback()

		vmraid.get_doc(dict(doctype="Console Log", script=self.console, output=self.output)).insert()
		vmraid.db.commit()


@vmraid.whitelist()
def execute_code(doc):
	console = vmraid.get_doc(json.loads(doc))
	console.run()
	return console.as_dict()


@vmraid.whitelist()
def show_processlist():
	vmraid.only_for("System Manager")

	return vmraid.db.multisql(
		{
			"postgres": """
			SELECT pid AS "Id",
				query_start AS "Time",
				state AS "State",
				query AS "Info",
				wait_event AS "Progress"
			FROM pg_stat_activity""",
			"mariadb": "show full processlist",
		},
		as_dict=True,
	)
