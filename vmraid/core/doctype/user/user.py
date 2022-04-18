# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
from bs4 import BeautifulSoup

import vmraid
import vmraid.defaults
import vmraid.permissions
import vmraid.share
from vmraid import _, msgprint, throw
from vmraid.core.doctype.user_type.user_type import user_linked_with_permission_on_doctype
from vmraid.desk.doctype.notification_settings.notification_settings import (
	create_notification_settings,
	toggle_notifications,
)
from vmraid.desk.notifications import clear_notifications
from vmraid.model.document import Document
from vmraid.query_builder import DocType
from vmraid.rate_limiter import rate_limit
from vmraid.utils import (
	cint,
	escape_html,
	flt,
	format_datetime,
	get_formatted_email,
	get_time_zone,
	has_gravatar,
	now_datetime,
	today,
)
from vmraid.utils.password import check_password, get_password_reset_limit
from vmraid.utils.password import update_password as _update_password
from vmraid.utils.user import get_system_managers
from vmraid.website.utils import is_signup_disabled

STANDARD_USERS = vmraid.STANDARD_USERS


class User(Document):
	__new_password = None

	def __setup__(self):
		# because it is handled separately
		self.flags.ignore_save_passwords = ["new_password"]

	def autoname(self):
		"""set name as Email Address"""
		if self.get("is_admin") or self.get("is_guest"):
			self.name = self.first_name
		else:
			self.email = self.email.strip().lower()
			self.name = self.email

	def onload(self):
		from vmraid.config import get_modules_from_all_apps

		self.set_onload("all_modules", [m.get("module_name") for m in get_modules_from_all_apps()])

	def before_insert(self):
		self.flags.in_insert = True
		throttle_user_creation()

	def after_insert(self):
		create_notification_settings(self.name)
		vmraid.cache().delete_key("users_for_mentions")
		vmraid.cache().delete_key("enabled_users")

	def validate(self):
		# clear new password
		self.__new_password = self.new_password
		self.new_password = ""

		if not vmraid.flags.in_test:
			self.password_strength_test()

		if self.name not in STANDARD_USERS:
			self.validate_email_type(self.email)
			self.validate_email_type(self.name)
		self.add_system_manager_role()
		self.set_system_user()
		self.set_full_name()
		self.check_enable_disable()
		self.ensure_unique_roles()
		self.remove_all_roles_for_guest()
		self.validate_username()
		self.remove_disabled_roles()
		self.validate_user_email_inbox()
		ask_pass_update()
		self.validate_roles()
		self.validate_allowed_modules()
		self.validate_user_image()
		self.set_time_zone()

		if self.language == "Loading...":
			self.language = None

		if (self.name not in ["Administrator", "Guest"]) and (
			not self.get_social_login_userid("vmraid")
		):
			self.set_social_login_userid("vmraid", vmraid.generate_hash(length=39))

	def validate_roles(self):
		if self.role_profile_name:
			role_profile = vmraid.get_doc("Role Profile", self.role_profile_name)
			self.set("roles", [])
			self.append_roles(*[role.role for role in role_profile.roles])

	def validate_allowed_modules(self):
		if self.module_profile:
			module_profile = vmraid.get_doc("Module Profile", self.module_profile)
			self.set("block_modules", [])
			for d in module_profile.get("block_modules"):
				self.append("block_modules", {"module": d.module})

	def validate_user_image(self):
		if self.user_image and len(self.user_image) > 2000:
			vmraid.throw(_("Not a valid User Image."))

	def on_update(self):
		# clear new password
		self.share_with_self()
		clear_notifications(user=self.name)
		vmraid.clear_cache(user=self.name)
		now = vmraid.flags.in_test or vmraid.flags.in_install
		self.send_password_notification(self.__new_password)
		vmraid.enqueue(
			"vmraid.core.doctype.user.user.create_contact", user=self, ignore_mandatory=True, now=now
		)
		if self.name not in ("Administrator", "Guest") and not self.user_image:
			vmraid.enqueue("vmraid.core.doctype.user.user.update_gravatar", name=self.name, now=now)

		# Set user selected timezone
		if self.time_zone:
			vmraid.defaults.set_default("time_zone", self.time_zone, self.name)

		if self.has_value_changed("allow_in_mentions") or self.has_value_changed("user_type"):
			vmraid.cache().delete_key("users_for_mentions")

		if self.has_value_changed("enabled"):
			vmraid.cache().delete_key("enabled_users")

	def has_website_permission(self, ptype, user, verbose=False):
		"""Returns true if current user is the session user"""
		return self.name == vmraid.session.user

	def set_full_name(self):
		self.full_name = " ".join(filter(None, [self.first_name, self.last_name]))

	def check_enable_disable(self):
		# do not allow disabling administrator/guest
		if not cint(self.enabled) and self.name in STANDARD_USERS:
			vmraid.throw(_("User {0} cannot be disabled").format(self.name))

		if not cint(self.enabled):
			self.a_system_manager_should_exist()

		# clear sessions if disabled
		if not cint(self.enabled) and getattr(vmraid.local, "login_manager", None):
			vmraid.local.login_manager.logout(user=self.name)

		# toggle notifications based on the user's status
		toggle_notifications(self.name, enable=cint(self.enabled))

	def add_system_manager_role(self):
		# if adding system manager, do nothing
		if not cint(self.enabled) or (
			"System Manager" in [user_role.role for user_role in self.get("roles")]
		):
			return

		if (
			self.name not in STANDARD_USERS
			and self.user_type == "System User"
			and not self.get_other_system_managers()
			and cint(vmraid.db.get_single_value("System Settings", "setup_complete"))
		):

			msgprint(_("Adding System Manager to this User as there must be atleast one System Manager"))
			self.append("roles", {"doctype": "Has Role", "role": "System Manager"})

		if self.name == "Administrator":
			# Administrator should always have System Manager Role
			self.extend(
				"roles",
				[
					{"doctype": "Has Role", "role": "System Manager"},
					{"doctype": "Has Role", "role": "Administrator"},
				],
			)

	def email_new_password(self, new_password=None):
		if new_password and not self.flags.in_insert:
			_update_password(user=self.name, pwd=new_password, logout_all_sessions=self.logout_all_sessions)

	def set_system_user(self):
		"""For the standard users like admin and guest, the user type is fixed."""
		user_type_mapper = {"Administrator": "System User", "Guest": "Website User"}

		if self.user_type and not vmraid.get_cached_value("User Type", self.user_type, "is_standard"):
			if user_type_mapper.get(self.name):
				self.user_type = user_type_mapper.get(self.name)
			else:
				self.set_roles_and_modules_based_on_user_type()
		else:
			"""Set as System User if any of the given roles has desk_access"""
			self.user_type = "System User" if self.has_desk_access() else "Website User"

	def set_roles_and_modules_based_on_user_type(self):
		user_type_doc = vmraid.get_cached_doc("User Type", self.user_type)
		if user_type_doc.role:
			self.roles = []

			# Check whether User has linked with the 'Apply User Permission On' doctype or not
			if user_linked_with_permission_on_doctype(user_type_doc, self.name):
				self.append("roles", {"role": user_type_doc.role})

				vmraid.msgprint(
					_("Role has been set as per the user type {0}").format(self.user_type), alert=True
				)

		user_type_doc.update_modules_in_user(self)

	def has_desk_access(self):
		"""Return true if any of the set roles has desk access"""
		if not self.roles:
			return False

		role_table = DocType("Role")
		return vmraid.db.count(
			role_table,
			((role_table.desk_access == 1) & (role_table.name.isin([d.role for d in self.roles]))),
		)

	def share_with_self(self):
		vmraid.share.add(
			self.doctype, self.name, self.name, write=1, share=1, flags={"ignore_share_permission": True}
		)

	def validate_share(self, docshare):
		pass
		# if docshare.user == self.name:
		# 	if self.user_type=="System User":
		# 		if docshare.share != 1:
		# 			vmraid.throw(_("Sorry! User should have complete access to their own record."))
		# 	else:
		# 		vmraid.throw(_("Sorry! Sharing with Website User is prohibited."))

	def send_password_notification(self, new_password):
		try:
			if self.flags.in_insert:
				if self.name not in STANDARD_USERS:
					if new_password:
						# new password given, no email required
						_update_password(
							user=self.name, pwd=new_password, logout_all_sessions=self.logout_all_sessions
						)

					if not self.flags.no_welcome_mail and cint(self.send_welcome_email):
						self.send_welcome_mail_to_user()
						self.flags.email_sent = 1
						if vmraid.session.user != "Guest":
							msgprint(_("Welcome email sent"))
						return
			else:
				self.email_new_password(new_password)

		except vmraid.OutgoingEmailError:
			# email server not set, don't send email
			vmraid.log_error(vmraid.get_traceback())

	@Document.hook
	def validate_reset_password(self):
		pass

	def reset_password(self, send_email=False, password_expired=False):
		from vmraid.utils import get_url, random_string

		key = random_string(32)
		self.db_set("reset_password_key", key)

		url = "/update-password?key=" + key
		if password_expired:
			url = "/update-password?key=" + key + "&password_expired=true"

		link = get_url(url)
		if send_email:
			self.password_reset_mail(link)

		return link

	def get_other_system_managers(self):
		user_doctype = DocType("User").as_("user")
		user_role_doctype = DocType("Has Role").as_("user_role")
		return (
			vmraid.qb.from_(user_doctype)
			.from_(user_role_doctype)
			.select(user_doctype.name)
			.where(user_role_doctype.role == "System Manager")
			.where(user_doctype.docstatus < 2)
			.where(user_doctype.enabled == 1)
			.where(user_role_doctype.parent == user_doctype.name)
			.where(user_role_doctype.parent.notin(["Administrator", self.name]))
			.limit(1)
			.distinct()
		).run()

	def get_fullname(self):
		"""get first_name space last_name"""
		return (self.first_name or "") + (self.first_name and " " or "") + (self.last_name or "")

	def password_reset_mail(self, link):
		self.send_login_mail(_("Password Reset"), "password_reset", {"link": link}, now=True)

	def send_welcome_mail_to_user(self):
		from vmraid.utils import get_url

		link = self.reset_password()
		subject = None
		method = vmraid.get_hooks("welcome_email")
		if method:
			subject = vmraid.get_attr(method[-1])()
		if not subject:
			site_name = vmraid.db.get_default("site_name") or vmraid.get_conf().get("site_name")
			if site_name:
				subject = _("Welcome to {0}").format(site_name)
			else:
				subject = _("Complete Registration")

		self.send_login_mail(
			subject,
			"new_user",
			dict(
				link=link,
				site_url=get_url(),
			),
		)

	def send_login_mail(self, subject, template, add_args, now=None):
		"""send mail with login details"""
		from vmraid.utils import get_url
		from vmraid.utils.user import get_user_fullname

		created_by = get_user_fullname(vmraid.session["user"])
		if created_by == "Guest":
			created_by = "Administrator"

		args = {
			"first_name": self.first_name or self.last_name or "user",
			"user": self.name,
			"title": subject,
			"login_url": get_url(),
			"created_by": created_by,
		}

		args.update(add_args)

		sender = (
			vmraid.session.user not in STANDARD_USERS and get_formatted_email(vmraid.session.user) or None
		)

		vmraid.sendmail(
			recipients=self.email,
			sender=sender,
			subject=subject,
			template=template,
			args=args,
			header=[subject, "green"],
			delayed=(not now) if now is not None else self.flags.delay_emails,
			retry=3,
		)

	def a_system_manager_should_exist(self):
		if not self.get_other_system_managers():
			throw(_("There should remain at least one System Manager"))

	def on_trash(self):
		vmraid.clear_cache(user=self.name)
		if self.name in STANDARD_USERS:
			throw(_("User {0} cannot be deleted").format(self.name))

		self.a_system_manager_should_exist()

		# disable the user and log him/her out
		self.enabled = 0
		if getattr(vmraid.local, "login_manager", None):
			vmraid.local.login_manager.logout(user=self.name)

		# delete todos
		vmraid.db.delete("ToDo", {"allocated_to": self.name})
		todo_table = DocType("ToDo")
		(
			vmraid.qb.update(todo_table)
			.set(todo_table.assigned_by, None)
			.where(todo_table.assigned_by == self.name)
		).run()

		# delete events
		vmraid.db.delete("Event", {"owner": self.name, "event_type": "Private"})

		# delete shares
		vmraid.db.delete("DocShare", {"user": self.name})
		# delete messages
		table = DocType("Communication")
		vmraid.db.delete(
			table,
			filters=(
				(table.communication_type.isin(["Chat", "Notification"]))
				& (table.reference_doctype == "User")
				& ((table.reference_name == self.name) | table.owner == self.name)
			),
			run=False,
		)
		# unlink contact
		table = DocType("Contact")
		vmraid.qb.update(table).where(table.user == self.name).set(table.user, None).run()

		# delete notification settings
		vmraid.delete_doc("Notification Settings", self.name, ignore_permissions=True)

		if self.get("allow_in_mentions"):
			vmraid.cache().delete_key("users_for_mentions")

		vmraid.cache().delete_key("enabled_users")

	def before_rename(self, old_name, new_name, merge=False):
		vmraid.clear_cache(user=old_name)
		self.validate_rename(old_name, new_name)

	def validate_rename(self, old_name, new_name):
		# do not allow renaming administrator and guest
		if old_name in STANDARD_USERS:
			throw(_("User {0} cannot be renamed").format(self.name))

		self.validate_email_type(new_name)

	def validate_email_type(self, email):
		from vmraid.utils import validate_email_address

		validate_email_address(email.strip(), True)

	def after_rename(self, old_name, new_name, merge=False):
		tables = vmraid.db.get_tables()
		for tab in tables:
			desc = vmraid.db.get_table_columns_description(tab)
			has_fields = []
			for d in desc:
				if d.get("name") in ["owner", "modified_by"]:
					has_fields.append(d.get("name"))
			for field in has_fields:
				vmraid.db.sql(
					"""UPDATE `%s`
					SET `%s` = %s
					WHERE `%s` = %s"""
					% (tab, field, "%s", field, "%s"),
					(new_name, old_name),
				)

		if vmraid.db.exists("Notification Settings", old_name):
			vmraid.rename_doc("Notification Settings", old_name, new_name, force=True, show_alert=False)

		# set email
		vmraid.db.update("User", new_name, "email", new_name)

	def append_roles(self, *roles):
		"""Add roles to user"""
		current_roles = [d.role for d in self.get("roles")]
		for role in roles:
			if role in current_roles:
				continue
			self.append("roles", {"role": role})

	def add_roles(self, *roles):
		"""Add roles to user and save"""
		self.append_roles(*roles)
		self.save()

	def remove_roles(self, *roles):
		existing_roles = dict((d.role, d) for d in self.get("roles"))
		for role in roles:
			if role in existing_roles:
				self.get("roles").remove(existing_roles[role])

		self.save()

	def remove_all_roles_for_guest(self):
		if self.name == "Guest":
			self.set("roles", list(set(d for d in self.get("roles") if d.role == "Guest")))

	def remove_disabled_roles(self):
		disabled_roles = [d.name for d in vmraid.get_all("Role", filters={"disabled": 1})]
		for role in list(self.get("roles")):
			if role.role in disabled_roles:
				self.get("roles").remove(role)

	def ensure_unique_roles(self):
		exists = []
		for i, d in enumerate(self.get("roles")):
			if (not d.role) or (d.role in exists):
				self.get("roles").remove(d)
			else:
				exists.append(d.role)

	def validate_username(self):
		if not self.username and self.is_new() and self.first_name:
			self.username = vmraid.scrub(self.first_name)

		if not self.username:
			return

		# strip space and @
		self.username = self.username.strip(" @")

		if self.username_exists():
			if self.user_type == "System User":
				vmraid.msgprint(_("Username {0} already exists").format(self.username))
				self.suggest_username()

			self.username = ""

	def password_strength_test(self):
		"""test password strength"""
		if self.flags.ignore_password_policy:
			return

		if self.__new_password:
			user_data = (self.first_name, self.middle_name, self.last_name, self.email, self.birth_date)
			result = test_password_strength(self.__new_password, "", None, user_data)
			feedback = result.get("feedback", None)

			if feedback and not feedback.get("password_policy_validation_passed", False):
				handle_password_test_fail(result)

	def suggest_username(self):
		def _check_suggestion(suggestion):
			if self.username != suggestion and not self.username_exists(suggestion):
				return suggestion

			return None

		# @firstname
		username = _check_suggestion(vmraid.scrub(self.first_name))

		if not username:
			# @firstname_last_name
			username = _check_suggestion(
				vmraid.scrub("{0} {1}".format(self.first_name, self.last_name or ""))
			)

		if username:
			vmraid.msgprint(_("Suggested Username: {0}").format(username))

		return username

	def username_exists(self, username=None):
		return vmraid.db.get_value(
			"User", {"username": username or self.username, "name": ("!=", self.name)}
		)

	def get_blocked_modules(self):
		"""Returns list of modules blocked for that user"""
		return [d.module for d in self.block_modules] if self.block_modules else []

	def validate_user_email_inbox(self):
		"""check if same email account added in User Emails twice"""

		email_accounts = [user_email.email_account for user_email in self.user_emails]
		if len(email_accounts) != len(set(email_accounts)):
			vmraid.throw(_("Email Account added multiple times"))

	def get_social_login_userid(self, provider):
		try:
			for p in self.social_logins:
				if p.provider == provider:
					return p.userid
		except:
			return None

	def set_social_login_userid(self, provider, userid, username=None):
		social_logins = {"provider": provider, "userid": userid}

		if username:
			social_logins["username"] = username

		self.append("social_logins", social_logins)

	def get_restricted_ip_list(self):
		if not self.restrict_ip:
			return

		return [i.strip() for i in self.restrict_ip.split(",")]

	@classmethod
	def find_by_credentials(cls, user_name: str, password: str, validate_password: bool = True):
		"""Find the user by credentials.

		This is a login utility that needs to check login related system settings while finding the user.
		1. Find user by email ID by default
		2. If allow_login_using_mobile_number is set, you can use mobile number while finding the user.
		3. If allow_login_using_user_name is set, you can use username while finding the user.
		"""

		login_with_mobile = cint(
			vmraid.db.get_value("System Settings", "System Settings", "allow_login_using_mobile_number")
		)
		login_with_username = cint(
			vmraid.db.get_value("System Settings", "System Settings", "allow_login_using_user_name")
		)

		or_filters = [{"name": user_name}]
		if login_with_mobile:
			or_filters.append({"mobile_no": user_name})
		if login_with_username:
			or_filters.append({"username": user_name})

		users = vmraid.db.get_all("User", fields=["name", "enabled"], or_filters=or_filters, limit=1)
		if not users:
			return

		user = users[0]
		user["is_authenticated"] = True
		if validate_password:
			try:
				check_password(user["name"], password, delete_tracker_cache=False)
			except vmraid.AuthenticationError:
				user["is_authenticated"] = False

		return user

	def set_time_zone(self):
		if not self.time_zone:
			self.time_zone = get_time_zone()


