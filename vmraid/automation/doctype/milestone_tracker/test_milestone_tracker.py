# -*- coding: utf-8 -*-
# Copyright (c) 2019, VMRaid Technologies and Contributors
# License: MIT. See LICENSE
import unittest

import vmraid
import vmraid.cache_manager


class TestMilestoneTracker(unittest.TestCase):
	def test_milestone(self):
		vmraid.db.delete("Milestone Tracker")

		vmraid.cache().delete_key("milestone_tracker_map")

		milestone_tracker = vmraid.get_doc(
			dict(doctype="Milestone Tracker", document_type="ToDo", track_field="status")
		).insert()

		todo = vmraid.get_doc(dict(doctype="ToDo", description="test milestone", status="Open")).insert()

		milestones = vmraid.get_all(
			"Milestone",
			fields=["track_field", "value", "milestone_tracker"],
			filters=dict(reference_type=todo.doctype, reference_name=todo.name),
		)

		self.assertEqual(len(milestones), 1)
		self.assertEqual(milestones[0].track_field, "status")
		self.assertEqual(milestones[0].value, "Open")

		todo.status = "Closed"
		todo.save()

		milestones = vmraid.get_all(
			"Milestone",
			fields=["track_field", "value", "milestone_tracker"],
			filters=dict(reference_type=todo.doctype, reference_name=todo.name),
			order_by="modified desc",
		)

		self.assertEqual(len(milestones), 2)
		self.assertEqual(milestones[0].track_field, "status")
		self.assertEqual(milestones[0].value, "Closed")

		# cleanup
		vmraid.db.delete("Milestone")
		milestone_tracker.delete()
