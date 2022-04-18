import sys
import unittest
from contextlib import contextmanager
from random import choice
from threading import Thread
from typing import Dict, Optional, Tuple
from unittest.mock import patch

import requests
from semantic_version import Version
from werkzeug.test import TestResponse

import vmraid
from vmraid.utils import get_site_url, get_test_client

try:
	_site = vmraid.local.site
except Exception:
	_site = None

authorization_token = None


@contextmanager
def suppress_stdout():
	"""Supress stdout for tests which expectedly make noise
	but that you don't need in tests"""
	sys.stdout = None
	try:
		yield
	finally:
		sys.stdout = sys.__stdout__


def make_request(
	target: str, args: Optional[Tuple] = None, kwargs: Optional[Dict] = None
) -> TestResponse:
	t = ThreadWithReturnValue(target=target, args=args, kwargs=kwargs)
	t.start()
	t.join()
	return t._return


def patch_request_header(key, *args, **kwargs):
	if key == "Authorization":
		return f"token {authorization_token}"


class ThreadWithReturnValue(Thread):
	def __init__(self, group=None, target=None, name=None, args=(), kwargs={}):
		Thread.__init__(self, group, target, name, args, kwargs)
		self._return = None

	def run(self):
		if self._target is not None:
			with patch("vmraid.app.get_site_name", return_value=_site):
				header_patch = patch("vmraid.get_request_header", new=patch_request_header)
				if authorization_token:
					header_patch.start()
				self._return = self._target(*self._args, **self._kwargs)
				if authorization_token:
					header_patch.stop()

	def join(self, *args):
		Thread.join(self, *args)
		return self._return


class VMRaidAPITestCase(unittest.TestCase):
	SITE = vmraid.local.site
	SITE_URL = get_site_url(SITE)
	RESOURCE_URL = f"{SITE_URL}/api/resource"
	TEST_CLIENT = get_test_client()

	@property
	def sid(self) -> str:
		if not getattr(self, "_sid", None):
			from vmraid.auth import CookieManager, LoginManager
			from vmraid.utils import set_request

			set_request(path="/")
			vmraid.local.cookie_manager = CookieManager()
			vmraid.local.login_manager = LoginManager()
			vmraid.local.login_manager.login_as("Administrator")
			self._sid = vmraid.session.sid

		return self._sid

	def get(self, path: str, params: Optional[Dict] = None, **kwargs) -> TestResponse:
		return make_request(target=self.TEST_CLIENT.get, args=(path,), kwargs={"data": params, **kwargs})

	def post(self, path, data, **kwargs) -> TestResponse:
		return make_request(target=self.TEST_CLIENT.post, args=(path,), kwargs={"data": data, **kwargs})

	def put(self, path, data, **kwargs) -> TestResponse:
		return make_request(target=self.TEST_CLIENT.put, args=(path,), kwargs={"data": data, **kwargs})

	def delete(self, path, **kwargs) -> TestResponse:
		return make_request(target=self.TEST_CLIENT.delete, args=(path,), kwargs=kwargs)


