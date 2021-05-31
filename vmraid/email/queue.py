# Copyright (c) 2015, VMRaid Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

from __future__ import unicode_literals
import vmraid
import sys
from six.moves import html_parser as HTMLParser
import smtplib, quopri, json
from vmraid import msgprint, _, safe_decode, safe_encode, enqueue
from vmraid.email.smtp import SMTPServer
from vmraid.email.doctype.email_account.email_account import EmailAccount
from vmraid.email.email_body import get_email, get_formatted_html, add_attachment
from vmraid.utils.verified_command import get_signed_params, verify_request
from html2text import html2text
from vmraid.utils import get_url, nowdate, now_datetime, add_days, split_emails, cstr, cint
from rq.timeouts import JobTimeoutException
from six import text_type, string_types, PY3
from email.parser import Parser


class EmailLimitCrossedError(vmraid.ValidationError): pass

def send(recipients=None, sender=None, subject=None, message=None, text_content=None, reference_doctype=None,
		reference_name=None, unsubscribe_method=None, unsubscribe_params=None, unsubscribe_message=None,
		attachments=None, reply_to=None, cc=None, bcc=None, message_id=None, in_reply_to=None, send_after=None,
		expose_recipients=None, send_priority=1, communication=None, now=False, read_receipt=None,
		queue_separately=False, is_notification=False, add_unsubscribe_link=1, inline_images=None,
		header=None, print_letterhead=False, with_container=False):
	"""Add email to sending queue (Email Queue)

	:param recipients: List of recipients.
	:param sender: Email sender.
	:param subject: Email subject.
	:param message: Email message.
	:param text_content: Text version of email message.
	:param reference_doctype: Reference DocType of caller document.
	:param reference_name: Reference name of caller document.
	:param send_priority: Priority for Email Queue, default 1.
	:param unsubscribe_method: URL method for unsubscribe. Default is `/api/method/vmraid.email.queue.unsubscribe`.
	:param unsubscribe_params: additional params for unsubscribed links. default are name, doctype, email
	:param attachments: Attachments to be sent.
	:param reply_to: Reply to be captured here (default inbox)
	:param in_reply_to: Used to send the Message-Id of a received email back as In-Reply-To.
	:param send_after: Send this email after the given datetime. If value is in integer, then `send_after` will be the automatically set to no of days from current date.
	:param communication: Communication link to be set in Email Queue record
	:param now: Send immediately (don't send in the background)
	:param queue_separately: Queue each email separately
	:param is_notification: Marks email as notification so will not trigger notifications from system
	:param add_unsubscribe_link: Send unsubscribe link in the footer of the Email, default 1.
	:param inline_images: List of inline images as {"filename", "filecontent"}. All src properties will be replaced with random Content-Id
	:param header: Append header in email (boolean)
	:param with_container: Wraps email inside styled container
	"""
	if not unsubscribe_method:
		unsubscribe_method = "/api/method/vmraid.email.queue.unsubscribe"

	if not recipients and not cc:
		return

	if not cc:
		cc = []
	if not bcc:
		bcc = []

	if isinstance(recipients, string_types):
		recipients = split_emails(recipients)

	if isinstance(cc, string_types):
		cc = split_emails(cc)

	if isinstance(bcc, string_types):
		bcc = split_emails(bcc)

	if isinstance(send_after, int):
		send_after = add_days(nowdate(), send_after)

	email_account = EmailAccount.find_outgoing(
		match_by_doctype=reference_doctype, match_by_email=sender, _raise_error=True)

	if not sender or sender == "Administrator":
		sender = email_account.default_sender

	if not text_content:
		try:
			text_content = html2text(message)
		except HTMLParser.HTMLParseError:
			text_content = "See html attachment"

	recipients = list(set(recipients))
	cc = list(set(cc))

	all_ids = tuple(recipients + cc)

	unsubscribed = vmraid.db.sql_list('''
		SELECT
			distinct email
		from
			`tabEmail Unsubscribe`
		where
			email in %(all_ids)s
			and (
				(
					reference_doctype = %(reference_doctype)s
					and reference_name = %(reference_name)s
				)
				or global_unsubscribe = 1
			)
	''', {
		'all_ids': all_ids,
		'reference_doctype': reference_doctype,
		'reference_name': reference_name,
	})

	recipients = [r for r in recipients if r and r not in unsubscribed]

	if cc:
		cc = [r for r in cc if r and r not in unsubscribed]

	if not recipients and not cc:
		# Recipients may have been unsubscribed, exit quietly
		return

	email_text_context = text_content

	should_append_unsubscribe = (add_unsubscribe_link
		and reference_doctype
		and (unsubscribe_message or reference_doctype=="Newsletter")
		and add_unsubscribe_link==1)

	unsubscribe_link = None
	if should_append_unsubscribe:
		unsubscribe_link = get_unsubscribe_message(unsubscribe_message, expose_recipients)
		email_text_context += unsubscribe_link.text

	email_content = get_formatted_html(subject, message,
		email_account=email_account, header=header,
		unsubscribe_link=unsubscribe_link, with_container=with_container)

	# add to queue
	add(recipients, sender, subject,
		formatted=email_content,
		text_content=email_text_context,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		attachments=attachments,
		reply_to=reply_to,
		cc=cc,
		bcc=bcc,
		message_id=message_id,
		in_reply_to=in_reply_to,
		send_after=send_after,
		send_priority=send_priority,
		email_account=email_account,
		communication=communication,
		add_unsubscribe_link=add_unsubscribe_link,
		unsubscribe_method=unsubscribe_method,
		unsubscribe_params=unsubscribe_params,
		expose_recipients=expose_recipients,
		read_receipt=read_receipt,
		queue_separately=queue_separately,
		is_notification = is_notification,
		inline_images = inline_images,
		header=header,
		now=now,
		print_letterhead=print_letterhead)