@vmraid.whitelist()
def get_timezones():
	import pytz

	return {"timezones": pytz.all_timezones}


@vmraid.whitelist()
def get_all_roles(arg=None):
	"""return all roles"""
	active_domains = vmraid.get_active_domains()

	roles = vmraid.get_all(
		"Role",
		filters={"name": ("not in", "Administrator,Guest,All"), "disabled": 0},
		or_filters={"ifnull(restrict_to_domain, '')": "", "restrict_to_domain": ("in", active_domains)},
		order_by="name",
	)

	return [role.get("name") for role in roles]


@vmraid.whitelist()
def get_roles(arg=None):
	"""get roles for a user"""
	return vmraid.get_roles(vmraid.form_dict["uid"])


@vmraid.whitelist()
def get_perm_info(role):
	"""get permission info"""
	from vmraid.permissions import get_all_perms

	return get_all_perms(role)


@vmraid.whitelist(allow_guest=True)
def update_password(new_password, logout_all_sessions=0, key=None, old_password=None):
	# validate key to avoid key input like ['like', '%'], '', ['in', ['']]
	if key and not isinstance(key, str):
		vmraid.throw(_("Invalid key type"))

	result = test_password_strength(new_password, key, old_password)
	feedback = result.get("feedback", None)

	if feedback and not feedback.get("password_policy_validation_passed", False):
		handle_password_test_fail(result)

	res = _get_user_for_update_password(key, old_password)
	if res.get("message"):
		vmraid.local.response.http_status_code = 410
		return res["message"]
	else:
		user = res["user"]

	logout_all_sessions = cint(logout_all_sessions) or vmraid.db.get_single_value(
		"System Settings", "logout_on_password_reset"
	)
	_update_password(user, new_password, logout_all_sessions=cint(logout_all_sessions))

	user_doc, redirect_url = reset_user_data(user)

	# get redirect url from cache
	redirect_to = vmraid.cache().hget("redirect_after_login", user)
	if redirect_to:
		redirect_url = redirect_to
		vmraid.cache().hdel("redirect_after_login", user)

	vmraid.local.login_manager.login_as(user)

	vmraid.db.set_value("User", user, "last_password_reset_date", today())
	vmraid.db.set_value("User", user, "reset_password_key", "")

	if user_doc.user_type == "System User":
		return "/app"
	else:
		return redirect_url if redirect_url else "/"


