# -*- coding: utf-8 -*-
# Copyright (c) 2019, VMRaid Technologies and contributors
# License: MIT. See LICENSE


import google.oauth2.credentials
import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import vmraid
from vmraid import _
from vmraid.integrations.doctype.google_settings.google_settings import get_auth_url
from vmraid.model.document import Document
from vmraid.utils import get_request_site_address

SCOPES = "https://www.googleapis.com/auth/contacts"


class GoogleContacts(Document):
	def validate(self):
		if not vmraid.db.get_single_value("Google Settings", "enable"):
			vmraid.throw(_("Enable Google API in Google Settings."))

	def get_access_token(self):
		google_settings = vmraid.get_doc("Google Settings")

		if not google_settings.enable:
			vmraid.throw(_("Google Contacts Integration is disabled."))

		if not self.refresh_token:
			button_label = vmraid.bold(_("Allow Google Contacts Access"))
			raise vmraid.ValidationError(_("Click on {0} to generate Refresh Token.").format(button_label))

		data = {
			"client_id": google_settings.client_id,
			"client_secret": google_settings.get_password(fieldname="client_secret", raise_exception=False),
			"refresh_token": self.get_password(fieldname="refresh_token", raise_exception=False),
			"grant_type": "refresh_token",
			"scope": SCOPES,
		}

		try:
			r = requests.post(get_auth_url(), data=data).json()
		except requests.exceptions.HTTPError:
			button_label = vmraid.bold(_("Allow Google Contacts Access"))
			vmraid.throw(
				_(
					"Something went wrong during the token generation. Click on {0} to generate a new one."
				).format(button_label)
			)

		return r.get("access_token")


@vmraid.whitelist()
def authorize_access(g_contact, reauthorize=None):
	"""
	If no Authorization code get it from Google and then request for Refresh Token.
	Google Contact Name is set to flags to set_value after Authorization Code is obtained.
	"""

	google_settings = vmraid.get_doc("Google Settings")
	google_contact = vmraid.get_doc("Google Contacts", g_contact)

	redirect_uri = (
		get_request_site_address(True)
		+ "?cmd=vmraid.integrations.doctype.google_contacts.google_contacts.google_callback"
	)

	if not google_contact.authorization_code or reauthorize:
		vmraid.cache().hset("google_contacts", "google_contact", google_contact.name)
		return get_authentication_url(client_id=google_settings.client_id, redirect_uri=redirect_uri)
	else:
		try:
			data = {
				"code": google_contact.authorization_code,
				"client_id": google_settings.client_id,
				"client_secret": google_settings.get_password(
					fieldname="client_secret", raise_exception=False
				),
				"redirect_uri": redirect_uri,
				"grant_type": "authorization_code",
			}
			r = requests.post(get_auth_url(), data=data).json()

			if "refresh_token" in r:
				vmraid.db.set_value(
					"Google Contacts", google_contact.name, "refresh_token", r.get("refresh_token")
				)
				vmraid.db.commit()

			vmraid.local.response["type"] = "redirect"
			vmraid.local.response["location"] = "/app/Form/Google%20Contacts/{}".format(google_contact.name)

			vmraid.msgprint(_("Google Contacts has been configured."))
		except Exception as e:
			vmraid.throw(e)


def get_authentication_url(client_id=None, redirect_uri=None):
	return {
		"url": "https://accounts.google.com/o/oauth2/v2/auth?access_type=offline&response_type=code&prompt=consent&client_id={}&include_granted_scopes=true&scope={}&redirect_uri={}".format(
			client_id, SCOPES, redirect_uri
		)
	}


@vmraid.whitelist()
def google_callback(code=None):
	"""
	Authorization code is sent to callback as per the API configuration
	"""
	google_contact = vmraid.cache().hget("google_contacts", "google_contact")
	vmraid.db.set_value("Google Contacts", google_contact, "authorization_code", code)
	vmraid.db.commit()

	authorize_access(google_contact)


def get_google_contacts_object(g_contact):
	"""
	Returns an object of Google Calendar along with Google Calendar doc.
	"""
	google_settings = vmraid.get_doc("Google Settings")
	account = vmraid.get_doc("Google Contacts", g_contact)

	credentials_dict = {
		"token": account.get_access_token(),
		"refresh_token": account.get_password(fieldname="refresh_token", raise_exception=False),
		"token_uri": get_auth_url(),
		"client_id": google_settings.client_id,
		"client_secret": google_settings.get_password(fieldname="client_secret", raise_exception=False),
		"scopes": "https://www.googleapis.com/auth/contacts",
	}

	credentials = google.oauth2.credentials.Credentials(**credentials_dict)
	google_contacts = build(
		serviceName="people", version="v1", credentials=credentials, static_discovery=False
	)

	return google_contacts, account


@vmraid.whitelist()
def sync(g_contact=None):
	filters = {"enable": 1}

	if g_contact:
		filters.update({"name": g_contact})

	google_contacts = vmraid.get_list("Google Contacts", filters=filters)

	for g in google_contacts:
		return sync_contacts_from_google_contacts(g.name)


