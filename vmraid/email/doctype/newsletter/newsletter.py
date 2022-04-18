# Copyright (c) 2021, VMRaid and Contributors
# MIT License. See LICENSE

from typing import Dict, List

import vmraid
import vmraid.utils
from vmraid import _
from vmraid.email.doctype.email_group.email_group import add_subscribers
from vmraid.utils.verified_command import get_signed_params, verify_request
from vmraid.website.website_generator import WebsiteGenerator

from .exceptions import NewsletterAlreadySentError, NewsletterNotSavedError, NoRecipientFoundError


class Newsletter(WebsiteGenerator):
	def validate(self):
		self.route = f"newsletters/{self.name}"
		self.validate_sender_address()
		self.validate_recipient_address()
		self.validate_publishing()

	@property
	def newsletter_recipients(self) -> List[str]:
		if getattr(self, "_recipients", None) is None:
			self._recipients = self.get_recipients()
		return self._recipients

	@vmraid.whitelist()
	def get_sending_status(self):
		count_by_status = vmraid.get_all(
			"Email Queue",
			filters={"reference_doctype": self.doctype, "reference_name": self.name},
			fields=["status", "count(name) as count"],
			group_by="status",
			order_by="status",
		)
		sent = 0
		total = 0
		for row in count_by_status:
			if row.status == "Sent":
				sent = row.count
			total += row.count

		return {"sent": sent, "total": total}

	@vmraid.whitelist()
	def send_test_email(self, email):
		test_emails = vmraid.utils.validate_email_address(email, throw=True)
		self.send_newsletter(emails=test_emails)
		vmraid.msgprint(_("Test email sent to {0}").format(email), alert=True)

	@vmraid.whitelist()
	def find_broken_links(self):
		import requests
		from bs4 import BeautifulSoup

		html = self.get_message()
		soup = BeautifulSoup(html, "html.parser")
		links = soup.find_all("a")
		images = soup.find_all("img")
		broken_links = []
		for el in links + images:
			url = el.attrs.get("href") or el.attrs.get("src")
			try:
				response = requests.head(url, verify=False, timeout=5)
				if response.status_code >= 400:
					broken_links.append(url)
			except:
				broken_links.append(url)
		return broken_links

	@vmraid.whitelist()
	def send_emails(self):
		"""queue sending emails to recipients"""
		self.schedule_sending = False
		self.schedule_send = None
		self.queue_all()
		vmraid.msgprint(_("Email queued to {0} recipients").format(self.total_recipients))

	def validate_send(self):
		"""Validate if Newsletter can be sent."""
		self.validate_newsletter_status()
		self.validate_newsletter_recipients()

	def validate_newsletter_status(self):
		if self.email_sent:
			vmraid.throw(_("Newsletter has already been sent"), exc=NewsletterAlreadySentError)

		if self.get("__islocal"):
			vmraid.throw(_("Please save the Newsletter before sending"), exc=NewsletterNotSavedError)

	def validate_newsletter_recipients(self):
		if not self.newsletter_recipients:
			vmraid.throw(_("Newsletter should have atleast one recipient"), exc=NoRecipientFoundError)
		self.validate_recipient_address()

	def validate_sender_address(self):
		"""Validate self.send_from is a valid email address or not."""
		if self.sender_email:
			vmraid.utils.validate_email_address(self.sender_email, throw=True)
			self.send_from = (
				f"{self.sender_name} <{self.sender_email}>" if self.sender_name else self.sender_email
			)

	def validate_recipient_address(self):
		"""Validate if self.newsletter_recipients are all valid email addresses or not."""
		for recipient in self.newsletter_recipients:
			vmraid.utils.validate_email_address(recipient, throw=True)

	def validate_publishing(self):
		if self.send_webview_link and not self.published:
			vmraid.throw(_("Newsletter must be published to send webview link in email"))

	def get_linked_email_queue(self) -> List[str]:
		"""Get list of email queue linked to this newsletter."""
		return vmraid.get_all(
			"Email Queue",
			filters={
				"reference_doctype": self.doctype,
				"reference_name": self.name,
			},
			pluck="name",
		)

	def get_success_recipients(self) -> List[str]:
		"""Recipients who have already recieved the newsletter.

		Couldn't think of a better name ;)
		"""
		return vmraid.get_all(
			"Email Queue Recipient",
			filters={
				"status": ("in", ["Not Sent", "Sending", "Sent"]),
				"parentfield": ("in", self.get_linked_email_queue()),
			},
			pluck="recipient",
		)

	def get_pending_recipients(self) -> List[str]:
		"""Get list of pending recipients of the newsletter. These
		recipients may not have receive the newsletter in the previous iteration.
		"""
		return [x for x in self.newsletter_recipients if x not in self.get_success_recipients()]

	def queue_all(self):
		"""Queue Newsletter to all the recipients generated from the `Email Group` table"""
		self.validate()
		self.validate_send()

		recipients = self.get_pending_recipients()
		self.send_newsletter(emails=recipients)

		self.email_sent = True
		self.email_sent_at = vmraid.utils.now()
		self.total_recipients = len(recipients)
		self.save()

	def get_newsletter_attachments(self) -> List[Dict[str, str]]:
		"""Get list of attachments on current Newsletter"""
		return [{"file_url": row.attachment} for row in self.attachments]

	def send_newsletter(self, emails: List[str]):
		"""Trigger email generation for `emails` and add it in Email Queue."""
		attachments = self.get_newsletter_attachments()
		sender = self.send_from or vmraid.utils.get_formatted_email(self.owner)
		args = self.as_dict()
		args["message"] = self.get_message()

		is_auto_commit_set = bool(vmraid.db.auto_commit_on_many_writes)
		vmraid.db.auto_commit_on_many_writes = not vmraid.flags.in_test

		vmraid.sendmail(
			subject=self.subject,
			sender=sender,
			recipients=emails,
			attachments=attachments,
			template="newsletter",
			add_unsubscribe_link=self.send_unsubscribe_link,
			unsubscribe_method="/unsubscribe",
			unsubscribe_params={"name": self.name},
			reference_doctype=self.doctype,
			reference_name=self.name,
			queue_separately=True,
			send_priority=0,
			args=args,
		)

		vmraid.db.auto_commit_on_many_writes = is_auto_commit_set

	def get_message(self) -> str:
		message = self.message
		if self.content_type == "Markdown":
			message = vmraid.utils.md_to_html(self.message_md)
		if self.content_type == "HTML":
			message = self.message_html

		return vmraid.render_template(message, {"doc": self.as_dict()})

	def get_recipients(self) -> List[str]:
		"""Get recipients from Email Group"""
		emails = vmraid.get_all(
			"Email Group Member",
			filters={"unsubscribed": 0, "email_group": ("in", self.get_email_groups())},
			pluck="email",
		)
		return list(set(emails))

	def get_email_groups(self) -> List[str]:
		# wondering why the 'or'? i can't figure out why both aren't equivalent - @gavin
		return [x.email_group for x in self.email_group] or vmraid.get_all(
			"Newsletter Email Group",
			filters={"parent": self.name, "parenttype": "Newsletter"},
			pluck="email_group",
		)

	def get_attachments(self) -> List[Dict[str, str]]:
		return vmraid.get_all(
			"File",
			fields=["name", "file_name", "file_url", "is_private"],
			filters={
				"attached_to_name": self.name,
				"attached_to_doctype": "Newsletter",
				"is_private": 0,
			},
		)