@vmraid.whitelist(allow_guest=True)
def test_password_strength(new_password, key=None, old_password=None, user_data=None):
	from vmraid.utils.password_strength import test_password_strength as _test_password_strength

	password_policy = (
		vmraid.db.get_value(
			"System Settings", None, ["enable_password_policy", "minimum_password_score"], as_dict=True
		)
		or {}
	)

	enable_password_policy = cint(password_policy.get("enable_password_policy", 0))
	minimum_password_score = cint(password_policy.get("minimum_password_score", 0))

	if not enable_password_policy:
		return {}

	if not user_data:
		user_data = vmraid.db.get_value(
			"User", vmraid.session.user, ["first_name", "middle_name", "last_name", "email", "birth_date"]
		)

	if new_password:
		result = _test_password_strength(new_password, user_inputs=user_data)
		password_policy_validation_passed = False

		# score should be greater than 0 and minimum_password_score
		if result.get("score") and result.get("score") >= minimum_password_score:
			password_policy_validation_passed = True

		result["feedback"]["password_policy_validation_passed"] = password_policy_validation_passed
		return result


# for login
@vmraid.whitelist()
def has_email_account(email):
	return vmraid.get_list("Email Account", filters={"email_id": email})


@vmraid.whitelist(allow_guest=False)
def get_email_awaiting(user):
	waiting = vmraid.get_all(
		"User Email",
		fields=["email_account", "email_id"],
		filters={"awaiting_password": 1, "parent": user},
	)
	if waiting:
		return waiting
	else:
		user_email_table = DocType("User Email")
		vmraid.qb.update(user_email_table).set(user_email_table.user_email_table, 0).where(
			user_email_table.parent == user
		).run()
		return False