def add(recipients, sender, subject, **kwargs):
	"""Add to Email Queue"""
	if kwargs.get('queue_separately') or len(recipients) > 20:
		email_queue = None
		for r in recipients:
			if not email_queue:
				email_queue = get_email_queue([r], sender, subject, **kwargs)
				if kwargs.get('now'):
					email_queue.send()
			else:
				duplicate = email_queue.get_duplicate([r])
				duplicate.insert(ignore_permissions=True)

				if kwargs.get('now'):
					duplicate.send()

			vmraid.db.commit()
	else:
		email_queue = get_email_queue(recipients, sender, subject, **kwargs)
		if kwargs.get('now'):
			email_queue.send()

def get_email_queue(recipients, sender, subject, **kwargs):
	'''Make Email Queue object'''
	e = vmraid.new_doc('Email Queue')
	e.priority = kwargs.get('send_priority')
	attachments = kwargs.get('attachments')
	if attachments:
		# store attachments with fid or print format details, to be attached on-demand later
		_attachments = []
		for att in attachments:
			if att.get('fid'):
				_attachments.append(att)
			elif att.get("print_format_attachment") == 1:
				if not att.get('lang', None):
					att['lang'] = vmraid.local.lang
				att['print_letterhead'] = kwargs.get('print_letterhead')
				_attachments.append(att)
		e.attachments = json.dumps(_attachments)

	try:
		mail = get_email(recipients,
			sender=sender,
			subject=subject,
			formatted=kwargs.get('formatted'),
			text_content=kwargs.get('text_content'),
			attachments=kwargs.get('attachments'),
			reply_to=kwargs.get('reply_to'),
			cc=kwargs.get('cc'),
			bcc=kwargs.get('bcc'),
			email_account=kwargs.get('email_account'),
			expose_recipients=kwargs.get('expose_recipients'),
			inline_images=kwargs.get('inline_images'),
			header=kwargs.get('header'))

		mail.set_message_id(kwargs.get('message_id'),kwargs.get('is_notification'))
		if kwargs.get('read_receipt'):
			mail.msg_root["Disposition-Notification-To"] = sender
		if kwargs.get('in_reply_to'):
			mail.set_in_reply_to(kwargs.get('in_reply_to'))

		e.message_id = mail.msg_root["Message-Id"].strip(" <>")
		e.message = cstr(mail.as_string())
		e.sender = mail.sender

	except vmraid.InvalidEmailAddressError:
		# bad Email Address - don't add to queue
		import traceback
		vmraid.log_error('Invalid Email ID Sender: {0}, Recipients: {1}, \nTraceback: {2} '.format(mail.sender,
			', '.join(mail.recipients), traceback.format_exc()), 'Email Not Sent')

	recipients = list(set(recipients + kwargs.get('cc', []) + kwargs.get('bcc', [])))
	email_account = kwargs.get('email_account')
	email_account_name = email_account and email_account.is_exists_in_db() and email_account.name

	e.set_recipients(recipients)
	e.reference_doctype = kwargs.get('reference_doctype')
	e.reference_name = kwargs.get('reference_name')
	e.add_unsubscribe_link = kwargs.get("add_unsubscribe_link")
	e.unsubscribe_method = kwargs.get('unsubscribe_method')
	e.unsubscribe_params = kwargs.get('unsubscribe_params')
	e.expose_recipients = kwargs.get('expose_recipients')
	e.communication = kwargs.get('communication')
	e.send_after = kwargs.get('send_after')
	e.show_as_cc = ",".join(kwargs.get('cc', []))
	e.show_as_bcc = ",".join(kwargs.get('bcc', []))
	e.email_account = email_account_name or None
	e.insert(ignore_permissions=True)
	return e

def get_emails_sent_this_month():
	return vmraid.db.sql("""
		SELECT COUNT(*) FROM `tabEmail Queue`
		WHERE `status`='Sent' AND EXTRACT(YEAR_MONTH FROM `creation`) = EXTRACT(YEAR_MONTH FROM NOW())
	""")[0][0]

