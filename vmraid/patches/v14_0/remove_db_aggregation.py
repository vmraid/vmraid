import re

import vmraid
from vmraid.query_builder import DocType


def execute():
	"""Replace temporarily available Database Aggregate APIs on vmraid (develop)

	APIs changed:
	        * vmraid.db.max => vmraid.qb.max
	        * vmraid.db.min => vmraid.qb.min
	        * vmraid.db.sum => vmraid.qb.sum
	        * vmraid.db.avg => vmraid.qb.avg
	"""
	ServerScript = DocType("Server Script")
	server_scripts = (
		vmraid.qb.from_(ServerScript)
		.where(
			ServerScript.script.like("%vmraid.db.max(%")
			| ServerScript.script.like("%vmraid.db.min(%")
			| ServerScript.script.like("%vmraid.db.sum(%")
			| ServerScript.script.like("%vmraid.db.avg(%")
		)
		.select("name", "script")
		.run(as_dict=True)
	)

	for server_script in server_scripts:
		name, script = server_script["name"], server_script["script"]

		for agg in ["avg", "max", "min", "sum"]:
			script = re.sub(f"vmraid.db.{agg}\(", f"vmraid.qb.{agg}(", script)

		vmraid.db.update("Server Script", name, "script", script)