def ask_pass_update():
	# update the sys defaults as to awaiting users
	from vmraid.utils import set_default

	password_list = vmraid.get_all(
		"User Email", filters={"awaiting_password": True}, pluck="parent", distinct=True
	)
	set_default("email_user_password", ",".join(password_list))


def _get_user_for_update_password(key, old_password):
	# verify old password
	result = vmraid._dict()
	if key:
		result.user = vmraid.db.get_value("User", {"reset_password_key": key})
		if not result.user:
			result.message = _("The Link specified has either been used before or Invalid")

	elif old_password:
		# verify old password
		vmraid.local.login_manager.check_password(vmraid.session.user, old_password)
		user = vmraid.session.user
		result.user = user

	return result


def reset_user_data(user):
	user_doc = vmraid.get_doc("User", user)
	redirect_url = user_doc.redirect_url
	user_doc.reset_password_key = ""
	user_doc.redirect_url = ""
	user_doc.save(ignore_permissions=True)

	return user_doc, redirect_url


@vmraid.whitelist()
def verify_password(password):
	vmraid.local.login_manager.check_password(vmraid.session.user, password)


@vmraid.whitelist(allow_guest=True)
def sign_up(email, full_name, redirect_to):
	if is_signup_disabled():
		vmraid.throw(_("Sign Up is disabled"), title=_("Not Allowed"))

	user = vmraid.db.get("User", {"email": email})
	if user:
		if user.enabled:
			return 0, _("Already Registered")
		else:
			return 0, _("Registered but disabled")
	else:
		if vmraid.db.get_creation_count("User", 60) > 300:
			vmraid.respond_as_web_page(
				_("Temporarily Disabled"),
				_(
					"Too many users signed up recently, so the registration is disabled. Please try back in an hour"
				),
				http_status_code=429,
			)

		from vmraid.utils import random_string

		user = vmraid.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": escape_html(full_name),
				"enabled": 1,
				"new_password": random_string(10),
				"user_type": "Website User",
			}
		)
		user.flags.ignore_permissions = True
		user.flags.ignore_password_policy = True
		user.insert()

		# set default signup role as per Portal Settings
		default_role = vmraid.db.get_value("Portal Settings", None, "default_role")
		if default_role:
			user.add_roles(default_role)

		if redirect_to:
			vmraid.cache().hset("redirect_after_login", user.name, redirect_to)

		if user.flags.email_sent:
			return 1, _("Please check your email for verification")
		else:
			return 2, _("Please ask your administrator to verify your sign-up")