class TestResourceAPI(VMRaidAPITestCase):
	DOCTYPE = "ToDo"
	GENERATED_DOCUMENTS = []

	@classmethod
	def setUpClass(cls):
		for _ in range(10):
			doc = vmraid.get_doc({"doctype": "ToDo", "description": vmraid.mock("paragraph")}).insert()
			cls.GENERATED_DOCUMENTS.append(doc.name)
		vmraid.db.commit()

	@classmethod
	def tearDownClass(cls):
		for name in cls.GENERATED_DOCUMENTS:
			vmraid.delete_doc_if_exists(cls.DOCTYPE, name)
		vmraid.db.commit()

	def test_unauthorized_call(self):
		# test 1: fetch documents without auth
		response = requests.get(f"{self.RESOURCE_URL}/{self.DOCTYPE}")
		self.assertEqual(response.status_code, 403)

	def test_get_list(self):
		# test 2: fetch documents without params
		response = self.get(f"/api/resource/{self.DOCTYPE}", {"sid": self.sid})
		self.assertEqual(response.status_code, 200)
		self.assertIsInstance(response.json, dict)
		self.assertIn("data", response.json)

	def test_get_list_limit(self):
		# test 3: fetch data with limit
		response = self.get(f"/api/resource/{self.DOCTYPE}", {"sid": self.sid, "limit": 2})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.json["data"]), 2)

	def test_get_list_dict(self):
		# test 4: fetch response as (not) dict
		response = self.get(f"/api/resource/{self.DOCTYPE}", {"sid": self.sid, "as_dict": True})
		json = vmraid._dict(response.json)
		self.assertEqual(response.status_code, 200)
		self.assertIsInstance(json.data, list)
		self.assertIsInstance(json.data[0], dict)

		response = self.get(f"/api/resource/{self.DOCTYPE}", {"sid": self.sid, "as_dict": False})
		json = vmraid._dict(response.json)
		self.assertEqual(response.status_code, 200)
		self.assertIsInstance(json.data, list)
		self.assertIsInstance(json.data[0], list)

	def test_get_list_debug(self):
		# test 5: fetch response with debug
		response = self.get(f"/api/resource/{self.DOCTYPE}", {"sid": self.sid, "debug": True})
		self.assertEqual(response.status_code, 200)
		self.assertIn("exc", response.json)
		self.assertIsInstance(response.json["exc"], str)
		self.assertIsInstance(eval(response.json["exc"]), list)

	def test_get_list_fields(self):
		# test 6: fetch response with fields
		response = self.get(
			f"/api/resource/{self.DOCTYPE}", {"sid": self.sid, "fields": '["description"]'}
		)
		self.assertEqual(response.status_code, 200)
		json = vmraid._dict(response.json)
		self.assertIn("description", json.data[0])

	def test_create_document(self):
		# test 7: POST method on /api/resource to create doc
		data = {"description": vmraid.mock("paragraph"), "sid": self.sid}
		response = self.post(f"/api/resource/{self.DOCTYPE}", data)
		self.assertEqual(response.status_code, 200)
		docname = response.json["data"]["name"]
		self.assertIsInstance(docname, str)
		self.GENERATED_DOCUMENTS.append(docname)

	def test_update_document(self):
		# test 8: PUT method on /api/resource to update doc
		generated_desc = vmraid.mock("paragraph")
		data = {"description": generated_desc, "sid": self.sid}
		random_doc = choice(self.GENERATED_DOCUMENTS)
		desc_before_update = vmraid.db.get_value(self.DOCTYPE, random_doc, "description")

		response = self.put(f"/api/resource/{self.DOCTYPE}/{random_doc}", data=data)
		self.assertEqual(response.status_code, 200)
		self.assertNotEqual(response.json["data"]["description"], desc_before_update)
		self.assertEqual(response.json["data"]["description"], generated_desc)

	def test_delete_document(self):
		# test 9: DELETE method on /api/resource
		doc_to_delete = choice(self.GENERATED_DOCUMENTS)
		response = self.delete(f"/api/resource/{self.DOCTYPE}/{doc_to_delete}")
		self.assertEqual(response.status_code, 202)
		self.assertDictEqual(response.json, {"message": "ok"})
		self.GENERATED_DOCUMENTS.remove(doc_to_delete)

		non_existent_doc = vmraid.generate_hash(length=12)
		with suppress_stdout():
			response = self.delete(f"/api/resource/{self.DOCTYPE}/{non_existent_doc}")
		self.assertEqual(response.status_code, 404)
		self.assertDictEqual(response.json, {})

	def test_run_doc_method(self):
		# test 10: Run whitelisted method on doc via /api/resource
		# status_code is 403 if no other tests are run before this - it's not logged in
		self.post("/api/resource/Website Theme/Standard", {"run_method": "get_apps"})
		response = self.get("/api/resource/Website Theme/Standard", {"run_method": "get_apps"})
		self.assertIn(response.status_code, (403, 200))

		if response.status_code == 403:
			self.assertTrue(
				set(response.json.keys()) == {"exc_type", "exception", "exc", "_server_messages"}
			)
			self.assertEqual(response.json.get("exc_type"), "PermissionError")
			self.assertEqual(
				response.json.get("exception"), "vmraid.exceptions.PermissionError: Not permitted"
			)
			self.assertIsInstance(response.json.get("exc"), str)

		elif response.status_code == 200:
			data = response.json.get("data")
			self.assertIsInstance(data, list)
			self.assertIsInstance(data[0], dict)


class TestMethodAPI(VMRaidAPITestCase):
	METHOD_PATH = "/api/method"

	def setUp(self):
		if self._testMethodName == "test_auth_cycle":
			from vmraid.core.doctype.user.user import generate_keys

			generate_keys("Administrator")
			vmraid.db.commit()

	def test_version(self):
		# test 1: test for /api/method/version
		response = self.get(f"{self.METHOD_PATH}/version")
		json = vmraid._dict(response.json)

		self.assertEqual(response.status_code, 200)
		self.assertIsInstance(json, dict)
		self.assertIsInstance(json.message, str)
		self.assertEqual(Version(json.message), Version(vmraid.__version__))

	def test_ping(self):
		# test 2: test for /api/method/ping
		response = self.get(f"{self.METHOD_PATH}/ping")
		self.assertEqual(response.status_code, 200)
		self.assertIsInstance(response.json, dict)
		self.assertEqual(response.json["message"], "pong")

	def test_get_user_info(self):
		# test 3: test for /api/method/vmraid.realtime.get_user_info
		response = self.get(f"{self.METHOD_PATH}/vmraid.realtime.get_user_info")
		self.assertEqual(response.status_code, 200)
		self.assertIsInstance(response.json, dict)
		self.assertIn(response.json.get("message").get("user"), ("Administrator", "Guest"))

	def test_auth_cycle(self):
		# test 4: Pass authorization token in request
		global authorization_token
		user = vmraid.get_doc("User", "Administrator")
		api_key, api_secret = user.api_key, user.get_password("api_secret")
		authorization_token = f"{api_key}:{api_secret}"
		response = self.get("/api/method/vmraid.auth.get_logged_user")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json["message"], "Administrator")

		authorization_token = None