def sync_contacts_from_google_contacts(g_contact):
	"""
	Syncs Contacts from Google Contacts.
	https://developers.google.com/people/api/rest/v1/people.connections/list
	"""
	google_contacts, account = get_google_contacts_object(g_contact)

	if not account.pull_from_google_contacts:
		return

	results = []
	contacts_updated = 0

	sync_token = account.get_password(fieldname="next_sync_token", raise_exception=False) or None
	contacts = vmraid._dict()

	while True:
		try:
			contacts = (
				google_contacts.people()
				.connections()
				.list(
					resourceName="people/me",
					pageToken=contacts.get("nextPageToken"),
					syncToken=sync_token,
					pageSize=2000,
					requestSyncToken=True,
					personFields="names,emailAddresses,organizations,phoneNumbers",
				)
				.execute()
			)

		except HttpError as err:
			vmraid.throw(
				_(
					"Google Contacts - Could not sync contacts from Google Contacts {0}, error code {1}."
				).format(account.name, err.resp.status)
			)

		for contact in contacts.get("connections", []):
			results.append(contact)

		if not contacts.get("nextPageToken"):
			if contacts.get("nextSyncToken"):
				vmraid.db.set_value(
					"Google Contacts", account.name, "next_sync_token", contacts.get("nextSyncToken")
				)
				vmraid.db.commit()
			break

	vmraid.db.set_value("Google Contacts", account.name, "last_sync_on", vmraid.utils.now_datetime())

	for idx, connection in enumerate(results):
		vmraid.publish_realtime(
			"import_google_contacts", dict(progress=idx + 1, total=len(results)), user=vmraid.session.user
		)

		for name in connection.get("names"):
			if name.get("metadata").get("primary"):
				contacts_updated += 1
				contact = vmraid.get_doc(
					{
						"doctype": "Contact",
						"first_name": name.get("givenName") or "",
						"middle_name": name.get("middleName") or "",
						"last_name": name.get("familyName") or "",
						"designation": get_indexed_value(connection.get("organizations"), 0, "title"),
						"pulled_from_google_contacts": 1,
						"google_contacts": account.name,
						"company_name": get_indexed_value(connection.get("organizations"), 0, "name"),
					}
				)

				for email in connection.get("emailAddresses", []):
					contact.add_email(
						email_id=email.get("value"), is_primary=1 if email.get("metadata").get("primary") else 0
					)

				for phone in connection.get("phoneNumbers", []):
					contact.add_phone(
						phone=phone.get("value"), is_primary_phone=1 if phone.get("metadata").get("primary") else 0
					)

				contact.insert(ignore_permissions=True)

	return (
		_("{0} Google Contacts synced.").format(contacts_updated)
		if contacts_updated > 0
		else _("No new Google Contacts synced.")
	)


def insert_contacts_to_google_contacts(doc, method=None):
	"""
	Syncs Contacts from Google Contacts.
	https://developers.google.com/people/api/rest/v1/people/createContact
	"""
	if (
		not vmraid.db.exists("Google Contacts", {"name": doc.google_contacts})
		or doc.pulled_from_google_contacts
		or not doc.sync_with_google_contacts
	):
		return

	google_contacts, account = get_google_contacts_object(doc.google_contacts)

	if not account.push_to_google_contacts:
		return

	names = {"givenName": doc.first_name, "middleName": doc.middle_name, "familyName": doc.last_name}

	phoneNumbers = [{"value": phone_no.phone} for phone_no in doc.phone_nos]
	emailAddresses = [{"value": email_id.email_id} for email_id in doc.email_ids]

	try:
		contact = (
			google_contacts.people()
			.createContact(
				body={"names": [names], "phoneNumbers": phoneNumbers, "emailAddresses": emailAddresses}
			)
			.execute()
		)
		vmraid.db.set_value("Contact", doc.name, "google_contacts_id", contact.get("resourceName"))
	except HttpError as err:
		vmraid.msgprint(
			_("Google Calendar - Could not insert contact in Google Contacts {0}, error code {1}.").format(
				account.name, err.resp.status
			)
		)


def update_contacts_to_google_contacts(doc, method=None):
	"""
	Syncs Contacts from Google Contacts.
	https://developers.google.com/people/api/rest/v1/people/updateContact
	"""
	# Workaround to avoid triggering updation when Event is being inserted since
	# creation and modified are same when inserting doc
	if (
		not vmraid.db.exists("Google Contacts", {"name": doc.google_contacts})
		or doc.modified == doc.creation
		or not doc.sync_with_google_contacts
	):
		return

	if doc.sync_with_google_contacts and not doc.google_contacts_id:
		# If sync_with_google_contacts is checked later, then insert the contact rather than updating it.
		insert_contacts_to_google_contacts(doc)
		return

	google_contacts, account = get_google_contacts_object(doc.google_contacts)

	if not account.push_to_google_contacts:
		return

	names = {"givenName": doc.first_name, "middleName": doc.middle_name, "familyName": doc.last_name}

	phoneNumbers = [{"value": phone_no.phone} for phone_no in doc.phone_nos]
	emailAddresses = [{"value": email_id.email_id} for email_id in doc.email_ids]

	try:
		contact = (
			google_contacts.people()
			.get(
				resourceName=doc.google_contacts_id,
				personFields="names,emailAddresses,organizations,phoneNumbers",
			)
			.execute()
		)

		contact["names"] = [names]
		contact["phoneNumbers"] = phoneNumbers
		contact["emailAddresses"] = emailAddresses

		google_contacts.people().updateContact(
			resourceName=doc.google_contacts_id,
			body={
				"names": [names],
				"phoneNumbers": phoneNumbers,
				"emailAddresses": emailAddresses,
				"etag": contact.get("etag"),
			},
			updatePersonFields="names,emailAddresses,organizations,phoneNumbers",
		).execute()
		vmraid.msgprint(_("Contact Synced with Google Contacts."))
	except HttpError as err:
		vmraid.msgprint(
			_("Google Contacts - Could not update contact in Google Contacts {0}, error code {1}.").format(
				account.name, err.resp.status
			)
		)


def get_indexed_value(d, index, key):
	if not d:
		return ""

	try:
		return d[index].get(key)
	except IndexError:
		return ""