@vmraid.whitelist(allow_guest=True)
@rate_limit(limit=get_password_reset_limit, seconds=24 * 60 * 60, methods=["POST"])
def reset_password(user):
	if user == "Administrator":
		return "not allowed"

	try:
		user = vmraid.get_doc("User", user)
		if not user.enabled:
			return "disabled"

		user.validate_reset_password()
		user.reset_password(send_email=True)

		return vmraid.msgprint(
			msg=_("Password reset instructions have been sent to your email"),
			title=_("Password Email Sent"),
		)
	except vmraid.DoesNotExistError:
		vmraid.local.response["http_status_code"] = 400
		vmraid.clear_messages()
		return "not found"


@vmraid.whitelist()
@vmraid.validate_and_sanitize_search_inputs
def user_query(doctype, txt, searchfield, start, page_len, filters):
	from vmraid.desk.reportview import get_filters_cond, get_match_cond

	conditions = []

	user_type_condition = "and user_type != 'Website User'"
	if filters and filters.get("ignore_user_type"):
		user_type_condition = ""
		filters.pop("ignore_user_type")

	txt = "%{}%".format(txt)
	return vmraid.db.sql(
		"""SELECT `name`, CONCAT_WS(' ', first_name, middle_name, last_name)
		FROM `tabUser`
		WHERE `enabled`=1
			{user_type_condition}
			AND `docstatus` < 2
			AND `name` NOT IN ({standard_users})
			AND ({key} LIKE %(txt)s
				OR CONCAT_WS(' ', first_name, middle_name, last_name) LIKE %(txt)s)
			{fcond} {mcond}
		ORDER BY
			CASE WHEN `name` LIKE %(txt)s THEN 0 ELSE 1 END,
			CASE WHEN concat_ws(' ', first_name, middle_name, last_name) LIKE %(txt)s
				THEN 0 ELSE 1 END,
			NAME asc
		LIMIT %(page_len)s OFFSET %(start)s
	""".format(
			user_type_condition=user_type_condition,
			standard_users=", ".join(vmraid.db.escape(u) for u in STANDARD_USERS),
			key=searchfield,
			fcond=get_filters_cond(doctype, filters, conditions),
			mcond=get_match_cond(doctype),
		),
		dict(start=start, page_len=page_len, txt=txt),
	)


