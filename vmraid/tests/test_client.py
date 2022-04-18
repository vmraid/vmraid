# Copyright (c) 2015, VMRaid and Contributors

import unittest

import vmraid


class TestClient(unittest.TestCase):
	def test_set_value(self):
		todo = vmraid.get_doc(dict(doctype="ToDo", description="test")).insert()
		vmraid.set_value("ToDo", todo.name, "description", "test 1")
		self.assertEqual(vmraid.get_value("ToDo", todo.name, "description"), "test 1")

		vmraid.set_value("ToDo", todo.name, {"description": "test 2"})
		self.assertEqual(vmraid.get_value("ToDo", todo.name, "description"), "test 2")

	def test_delete(self):
		from vmraid.client import delete

		todo = vmraid.get_doc(dict(doctype="ToDo", description="description")).insert()
		delete("ToDo", todo.name)

		self.assertFalse(vmraid.db.exists("ToDo", todo.name))
		self.assertRaises(vmraid.DoesNotExistError, delete, "ToDo", todo.name)

	def test_http_valid_method_access(self):
		from vmraid.client import delete
		from vmraid.handler import execute_cmd

		vmraid.set_user("Administrator")

		vmraid.local.request = vmraid._dict()
		vmraid.local.request.method = "POST"

		vmraid.local.form_dict = vmraid._dict(
			{"doc": dict(doctype="ToDo", description="Valid http method"), "cmd": "vmraid.client.save"}
		)
		todo = execute_cmd("vmraid.client.save")

		self.assertEqual(todo.get("description"), "Valid http method")

		delete("ToDo", todo.name)

	def test_http_invalid_method_access(self):
		from vmraid.handler import execute_cmd

		vmraid.set_user("Administrator")

		vmraid.local.request = vmraid._dict()
		vmraid.local.request.method = "GET"

		vmraid.local.form_dict = vmraid._dict(
			{"doc": dict(doctype="ToDo", description="Invalid http method"), "cmd": "vmraid.client.save"}
		)

		self.assertRaises(vmraid.PermissionError, execute_cmd, "vmraid.client.save")

	def test_run_doc_method(self):
		from vmraid.handler import execute_cmd

		if not vmraid.db.exists("Report", "Test Run Doc Method"):
			report = vmraid.get_doc(
				{
					"doctype": "Report",
					"ref_doctype": "User",
					"report_name": "Test Run Doc Method",
					"report_type": "Query Report",
					"is_standard": "No",
					"roles": [{"role": "System Manager"}],
				}
			).insert()
		else:
			report = vmraid.get_doc("Report", "Test Run Doc Method")

		vmraid.local.request = vmraid._dict()
		vmraid.local.request.method = "GET"

		# Whitelisted, works as expected
		vmraid.local.form_dict = vmraid._dict(
			{
				"dt": report.doctype,
				"dn": report.name,
				"method": "toggle_disable",
				"cmd": "run_doc_method",
				"args": 0,
			}
		)

		execute_cmd(vmraid.local.form_dict.cmd)

		# Not whitelisted, throws permission error
		vmraid.local.form_dict = vmraid._dict(
			{
				"dt": report.doctype,
				"dn": report.name,
				"method": "create_report_py",
				"cmd": "run_doc_method",
				"args": 0,
			}
		)

		self.assertRaises(vmraid.PermissionError, execute_cmd, vmraid.local.form_dict.cmd)

	def test_array_values_in_request_args(self):
		import requests

		from vmraid.auth import CookieManager, LoginManager

		vmraid.utils.set_request(path="/")
		vmraid.local.cookie_manager = CookieManager()
		vmraid.local.login_manager = LoginManager()
		vmraid.local.login_manager.login_as("Administrator")
		params = {
			"doctype": "DocType",
			"fields": ["name", "modified"],
			"sid": vmraid.session.sid,
		}
		headers = {
			"accept": "application/json",
			"content-type": "application/json",
		}
		url = (
			f"http://{vmraid.local.site}:{vmraid.conf.webserver_port}/api/method/vmraid.client.get_list"
		)
		res = requests.post(url, json=params, headers=headers)
		self.assertEqual(res.status_code, 200)
		data = res.json()
		first_item = data["message"][0]
		self.assertTrue("name" in first_item)
		self.assertTrue("modified" in first_item)
		vmraid.local.login_manager.logout()

	def test_client_get(self):
		from vmraid.client import get

		todo = vmraid.get_doc(doctype="ToDo", description="test").insert()
		filters = {"name": todo.name}
		filters_json = vmraid.as_json(filters)

		self.assertEqual(get("ToDo", filters=filters).description, "test")
		self.assertEqual(get("ToDo", filters=filters_json).description, "test")

		todo.delete()
