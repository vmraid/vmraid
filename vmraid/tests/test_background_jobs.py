import time
import unittest

from rq import Queue

import vmraid
from vmraid.core.page.background_jobs.background_jobs import remove_failed_jobs
from vmraid.utils.background_jobs import generate_qname, get_redis_conn


class TestBackgroundJobs(unittest.TestCase):
	def test_remove_failed_jobs(self):
		vmraid.enqueue(method="vmraid.tests.test_background_jobs.fail_function", queue="short")
		# wait for enqueued job to execute
		time.sleep(2)
		conn = get_redis_conn()
		queues = Queue.all(conn)

		for queue in queues:
			if queue.name == generate_qname("short"):
				fail_registry = queue.failed_job_registry
				self.assertGreater(fail_registry.count, 0)

		remove_failed_jobs()

		for queue in queues:
			if queue.name == generate_qname("short"):
				fail_registry = queue.failed_job_registry
				self.assertEqual(fail_registry.count, 0)

	def test_enqueue_at_front(self):
		kwargs = {
			"method": "vmraid.handler.ping",
			"queue": "short",
		}

		# give worker something to work on first so that get_position doesn't return None
		vmraid.enqueue(**kwargs)

		# test enqueue with at_front=True
		low_priority_job = vmraid.enqueue(**kwargs)
		high_priority_job = vmraid.enqueue(**kwargs, at_front=True)

		# lesser is earlier
		self.assertTrue(high_priority_job.get_position() < low_priority_job.get_position())


def fail_function():
	return 1 / 0