def get_total_users():
	"""Returns total no. of system users"""
	return flt(
		vmraid.db.sql(
			"""SELECT SUM(`simultaneous_sessions`)
		FROM `tabUser`
		WHERE `enabled` = 1
		AND `user_type` = 'System User'
		AND `name` NOT IN ({})""".format(
				", ".join(["%s"] * len(STANDARD_USERS))
			),
			STANDARD_USERS,
		)[0][0]
	)


def get_system_users(exclude_users=None, limit=None):
	if not exclude_users:
		exclude_users = []
	elif not isinstance(exclude_users, (list, tuple)):
		exclude_users = [exclude_users]

	limit_cond = ""
	if limit:
		limit_cond = "limit {0}".format(limit)

	exclude_users += list(STANDARD_USERS)

	system_users = vmraid.db.sql_list(
		"""select name from `tabUser`
		where enabled=1 and user_type != 'Website User'
		and name not in ({}) {}""".format(
			", ".join(["%s"] * len(exclude_users)), limit_cond
		),
		exclude_users,
	)

	return system_users


def get_active_users():
	"""Returns No. of system users who logged in, in the last 3 days"""
	return vmraid.db.sql(
		"""select count(*) from `tabUser`
		where enabled = 1 and user_type != 'Website User'
		and name not in ({})
		and hour(timediff(now(), last_active)) < 72""".format(
			", ".join(["%s"] * len(STANDARD_USERS))
		),
		STANDARD_USERS,
	)[0][0]


