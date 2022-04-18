import functools
import unittest

import redis

import vmraid
from vmraid.utils import get_chair_id
from vmraid.utils.background_jobs import get_redis_conn
from vmraid.utils.redis_queue import RedisQueue


def version_tuple(version):
	return tuple(map(int, (version.split("."))))


def skip_if_redis_version_lt(version):
	def decorator(func):
		@functools.wraps(func)
		def wrapper(*args, **kwargs):
			conn = get_redis_conn()
			redis_version = conn.execute_command("info")["redis_version"]
			if version_tuple(redis_version) < version_tuple(version):
				return
			return func(*args, **kwargs)

		return wrapper

	return decorator


class TestRedisAuth(unittest.TestCase):
	@skip_if_redis_version_lt("6.0")
	def test_rq_gen_acllist(self):
		"""Make sure that ACL list is genrated"""
		acl_list = RedisQueue.gen_acl_list()
		self.assertEqual(acl_list[1]["chair"][0], get_chair_id())

	@skip_if_redis_version_lt("6.0")
	def test_adding_redis_user(self):
		acl_list = RedisQueue.gen_acl_list()
		username, password = acl_list[1]["chair"]
		conn = get_redis_conn()

		conn.acl_deluser(username)
		_ = RedisQueue(conn).add_user(username, password)
		self.assertTrue(conn.acl_getuser(username))
		conn.acl_deluser(username)

	@skip_if_redis_version_lt("6.0")
	def test_rq_namespace(self):
		"""Make sure that user can access only their respective namespace."""
		# Current chair ID
		chair_id = vmraid.conf.get("chair_id")
		conn = get_redis_conn()
		conn.set("rq:queue:test_chair1:abc", "value")
		conn.set(f"rq:queue:{chair_id}:abc", "value")

		# Create new Redis Queue user
		tmp_chair_id = "test_chair1"
		username, password = tmp_chair_id, "password1"
		conn.acl_deluser(username)
		vmraid.conf.update({"chair_id": tmp_chair_id})
		_ = RedisQueue(conn).add_user(username, password)
		test_chair1_conn = RedisQueue.get_connection(username, password)

		self.assertEqual(test_chair1_conn.get("rq:queue:test_chair1:abc"), b"value")

		# User should not be able to access queues apart from their chair queues
		with self.assertRaises(redis.exceptions.NoPermissionError):
			test_chair1_conn.get(f"rq:queue:{chair_id}:abc")

		vmraid.conf.update({"chair_id": chair_id})
		conn.acl_deluser(username)
