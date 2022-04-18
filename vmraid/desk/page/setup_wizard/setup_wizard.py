# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import json
import os

import vmraid
from vmraid.geo.country_info import get_country_info
from vmraid.translate import get_dict, send_translations, set_default_language
from vmraid.utils import cint, strip
from vmraid.utils.password import update_password

from . import install_fixtures


def get_setup_stages(args):

	# App setup stage functions should not include vmraid.db.commit
	# That is done by vmraid after successful completion of all stages
	stages = [
		{
			"status": "Updating global settings",
			"fail_msg": "Failed to update global settings",
			"tasks": [
				{"fn": update_global_settings, "args": args, "fail_msg": "Failed to update global settings"}
			],
		}
	]

	stages += get_stages_hooks(args) + get_setup_complete_hooks(args)

	stages.append(
		{
			# post executing hooks
			"status": "Wrapping up",
			"fail_msg": "Failed to complete setup",
			"tasks": [
				{"fn": run_post_setup_complete, "args": args, "fail_msg": "Failed to complete setup"}
			],
		}
	)

	return stages


@vmraid.whitelist()
def setup_complete(args):
	"""Calls hooks for `setup_wizard_complete`, sets home page as `desktop`
	and clears cache. If wizard breaks, calls `setup_wizard_exception` hook"""

	# Setup complete: do not throw an exception, let the user continue to desk
	if cint(vmraid.db.get_single_value("System Settings", "setup_complete")):
		return {"status": "ok"}

	args = parse_args(args)
	stages = get_setup_stages(args)
	is_background_task = vmraid.conf.get("trigger_site_setup_in_background")

	if is_background_task:
		process_setup_stages.enqueue(stages=stages, user_input=args, is_background_task=True)
		return {"status": "registered"}
	else:
		return process_setup_stages(stages, args)


@vmraid.task()
def process_setup_stages(stages, user_input, is_background_task=False):
	try:
		vmraid.flags.in_setup_wizard = True
		current_task = None
		for idx, stage in enumerate(stages):
			vmraid.publish_realtime(
				"setup_task",
				{"progress": [idx, len(stages)], "stage_status": stage.get("status")},
				user=vmraid.session.user,
			)

			for task in stage.get("tasks"):
				current_task = task
				task.get("fn")(task.get("args"))
	except Exception:
		handle_setup_exception(user_input)
		if not is_background_task:
			return {"status": "fail", "fail": current_task.get("fail_msg")}
		vmraid.publish_realtime(
			"setup_task",
			{"status": "fail", "fail_msg": current_task.get("fail_msg")},
			user=vmraid.session.user,
		)
	else:
		run_setup_success(user_input)
		if not is_background_task:
			return {"status": "ok"}
		vmraid.publish_realtime("setup_task", {"status": "ok"}, user=vmraid.session.user)
	finally:
		vmraid.flags.in_setup_wizard = False


def update_global_settings(args):
	if args.language and args.language != "English":
		set_default_language(get_language_code(args.lang))
		vmraid.db.commit()
	vmraid.clear_cache()

	update_system_settings(args)
	update_user_name(args)


def run_post_setup_complete(args):
	disable_future_access()
	vmraid.db.commit()
	vmraid.clear_cache()


def run_setup_success(args):
	for hook in vmraid.get_hooks("setup_wizard_success"):
		vmraid.get_attr(hook)(args)
	install_fixtures.install()


def get_stages_hooks(args):
	stages = []
	for method in vmraid.get_hooks("setup_wizard_stages"):
		stages += vmraid.get_attr(method)(args)
	return stages


def get_setup_complete_hooks(args):
	stages = []
	for method in vmraid.get_hooks("setup_wizard_complete"):
		stages.append(
			{
				"status": "Executing method",
				"fail_msg": "Failed to execute method",
				"tasks": [
					{"fn": vmraid.get_attr(method), "args": args, "fail_msg": "Failed to execute method"}
				],
			}
		)
	return stages


def handle_setup_exception(args):
	vmraid.db.rollback()
	if args:
		traceback = vmraid.get_traceback()
		print(traceback)
		for hook in vmraid.get_hooks("setup_wizard_exception"):
			vmraid.get_attr(hook)(traceback, args)