def get_website_users():
	"""Returns total no. of website users"""
	return vmraid.db.count("User", filters={"enabled": True, "user_type": "Website User"})


def get_active_website_users():
	"""Returns No. of website users who logged in, in the last 3 days"""
	return vmraid.db.sql(
		"""select count(*) from `tabUser`
		where enabled = 1 and user_type = 'Website User'
		and hour(timediff(now(), last_active)) < 72"""
	)[0][0]


def get_permission_query_conditions(user):
	if user == "Administrator":
		return ""
	else:
		return """(`tabUser`.name not in ({standard_users}))""".format(
			standard_users=", ".join(vmraid.db.escape(user) for user in STANDARD_USERS)
		)


def has_permission(doc, user):
	if (user != "Administrator") and (doc.name in STANDARD_USERS):
		# dont allow non Administrator user to view / edit Administrator user
		return False


def notify_admin_access_to_system_manager(login_manager=None):
	if (
		login_manager
		and login_manager.user == "Administrator"
		and vmraid.local.conf.notify_admin_access_to_system_manager
	):

		site = '<a href="{0}" target="_blank">{0}</a>'.format(vmraid.local.request.host_url)
		date_and_time = "<b>{0}</b>".format(format_datetime(now_datetime(), format_string="medium"))
		ip_address = vmraid.local.request_ip

		access_message = _("Administrator accessed {0} on {1} via IP Address {2}.").format(
			site, date_and_time, ip_address
		)

		vmraid.sendmail(
			recipients=get_system_managers(),
			subject=_("Administrator Logged In"),
			template="administrator_logged_in",
			args={"access_message": access_message},
			header=["Access Notification", "orange"],
		)


