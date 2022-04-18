# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
import json
import unittest

import vmraid
from vmraid.website.doctype.web_form.web_form import accept
from vmraid.website.serve import get_response_content

test_dependencies = ["Web Form"]


class TestWebForm(unittest.TestCase):
	def setUp(self):
		vmraid.conf.disable_website_cache = True
		vmraid.local.path = None

	def tearDown(self):
		vmraid.conf.disable_website_cache = False
		vmraid.local.path = None
		vmraid.local.request_ip = None
		vmraid.form_dict.web_form = None
		vmraid.form_dict.data = None
		vmraid.form_dict.docname = None

	def test_accept(self):
		vmraid.set_user("Administrator")

		doc = {
			"doctype": "Event",
			"subject": "_Test Event Web Form",
			"description": "_Test Event Description",
			"starts_on": "2014-09-09",
		}

		vmraid.form_dict.web_form = "manage-events"
		vmraid.form_dict.data = json.dumps(doc)
		vmraid.local.request_ip = "127.0.0.1"

		accept(web_form="manage-events", data=json.dumps(doc))

		self.event_name = vmraid.db.get_value("Event", {"subject": "_Test Event Web Form"})
		self.assertTrue(self.event_name)

	def test_edit(self):
		self.test_accept()

		doc = {
			"doctype": "Event",
			"subject": "_Test Event Web Form",
			"description": "_Test Event Description 1",
			"starts_on": "2014-09-09",
			"name": self.event_name,
		}

		self.assertNotEqual(
			vmraid.db.get_value("Event", self.event_name, "description"), doc.get("description")
		)

		vmraid.form_dict.web_form = "manage-events"
		vmraid.form_dict.docname = self.event_name
		vmraid.form_dict.data = json.dumps(doc)

		accept(web_form="manage-events", docname=self.event_name, data=json.dumps(doc))

		self.assertEqual(
			vmraid.db.get_value("Event", self.event_name, "description"), doc.get("description")
		)

	def test_webform_render(self):
		content = get_response_content("request-data")
		self.assertIn("<h3>Request Data</h3>", content)
		self.assertIn('data-doctype="Web Form"', content)
		self.assertIn('data-path="request-data"', content)
		self.assertIn('source-type="Generator"', content)
