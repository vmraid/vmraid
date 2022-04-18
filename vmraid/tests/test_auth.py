# Copyright (c) 2021, VMRaid and Contributors
# License: MIT. See LICENSE
import time
import unittest

import vmraid
import vmraid.utils
from vmraid.auth import LoginAttemptTracker
from vmraid.vmraidclient import AuthError, VMRaidClient


def add_user(email, password, username=None, mobile_no=None):
	first_name = email.split("@", 1)[0]
	user = vmraid.get_doc(
		dict(doctype="User", email=email, first_name=first_name, username=username, mobile_no=mobile_no)
	).insert()
	user.new_password = password
	user.add_roles("System Manager")
	vmraid.db.commit()


class TestAuth(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.HOST_NAME = vmraid.get_site_config().host_name or vmraid.utils.get_site_url(
			vmraid.local.site
		)
		cls.test_user_email = "test_auth@test.com"
		cls.test_user_name = "test_auth_user"
		cls.test_user_mobile = "+911234567890"
		cls.test_user_password = "pwd_012"

		cls.tearDownClass()
		add_user(
			email=cls.test_user_email,
			password=cls.test_user_password,
			username=cls.test_user_name,
			mobile_no=cls.test_user_mobile,
		)

	@classmethod
	def tearDownClass(cls):
		vmraid.delete_doc("User", cls.test_user_email, force=True)

	def set_system_settings(self, k, v):
		vmraid.db.set_value("System Settings", "System Settings", k, v)
		vmraid.clear_cache()
		vmraid.db.commit()

	def test_allow_login_using_mobile(self):
		self.set_system_settings("allow_login_using_mobile_number", 1)
		self.set_system_settings("allow_login_using_user_name", 0)

		# Login by both email and mobile should work
		VMRaidClient(self.HOST_NAME, self.test_user_mobile, self.test_user_password)
		VMRaidClient(self.HOST_NAME, self.test_user_email, self.test_user_password)

		# login by username should fail
		with self.assertRaises(AuthError):
			VMRaidClient(self.HOST_NAME, self.test_user_name, self.test_user_password)

	def test_allow_login_using_only_email(self):
		self.set_system_settings("allow_login_using_mobile_number", 0)
		self.set_system_settings("allow_login_using_user_name", 0)

		# Login by mobile number should fail
		with self.assertRaises(AuthError):
			VMRaidClient(self.HOST_NAME, self.test_user_mobile, self.test_user_password)

		# login by username should fail
		with self.assertRaises(AuthError):
			VMRaidClient(self.HOST_NAME, self.test_user_name, self.test_user_password)

		# Login by email should work
		VMRaidClient(self.HOST_NAME, self.test_user_email, self.test_user_password)

	def test_allow_login_using_username(self):
		self.set_system_settings("allow_login_using_mobile_number", 0)
		self.set_system_settings("allow_login_using_user_name", 1)

		# Mobile login should fail
		with self.assertRaises(AuthError):
			VMRaidClient(self.HOST_NAME, self.test_user_mobile, self.test_user_password)

		# Both email and username logins should work
		VMRaidClient(self.HOST_NAME, self.test_user_email, self.test_user_password)
		VMRaidClient(self.HOST_NAME, self.test_user_name, self.test_user_password)

	def test_allow_login_using_username_and_mobile(self):
		self.set_system_settings("allow_login_using_mobile_number", 1)
		self.set_system_settings("allow_login_using_user_name", 1)

		# Both email and username and mobile logins should work
		VMRaidClient(self.HOST_NAME, self.test_user_mobile, self.test_user_password)
		VMRaidClient(self.HOST_NAME, self.test_user_email, self.test_user_password)
		VMRaidClient(self.HOST_NAME, self.test_user_name, self.test_user_password)

	def test_deny_multiple_login(self):
		self.set_system_settings("deny_multiple_sessions", 1)

		first_login = VMRaidClient(self.HOST_NAME, self.test_user_email, self.test_user_password)
		first_login.get_list("ToDo")

		second_login = VMRaidClient(self.HOST_NAME, self.test_user_email, self.test_user_password)
		second_login.get_list("ToDo")
		with self.assertRaises(Exception):
			first_login.get_list("ToDo")

		third_login = VMRaidClient(self.HOST_NAME, self.test_user_email, self.test_user_password)
		with self.assertRaises(Exception):
			first_login.get_list("ToDo")
		with self.assertRaises(Exception):
			second_login.get_list("ToDo")
		third_login.get_list("ToDo")


class TestLoginAttemptTracker(unittest.TestCase):
	def test_account_lock(self):
		"""Make sure that account locks after `n consecutive failures"""
		tracker = LoginAttemptTracker(
			user_name="tester", max_consecutive_login_attempts=3, lock_interval=60
		)
		# Clear the cache by setting attempt as success
		tracker.add_success_attempt()

		tracker.add_failure_attempt()
		self.assertTrue(tracker.is_user_allowed())

		tracker.add_failure_attempt()
		self.assertTrue(tracker.is_user_allowed())

		tracker.add_failure_attempt()
		self.assertTrue(tracker.is_user_allowed())

		tracker.add_failure_attempt()
		self.assertFalse(tracker.is_user_allowed())

	def test_account_unlock(self):
		"""Make sure that locked account gets unlocked after lock_interval of time."""
		lock_interval = 2  # In sec
		tracker = LoginAttemptTracker(
			user_name="tester", max_consecutive_login_attempts=1, lock_interval=lock_interval
		)
		# Clear the cache by setting attempt as success
		tracker.add_success_attempt()

		tracker.add_failure_attempt()
		self.assertTrue(tracker.is_user_allowed())

		tracker.add_failure_attempt()
		self.assertFalse(tracker.is_user_allowed())

		# Sleep for lock_interval of time, so that next request con unlock the user access.
		time.sleep(lock_interval)

		tracker.add_failure_attempt()
		self.assertTrue(tracker.is_user_allowed())