def update_system_settings(args):
	number_format = get_country_info(args.get("country")).get("number_format", "#,###.##")

	# replace these as float number formats, as they have 0 precision
	# and are currency number formats and not for floats
	if number_format == "#.###":
		number_format = "#.###,##"
	elif number_format == "#,###":
		number_format = "#,###.##"

	system_settings = vmraid.get_doc("System Settings", "System Settings")
	system_settings.update(
		{
			"country": args.get("country"),
			"language": get_language_code(args.get("language")) or "en",
			"time_zone": args.get("timezone"),
			"float_precision": 3,
			"date_format": vmraid.db.get_value("Country", args.get("country"), "date_format"),
			"time_format": vmraid.db.get_value("Country", args.get("country"), "time_format"),
			"number_format": number_format,
			"enable_scheduler": 1 if not vmraid.flags.in_test else 0,
			"backup_limit": 3,  # Default for downloadable backups
		}
	)
	system_settings.save()


def update_user_name(args):
	first_name, last_name = args.get("full_name", ""), ""
	if " " in first_name:
		first_name, last_name = first_name.split(" ", 1)

	if args.get("email"):
		if vmraid.db.exists("User", args.get("email")):
			# running again
			return

		args["name"] = args.get("email")

		_mute_emails, vmraid.flags.mute_emails = vmraid.flags.mute_emails, True
		doc = vmraid.get_doc(
			{
				"doctype": "User",
				"email": args.get("email"),
				"first_name": first_name,
				"last_name": last_name,
			}
		)
		doc.flags.no_welcome_mail = True
		doc.insert()
		vmraid.flags.mute_emails = _mute_emails
		update_password(args.get("email"), args.get("password"))

	elif first_name:
		args.update({"name": vmraid.session.user, "first_name": first_name, "last_name": last_name})

		vmraid.db.sql(
			"""update `tabUser` SET first_name=%(first_name)s,
			last_name=%(last_name)s WHERE name=%(name)s""",
			args,
		)

	if args.get("attach_user"):
		attach_user = args.get("attach_user").split(",")
		if len(attach_user) == 3:
			filename, filetype, content = attach_user
			_file = vmraid.get_doc(
				{
					"doctype": "File",
					"file_name": filename,
					"attached_to_doctype": "User",
					"attached_to_name": args.get("name"),
					"content": content,
					"decode": True,
				}
			)
			_file.save()
			fileurl = _file.file_url
			vmraid.db.set_value("User", args.get("name"), "user_image", fileurl)

	if args.get("name"):
		add_all_roles_to(args.get("name"))


def parse_args(args):
	if not args:
		args = vmraid.local.form_dict
	if isinstance(args, str):
		args = json.loads(args)

	args = vmraid._dict(args)

	# strip the whitespace
	for key, value in args.items():
		if isinstance(value, str):
			args[key] = strip(value)

	return args


def add_all_roles_to(name):
	user = vmraid.get_doc("User", name)
	for role in vmraid.db.sql("""select name from tabRole"""):
		if role[0] not in [
			"Administrator",
			"Guest",
			"All",
			"Customer",
			"Supplier",
			"Partner",
			"Employee",
		]:
			d = user.append("roles")
			d.role = role[0]
	user.save()


def disable_future_access():
	vmraid.db.set_default("desktop:home_page", "workspace")
	vmraid.db.set_value("System Settings", "System Settings", "setup_complete", 1)
	vmraid.db.set_value("System Settings", "System Settings", "is_first_startup", 1)

	# Enable onboarding after install
	vmraid.db.set_value("System Settings", "System Settings", "enable_onboarding", 1)

	if not vmraid.flags.in_test:
		# remove all roles and add 'Administrator' to prevent future access
		page = vmraid.get_doc("Page", "setup-wizard")
		page.roles = []
		page.append("roles", {"role": "Administrator"})
		page.flags.do_not_update_json = True
		page.flags.ignore_permissions = True
		page.save()


@vmraid.whitelist()
def load_messages(language):
	"""Load translation messages for given language from all `setup_wizard_requires`
	javascript files"""
	vmraid.clear_cache()
	set_default_language(get_language_code(language))
	vmraid.db.commit()
	m = get_dict("page", "setup-wizard")

	for path in vmraid.get_hooks("setup_wizard_requires"):
		# common folder `assets` served from `sites/`
		js_file_path = os.path.abspath(vmraid.get_site_path("..", *path.strip("/").split("/")))
		m.update(get_dict("jsfile", js_file_path))

	m.update(get_dict("boot"))
	send_translations(m)
	return vmraid.local.lang