def extract_mentions(txt):
	"""Find all instances of @mentions in the html."""
	soup = BeautifulSoup(txt, "html.parser")
	emails = []
	for mention in soup.find_all(class_="mention"):
		if mention.get("data-is-group") == "true":
			try:
				user_group = vmraid.get_cached_doc("User Group", mention["data-id"])
				emails += [d.user for d in user_group.user_group_members]
			except vmraid.DoesNotExistError:
				pass
			continue
		email = mention["data-id"]
		emails.append(email)

	return emails


def handle_password_test_fail(result):
	suggestions = result["feedback"]["suggestions"][0] if result["feedback"]["suggestions"] else ""
	warning = result["feedback"]["warning"] if "warning" in result["feedback"] else ""
	suggestions += (
		"<br>" + _("Hint: Include symbols, numbers and capital letters in the password") + "<br>"
	)
	vmraid.throw(" ".join([_("Invalid Password:"), warning, suggestions]))


def update_gravatar(name):
	gravatar = has_gravatar(name)
	if gravatar:
		vmraid.db.set_value("User", name, "user_image", gravatar)


def throttle_user_creation():
	if vmraid.flags.in_import:
		return

	if vmraid.db.get_creation_count("User", 60) > vmraid.local.conf.get("throttle_user_limit", 60):
		vmraid.throw(_("Throttled"))


@vmraid.whitelist()
def get_role_profile(role_profile):
	roles = vmraid.get_doc("Role Profile", {"role_profile": role_profile})
	return roles.roles


@vmraid.whitelist()
def get_module_profile(module_profile):
	module_profile = vmraid.get_doc("Module Profile", {"module_profile_name": module_profile})
	return module_profile.get("block_modules")


def create_contact(user, ignore_links=False, ignore_mandatory=False):
	from vmraid.contacts.doctype.contact.contact import get_contact_name

	if user.name in ["Administrator", "Guest"]:
		return

	contact_name = get_contact_name(user.email)
	if not contact_name:
		contact = vmraid.get_doc(
			{
				"doctype": "Contact",
				"first_name": user.first_name,
				"last_name": user.last_name,
				"user": user.name,
				"gender": user.gender,
			}
		)

		if user.email:
			contact.add_email(user.email, is_primary=True)

		if user.phone:
			contact.add_phone(user.phone, is_primary_phone=True)

		if user.mobile_no:
			contact.add_phone(user.mobile_no, is_primary_mobile_no=True)
		contact.insert(
			ignore_permissions=True, ignore_links=ignore_links, ignore_mandatory=ignore_mandatory
		)
	else:
		contact = vmraid.get_doc("Contact", contact_name)
		contact.first_name = user.first_name
		contact.last_name = user.last_name
		contact.gender = user.gender

		# Add mobile number if phone does not exists in contact
		if user.phone and not any(new_contact.phone == user.phone for new_contact in contact.phone_nos):
			# Set primary phone if there is no primary phone number
			contact.add_phone(
				user.phone,
				is_primary_phone=not any(
					new_contact.is_primary_phone == 1 for new_contact in contact.phone_nos
				),
			)

		# Add mobile number if mobile does not exists in contact
		if user.mobile_no and not any(
			new_contact.phone == user.mobile_no for new_contact in contact.phone_nos
		):
			# Set primary mobile if there is no primary mobile number
			contact.add_phone(
				user.mobile_no,
				is_primary_mobile_no=not any(
					new_contact.is_primary_mobile_no == 1 for new_contact in contact.phone_nos
				),
			)

		contact.save(ignore_permissions=True)


@vmraid.whitelist()
def generate_keys(user):
	"""
	generate api key and api secret

	:param user: str
	"""
	vmraid.only_for("System Manager")
	user_details = vmraid.get_doc("User", user)
	api_secret = vmraid.generate_hash(length=15)
	# if api key is not set generate api key
	if not user_details.api_key:
		api_key = vmraid.generate_hash(length=15)
		user_details.api_key = api_key
	user_details.api_secret = api_secret
	user_details.save()

	return {"api_secret": api_secret}


@vmraid.whitelist()
def switch_theme(theme):
	if theme in ["Dark", "Light", "Automatic"]:
		vmraid.db.set_value("User", vmraid.session.user, "desk_theme", theme)


def get_enabled_users():
	def _get_enabled_users():
		enabled_users = vmraid.get_all("User", filters={"enabled": "1"}, pluck="name")
		return enabled_users

	return vmraid.cache().get_value("enabled_users", _get_enabled_users)
