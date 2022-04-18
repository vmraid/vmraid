import vmraid
import json

def execute():
	if vmraid.db.exists("Social Login Key", "github"):
		vmraid.db.set_value("Social Login Key", "github", "auth_url_data",
			json.dumps({
				"scope": "user:email"
			})
		)
