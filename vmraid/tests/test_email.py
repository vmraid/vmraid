# Copyright (c) 2022, VMRaid and Contributors
# License: MIT. See LICENSE

import email
import re
import unittest

import vmraid
from vmraid.email.doctype.email_account.test_email_account import TestEmailAccount

test_dependencies = ["Email Account"]


class TestEmail(unittest.TestCase):
	def setUp(self):
		vmraid.db.delete("Email Unsubscribe")
		vmraid.db.delete("Email Queue")
		vmraid.db.delete("Email Queue Recipient")

	def test_email_queue(self, send_after=None):
		vmraid.sendmail(
			recipients=["test@example.com", "test1@example.com"],
			sender="admin@example.com",
			reference_doctype="User",
			reference_name="Administrator",
			subject="Testing Queue",
			message="This mail is queued!",
			unsubscribe_message="Unsubscribe",
			send_after=send_after,
		)

		email_queue = vmraid.db.sql(
			"""select name,message from `tabEmail Queue` where status='Not Sent'""", as_dict=1
		)
		self.assertEqual(len(email_queue), 1)
		queue_recipients = [
			r.recipient
			for r in vmraid.db.sql(
				"""SELECT recipient FROM `tabEmail Queue Recipient`
			WHERE status='Not Sent'""",
				as_dict=1,
			)
		]
		self.assertTrue("test@example.com" in queue_recipients)
		self.assertTrue("test1@example.com" in queue_recipients)
		self.assertEqual(len(queue_recipients), 2)
		self.assertTrue("<!--unsubscribe_url-->" in email_queue[0]["message"])

	def test_send_after(self):
		self.test_email_queue(send_after=1)
		from vmraid.email.queue import flush

		flush(from_test=True)
		email_queue = vmraid.db.sql(
			"""select name from `tabEmail Queue` where status='Sent'""", as_dict=1
		)
		self.assertEqual(len(email_queue), 0)

	def test_flush(self):
		self.test_email_queue()
		from vmraid.email.queue import flush

		flush(from_test=True)
		email_queue = vmraid.db.sql(
			"""select name from `tabEmail Queue` where status='Sent'""", as_dict=1
		)
		self.assertEqual(len(email_queue), 1)
		queue_recipients = [
			r.recipient
			for r in vmraid.db.sql(
				"""select recipient from `tabEmail Queue Recipient`
			where status='Sent'""",
				as_dict=1,
			)
		]
		self.assertTrue("test@example.com" in queue_recipients)
		self.assertTrue("test1@example.com" in queue_recipients)
		self.assertEqual(len(queue_recipients), 2)
		self.assertTrue("Unsubscribe" in vmraid.safe_decode(vmraid.flags.sent_mail))

	def test_cc_header(self):
		# test if sending with cc's makes it into header
		vmraid.sendmail(
			recipients=["test@example.com"],
			cc=["test1@example.com"],
			sender="admin@example.com",
			reference_doctype="User",
			reference_name="Administrator",
			subject="Testing Email Queue",
			message="This is mail is queued!",
			unsubscribe_message="Unsubscribe",
			expose_recipients="header",
		)
		email_queue = vmraid.db.sql(
			"""select name from `tabEmail Queue` where status='Not Sent'""", as_dict=1
		)
		self.assertEqual(len(email_queue), 1)
		queue_recipients = [
			r.recipient
			for r in vmraid.db.sql(
				"""select recipient from `tabEmail Queue Recipient`
			where status='Not Sent'""",
				as_dict=1,
			)
		]
		self.assertTrue("test@example.com" in queue_recipients)
		self.assertTrue("test1@example.com" in queue_recipients)

		message = vmraid.db.sql(
			"""select message from `tabEmail Queue`
			where status='Not Sent'""",
			as_dict=1,
		)[0].message
		self.assertTrue("To: test@example.com" in message)
		self.assertTrue("CC: test1@example.com" in message)

	def test_cc_footer(self):
		vmraid.conf.use_ssl = True
		# test if sending with cc's makes it into header
		vmraid.sendmail(
			recipients=["test@example.com"],
			cc=["test1@example.com"],
			sender="admin@example.com",
			reference_doctype="User",
			reference_name="Administrator",
			subject="Testing Email Queue",
			message="This is mail is queued!",
			unsubscribe_message="Unsubscribe",
			expose_recipients="footer",
			now=True,
		)
		email_queue = vmraid.db.sql(
			"""select name from `tabEmail Queue` where status='Sent'""", as_dict=1
		)
		self.assertEqual(len(email_queue), 1)
		queue_recipients = [
			r.recipient
			for r in vmraid.db.sql(
				"""select recipient from `tabEmail Queue Recipient`
			where status='Sent'""",
				as_dict=1,
			)
		]
		self.assertTrue("test@example.com" in queue_recipients)
		self.assertTrue("test1@example.com" in queue_recipients)

		self.assertTrue(
			"This email was sent to test@example.com and copied to test1@example.com"
			in vmraid.safe_decode(vmraid.flags.sent_mail)
		)

		# check for email tracker
		self.assertTrue("mark_email_as_seen" in vmraid.safe_decode(vmraid.flags.sent_mail))
		vmraid.conf.use_ssl = False

	def test_expose(self):

		from vmraid.utils.verified_command import verify_request

		vmraid.sendmail(
			recipients=["test@example.com"],
			cc=["test1@example.com"],
			sender="admin@example.com",
			reference_doctype="User",
			reference_name="Administrator",
			subject="Testing Email Queue",
			message="This is mail is queued!",
			unsubscribe_message="Unsubscribe",
			now=True,
		)
		email_queue = vmraid.db.sql(
			"""select name from `tabEmail Queue` where status='Sent'""", as_dict=1
		)
		self.assertEqual(len(email_queue), 1)
		queue_recipients = [
			r.recipient
			for r in vmraid.db.sql(
				"""select recipient from `tabEmail Queue Recipient`
			where status='Sent'""",
				as_dict=1,
			)
		]
		self.assertTrue("test@example.com" in queue_recipients)
		self.assertTrue("test1@example.com" in queue_recipients)

		message = vmraid.db.sql(
			"""select message from `tabEmail Queue`
			where status='Sent'""",
			as_dict=1,
		)[0].message
		self.assertTrue("<!--recipient-->" in message)

		email_obj = email.message_from_string(vmraid.safe_decode(vmraid.flags.sent_mail))
		for part in email_obj.walk():
			content = part.get_payload(decode=True)

			if content:
				eol = "\r\n"

				vmraid.local.flags.signed_query_string = re.search(
					r"(?<=/api/method/vmraid.email.queue.unsubscribe\?).*(?=" + eol + ")", content.decode()
				).group(0)
				self.assertTrue(verify_request())
				break

	def test_expired(self):
		self.test_email_queue()
		vmraid.db.sql("UPDATE `tabEmail Queue` SET `modified`=(NOW() - INTERVAL '8' day)")

		from vmraid.email.queue import set_expiry_for_email_queue

		set_expiry_for_email_queue()

		email_queue = vmraid.db.sql(
			"""select name from `tabEmail Queue` where status='Expired'""", as_dict=1
		)
		self.assertEqual(len(email_queue), 1)
		queue_recipients = [
			r.recipient
			for r in vmraid.db.sql(
				"""select recipient from `tabEmail Queue Recipient`
			where parent = %s""",
				email_queue[0].name,
				as_dict=1,
			)
		]
		self.assertTrue("test@example.com" in queue_recipients)
		self.assertTrue("test1@example.com" in queue_recipients)
		self.assertEqual(len(queue_recipients), 2)

	def test_unsubscribe(self):
		from vmraid.email.doctype.email_queue.email_queue import QueueBuilder
		from vmraid.email.queue import unsubscribe

		unsubscribe(doctype="User", name="Administrator", email="test@example.com")

		self.assertTrue(
			vmraid.db.get_value(
				"Email Unsubscribe",
				{"reference_doctype": "User", "reference_name": "Administrator", "email": "test@example.com"},
			)
		)

		before = vmraid.db.sql("""select count(name) from `tabEmail Queue` where status='Not Sent'""")[
			0
		][0]

		builder = QueueBuilder(
			recipients=["test@example.com", "test1@example.com"],
			sender="admin@example.com",
			reference_doctype="User",
			reference_name="Administrator",
			subject="Testing Email Queue",
			message="This is mail is queued!",
			unsubscribe_message="Unsubscribe",
		)
		builder.process()
		# this is sent async (?)

		email_queue = vmraid.db.sql(
			"""select name from `tabEmail Queue` where status='Not Sent'""", as_dict=1
		)
		self.assertEqual(len(email_queue), before + 1)
		queue_recipients = [
			r.recipient
			for r in vmraid.db.sql(
				"""select recipient from `tabEmail Queue Recipient`
			where status='Not Sent'""",
				as_dict=1,
			)
		]
		self.assertFalse("test@example.com" in queue_recipients)
		self.assertTrue("test1@example.com" in queue_recipients)
		self.assertEqual(len(queue_recipients), 1)
		self.assertTrue("Unsubscribe" in vmraid.safe_decode(vmraid.flags.sent_mail))

	def test_image_parsing(self):
		import re

		email_account = vmraid.get_doc("Email Account", "_Test Email Account 1")

		vmraid.db.delete("Communication", {"sender": "sukh@yyy.com"})

		with open(vmraid.get_app_path("vmraid", "tests", "data", "email_with_image.txt"), "r") as raw:
			messages = {
				'"INBOX"': {"latest_messages": [raw.read()], "seen_status": {2: "UNSEEN"}, "uid_list": [2]}
			}

			email_account = vmraid.get_doc("Email Account", "_Test Email Account 1")
			changed_flag = False
			if not email_account.enable_incoming:
				email_account.enable_incoming = True
				changed_flag = True
			mails = TestEmailAccount.mocked_get_inbound_mails(email_account, messages)

			# TODO: fix this flaky test! - 'IndexError: list index out of range' for `.process()` line
			if not mails:
				raise self.skipTest("No inbound mails found / Email Account wasn't patched properly")

			communication = mails[0].process()

		self.assertTrue(
			re.search("""<img[^>]*src=["']/private/files/rtco1.png[^>]*>""", communication.content)
		)
		self.assertTrue(
			re.search("""<img[^>]*src=["']/private/files/rtco2.png[^>]*>""", communication.content)
		)

		if changed_flag:
			email_account.enable_incoming = False


if __name__ == "__main__":
	vmraid.connect()
	unittest.main()