@vmraid.whitelist()
def load_languages():
	language_codes = vmraid.db.sql(
		"select language_code, language_name from tabLanguage order by name", as_dict=True
	)
	codes_to_names = {}
	for d in language_codes:
		codes_to_names[d.language_code] = d.language_name
	return {
		"default_language": vmraid.db.get_value("Language", vmraid.local.lang, "language_name")
		or vmraid.local.lang,
		"languages": sorted(vmraid.db.sql_list("select language_name from tabLanguage order by name")),
		"codes_to_names": codes_to_names,
	}


@vmraid.whitelist()
def load_country():
	from vmraid.sessions import get_geo_ip_country

	return get_geo_ip_country(vmraid.local.request_ip) if vmraid.local.request_ip else None


@vmraid.whitelist()
def load_user_details():
	return {
		"full_name": vmraid.cache().hget("full_name", "signup"),
		"email": vmraid.cache().hget("email", "signup"),
	}


@vmraid.whitelist()
def reset_is_first_startup():
	vmraid.db.set_value("System Settings", "System Settings", "is_first_startup", 0)


def prettify_args(args):
	# remove attachments
	for key, val in args.items():
		if isinstance(val, str) and "data:image" in val:
			filename = val.split("data:image", 1)[0].strip(", ")
			size = round((len(val) * 3 / 4) / 1048576.0, 2)
			args[key] = "Image Attached: '{0}' of size {1} MB".format(filename, size)

	pretty_args = []
	for key in sorted(args):
		pretty_args.append("{} = {}".format(key, args[key]))
	return pretty_args


def email_setup_wizard_exception(traceback, args):
	if not vmraid.conf.setup_wizard_exception_email:
		return

	pretty_args = prettify_args(args)
	message = """

#### Traceback

<pre>{traceback}</pre>

---

#### Setup Wizard Arguments

<pre>{args}</pre>

---

#### Request Headers

<pre>{headers}</pre>

---

#### Basic Information

- **Site:** {site}
- **User:** {user}""".format(
		site=vmraid.local.site,
		traceback=traceback,
		args="\n".join(pretty_args),
		user=vmraid.session.user,
		headers=vmraid.request.headers,
	)

	vmraid.sendmail(
		recipients=vmraid.conf.setup_wizard_exception_email,
		sender=vmraid.session.user,
		subject="Setup failed: {}".format(vmraid.local.site),
		message=message,
		delayed=False,
	)


def log_setup_wizard_exception(traceback, args):
	with open("../logs/setup-wizard.log", "w+") as setup_log:
		setup_log.write(traceback)
		setup_log.write(json.dumps(args))


def get_language_code(lang):
	return vmraid.db.get_value("Language", {"language_name": lang})


def enable_twofactor_all_roles():
	all_role = vmraid.get_doc("Role", {"role_name": "All"})
	all_role.two_factor_auth = True
	all_role.save(ignore_permissions=True)


def make_records(records, debug=False):
	from vmraid import _dict
	from vmraid.modules import scrub

	if debug:
		print("make_records: in DEBUG mode")

	# LOG every success and failure
	for record in records:
		doctype = record.get("doctype")
		condition = record.get("__condition")

		if condition and not condition():
			continue

		doc = vmraid.new_doc(doctype)
		doc.update(record)

		# ignore mandatory for root
		parent_link_field = "parent_" + scrub(doc.doctype)
		if doc.meta.get_field(parent_link_field) and not doc.get(parent_link_field):
			doc.flags.ignore_mandatory = True

		try:
			doc.insert(ignore_permissions=True)
			vmraid.db.commit()

		except vmraid.DuplicateEntryError as e:
			# print("Failed to insert duplicate {0} {1}".format(doctype, doc.name))

			# pass DuplicateEntryError and continue
			if e.args and e.args[0] == doc.doctype and e.args[1] == doc.name:
				# make sure DuplicateEntryError is for the exact same doc and not a related doc
				vmraid.clear_messages()
			else:
				raise

		except Exception as e:
			vmraid.db.rollback()
			exception = record.get("__exception")
			if exception:
				config = _dict(exception)
				if isinstance(e, config.exception):
					config.handler()
				else:
					show_document_insert_error()
			else:
				show_document_insert_error()


def show_document_insert_error():
	print("Document Insert Error")
	print(vmraid.get_traceback())