@vmraid.whitelist(allow_guest=True)
def confirmed_unsubscribe(email, group):
	"""unsubscribe the email(user) from the mailing list(email_group)"""
	vmraid.flags.ignore_permissions = True
	doc = vmraid.get_doc("Email Group Member", {"email": email, "email_group": group})
	if not doc.unsubscribed:
		doc.unsubscribed = 1
		doc.save(ignore_permissions=True)


@vmraid.whitelist(allow_guest=True)
def subscribe(email, email_group=_("Website")):
	"""API endpoint to subscribe an email to a particular email group. Triggers a confirmation email."""

	# build subscription confirmation URL
	api_endpoint = vmraid.utils.get_url(
		"/api/method/vmraid.email.doctype.newsletter.newsletter.confirm_subscription"
	)
	signed_params = get_signed_params({"email": email, "email_group": email_group})
	confirm_subscription_url = f"{api_endpoint}?{signed_params}"

	# fetch custom template if available
	email_confirmation_template = vmraid.db.get_value(
		"Email Group", email_group, "confirmation_email_template"
	)

	# build email and send
	if email_confirmation_template:
		args = {"email": email, "confirmation_url": confirm_subscription_url, "email_group": email_group}
		email_template = vmraid.get_doc("Email Template", email_confirmation_template)
		email_subject = email_template.subject
		content = vmraid.render_template(email_template.response, args)
	else:
		email_subject = _("Confirm Your Email")
		translatable_content = (
			_("Thank you for your interest in subscribing to our updates"),
			_("Please verify your Email Address"),
			confirm_subscription_url,
			_("Click here to verify"),
		)
		content = """
			<p>{0}. {1}.</p>
			<p><a href="{2}">{3}</a></p>
		""".format(
			*translatable_content
		)

	vmraid.sendmail(
		email,
		subject=email_subject,
		content=content,
		now=True,
	)


@vmraid.whitelist(allow_guest=True)
def confirm_subscription(email, email_group=_("Website")):
	"""API endpoint to confirm email subscription.
	This endpoint is called when user clicks on the link sent to their mail.
	"""
	if not verify_request():
		return

	if not vmraid.db.exists("Email Group", email_group):
		vmraid.get_doc({"doctype": "Email Group", "title": email_group}).insert(ignore_permissions=True)

	vmraid.flags.ignore_permissions = True

	add_subscribers(email_group, email)
	vmraid.db.commit()

	vmraid.respond_as_web_page(
		_("Confirmed"),
		_("{0} has been successfully added to the Email Group.").format(email),
		indicator_color="green",
	)


def get_list_context(context=None):
	context.update(
		{
			"show_search": True,
			"no_breadcrumbs": True,
			"title": _("Newsletters"),
			"filters": {"published": 1},
			"row_template": "email/doctype/newsletter/templates/newsletter_row.html",
		}
	)


def send_scheduled_email():
	"""Send scheduled newsletter to the recipients."""
	scheduled_newsletter = vmraid.get_all(
		"Newsletter",
		filters={
			"schedule_send": ("<=", vmraid.utils.now_datetime()),
			"email_sent": False,
			"schedule_sending": True,
		},
		ignore_ifnull=True,
		pluck="name",
	)

	for newsletter in scheduled_newsletter:
		try:
			vmraid.get_doc("Newsletter", newsletter).queue_all()

		except Exception:
			vmraid.db.rollback()

			# wasn't able to send emails :(
			vmraid.db.set_value("Newsletter", newsletter, "email_sent", 0)
			message = (
				f"Newsletter {newsletter} failed to send" "\n\n" f"Traceback: {vmraid.get_traceback()}"
			)
			vmraid.log_error(title="Send Newsletter", message=message)

		if not vmraid.flags.in_test:
			vmraid.db.commit()