def get_emails_sent_today():
	return vmraid.db.sql("""SELECT COUNT(`name`) FROM `tabEmail Queue` WHERE
		`status` in ('Sent', 'Not Sent', 'Sending') AND `creation` > (NOW() - INTERVAL '24' HOUR)""")[0][0]

def get_unsubscribe_message(unsubscribe_message, expose_recipients):
	if unsubscribe_message:
		unsubscribe_html = '''<a href="<!--unsubscribe url-->"
			target="_blank">{0}</a>'''.format(unsubscribe_message)
	else:
		unsubscribe_link = '''<a href="<!--unsubscribe url-->"
			target="_blank">{0}</a>'''.format(_('Unsubscribe'))
		unsubscribe_html = _("{0} to stop receiving emails of this type").format(unsubscribe_link)

	html = """<div class="email-unsubscribe">
			<!--cc message-->
			<div>
				{0}
			</div>
		</div>""".format(unsubscribe_html)

	if expose_recipients == "footer":
		text = "\n<!--cc message-->"
	else:
		text = ""
	text += "\n\n{unsubscribe_message}: <!--unsubscribe url-->\n".format(unsubscribe_message=unsubscribe_message)

	return vmraid._dict({
		"html": html,
		"text": text
	})

def get_unsubcribed_url(reference_doctype, reference_name, email, unsubscribe_method, unsubscribe_params):
	params = {"email": email.encode("utf-8"),
		"doctype": reference_doctype.encode("utf-8"),
		"name": reference_name.encode("utf-8")}
	if unsubscribe_params:
		params.update(unsubscribe_params)

	query_string = get_signed_params(params)

	# for test
	vmraid.local.flags.signed_query_string = query_string

	return get_url(unsubscribe_method + "?" + get_signed_params(params))

@vmraid.whitelist(allow_guest=True)
def unsubscribe(doctype, name, email):
	# unsubsribe from comments and communications
	if not verify_request():
		return

	try:
		vmraid.get_doc({
			"doctype": "Email Unsubscribe",
			"email": email,
			"reference_doctype": doctype,
			"reference_name": name
		}).insert(ignore_permissions=True)

	except vmraid.DuplicateEntryError:
		vmraid.db.rollback()

	else:
		vmraid.db.commit()

	return_unsubscribed_page(email, doctype, name)

def return_unsubscribed_page(email, doctype, name):
	vmraid.respond_as_web_page(_("Unsubscribed"),
		_("{0} has left the conversation in {1} {2}").format(email, _(doctype), name),
		indicator_color='green')

def flush(from_test=False):
	"""flush email queue, every time: called from scheduler
	"""
	from vmraid.email.doctype.email_queue.email_queue import send_mail
	# To avoid running jobs inside unit tests
	if vmraid.are_emails_muted():
		msgprint(_("Emails are muted"))
		from_test = True

	if cint(vmraid.defaults.get_defaults().get("hold_queue"))==1:
		return

	for row in get_queue():
		try:
			func = send_mail if from_test else send_mail.enqueue
			is_background_task = not from_test
			func(email_queue_name = row.name, is_background_task = is_background_task)
		except Exception:
			vmraid.log_error()

def get_queue():
	return vmraid.db.sql('''select
			name, sender
		from
			`tabEmail Queue`
		where
			(status='Not Sent' or status='Partially Sent') and
			(send_after is null or send_after < %(now)s)
		order
			by priority desc, creation asc
		limit 500''', { 'now': now_datetime() }, as_dict=True)

def clear_outbox(days=None):
	"""Remove low priority older than 31 days in Outbox or configured in Log Settings.
	Note: Used separate query to avoid deadlock
	"""
	if not days:
		days=31

	email_queues = vmraid.db.sql_list("""SELECT `name` FROM `tabEmail Queue`
		WHERE `priority`=0 AND `modified` < (NOW() - INTERVAL '{0}' DAY)""".format(days))

	if email_queues:
		vmraid.db.sql("""DELETE FROM `tabEmail Queue` WHERE `name` IN ({0})""".format(
			','.join(['%s']*len(email_queues)
		)), tuple(email_queues))

		vmraid.db.sql("""DELETE FROM `tabEmail Queue Recipient` WHERE `parent` IN ({0})""".format(
			','.join(['%s']*len(email_queues)
		)), tuple(email_queues))

def set_expiry_for_email_queue():
	''' Mark emails as expire that has not sent for 7 days.
		Called daily via scheduler.
	 '''

	vmraid.db.sql("""
		UPDATE `tabEmail Queue`
		SET `status`='Expired'
		WHERE `modified` < (NOW() - INTERVAL '7' DAY)
		AND `status`='Not Sent'
		AND (`send_after` IS NULL OR `send_after` < %(now)s)""", { 'now': now_datetime() })
