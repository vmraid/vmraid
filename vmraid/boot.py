# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
"""
bootstrap client session
"""

import vmraid
import vmraid.defaults
import vmraid.desk.desk_page
from vmraid.core.doctype.navbar_settings.navbar_settings import get_app_logo, get_navbar_settings
from vmraid.desk.doctype.route_history.route_history import frequently_visited_links
from vmraid.desk.form.load import get_meta_bundle
from vmraid.email.inbox import get_email_accounts
from vmraid.model.base_document import get_controller
from vmraid.query_builder import DocType
from vmraid.query_builder.functions import Count
from vmraid.query_builder.terms import subqry
from vmraid.social.doctype.energy_point_log.energy_point_log import get_energy_points
from vmraid.social.doctype.energy_point_settings.energy_point_settings import (
	is_energy_point_enabled,
)
from vmraid.translate import get_lang_dict
from vmraid.utils import add_user_info, get_time_zone
from vmraid.utils.change_log import get_versions
from vmraid.website.doctype.web_page_view.web_page_view import is_tracking_enabled


def get_bootinfo():
	"""build and return boot info"""
	vmraid.set_user_lang(vmraid.session.user)
	bootinfo = vmraid._dict()
	hooks = vmraid.get_hooks()
	doclist = []

	# user
	get_user(bootinfo)

	# system info
	bootinfo.sitename = vmraid.local.site
	bootinfo.sysdefaults = vmraid.defaults.get_defaults()
	bootinfo.server_date = vmraid.utils.nowdate()

	if vmraid.session["user"] != "Guest":
		bootinfo.user_info = get_user_info()
		bootinfo.sid = vmraid.session["sid"]

	bootinfo.modules = {}
	bootinfo.module_list = []
	load_desktop_data(bootinfo)
	bootinfo.letter_heads = get_letter_heads()
	bootinfo.active_domains = vmraid.get_active_domains()
	bootinfo.all_domains = [d.get("name") for d in vmraid.get_all("Domain")]
	add_layouts(bootinfo)

	bootinfo.module_app = vmraid.local.module_app
	bootinfo.single_types = [d.name for d in vmraid.get_all("DocType", {"issingle": 1})]
	bootinfo.nested_set_doctypes = [
		d.parent for d in vmraid.get_all("DocField", {"fieldname": "lft"}, ["parent"])
	]
	add_home_page(bootinfo, doclist)
	bootinfo.page_info = get_allowed_pages()
	load_translations(bootinfo)
	add_timezone_info(bootinfo)
	load_conf_settings(bootinfo)
	load_print(bootinfo, doclist)
	doclist.extend(get_meta_bundle("Page"))
	bootinfo.home_folder = vmraid.db.get_value("File", {"is_home_folder": 1})
	bootinfo.navbar_settings = get_navbar_settings()
	bootinfo.notification_settings = get_notification_settings()
	set_time_zone(bootinfo)

	# ipinfo
	if vmraid.session.data.get("ipinfo"):
		bootinfo.ipinfo = vmraid.session["data"]["ipinfo"]

	# add docs
	bootinfo.docs = doclist

	for method in hooks.boot_session or []:
		vmraid.get_attr(method)(bootinfo)

	if bootinfo.lang:
		bootinfo.lang = str(bootinfo.lang)
	bootinfo.versions = {k: v["version"] for k, v in get_versions().items()}

	bootinfo.error_report_email = vmraid.conf.error_report_email
	bootinfo.calendars = sorted(vmraid.get_hooks("calendars"))
	bootinfo.treeviews = vmraid.get_hooks("treeviews") or []
	bootinfo.lang_dict = get_lang_dict()
	bootinfo.success_action = get_success_action()
	bootinfo.update(get_email_accounts(user=vmraid.session.user))
	bootinfo.energy_points_enabled = is_energy_point_enabled()
	bootinfo.website_tracking_enabled = is_tracking_enabled()
	bootinfo.points = get_energy_points(vmraid.session.user)
	bootinfo.frequently_visited_links = frequently_visited_links()
	bootinfo.link_preview_doctypes = get_link_preview_doctypes()
	bootinfo.additional_filters_config = get_additional_filters_from_hooks()
	bootinfo.desk_settings = get_desk_settings()
	bootinfo.app_logo_url = get_app_logo()
	bootinfo.link_title_doctypes = get_link_title_doctypes()

	return bootinfo


def get_letter_heads():
	letter_heads = {}
	for letter_head in vmraid.get_all("Letter Head", fields=["name", "content", "footer"]):
		letter_heads.setdefault(
			letter_head.name, {"header": letter_head.content, "footer": letter_head.footer}
		)

	return letter_heads


def load_conf_settings(bootinfo):
	from vmraid import conf

	bootinfo.max_file_size = conf.get("max_file_size") or 10485760
	for key in ("developer_mode", "socketio_port", "file_watcher_port"):
		if key in conf:
			bootinfo[key] = conf.get(key)


def load_desktop_data(bootinfo):
	from vmraid.desk.desktop import get_workspace_sidebar_items

	bootinfo.allowed_workspaces = get_workspace_sidebar_items().get("pages")
	bootinfo.module_page_map = get_controller("Workspace").get_module_page_map()
	bootinfo.dashboards = vmraid.get_all("Dashboard")


def get_allowed_pages(cache=False):
	return get_user_pages_or_reports("Page", cache=cache)


def get_allowed_reports(cache=False):
	return get_user_pages_or_reports("Report", cache=cache)


def get_user_pages_or_reports(parent, cache=False):
	_cache = vmraid.cache()

	if cache:
		has_role = _cache.get_value("has_role:" + parent, user=vmraid.session.user)
		if has_role:
			return has_role

	roles = vmraid.get_roles()
	has_role = {}

	page = DocType("Page")
	report = DocType("Report")

	if parent == "Report":
		columns = (report.name.as_("title"), report.ref_doctype, report.report_type)
	else:
		columns = (page.title.as_("title"),)

	customRole = DocType("Custom Role")
	hasRole = DocType("Has Role")
	parentTable = DocType(parent)

	# get pages or reports set on custom role
	pages_with_custom_roles = (
		vmraid.qb.from_(customRole)
		.from_(hasRole)
		.from_(parentTable)
		.select(
			customRole[parent.lower()].as_("name"), customRole.modified, customRole.ref_doctype, *columns
		)
		.where(
			(hasRole.parent == customRole.name)
			& (parentTable.name == customRole[parent.lower()])
			& (customRole[parent.lower()].isnotnull())
			& (hasRole.role.isin(roles))
		)
	).run(as_dict=True)

	for p in pages_with_custom_roles:
		has_role[p.name] = {"modified": p.modified, "title": p.title, "ref_doctype": p.ref_doctype}

	subq = (
		vmraid.qb.from_(customRole)
		.select(customRole[parent.lower()])
		.where(customRole[parent.lower()].isnotnull())
	)

	pages_with_standard_roles = (
		vmraid.qb.from_(hasRole)
		.from_(parentTable)
		.select(parentTable.name.as_("name"), parentTable.modified, *columns)
		.where(
			(hasRole.role.isin(roles))
			& (hasRole.parent == parentTable.name)
			& (parentTable.name.notin(subq))
		)
		.distinct()
	)

	if parent == "Report":
		pages_with_standard_roles = pages_with_standard_roles.where(report.disabled == 0)

	pages_with_standard_roles = pages_with_standard_roles.run(as_dict=True)

	for p in pages_with_standard_roles:
		if p.name not in has_role:
			has_role[p.name] = {"modified": p.modified, "title": p.title}
			if parent == "Report":
				has_role[p.name].update({"ref_doctype": p.ref_doctype})

	no_of_roles = (
		vmraid.qb.from_(hasRole).select(Count("*")).where(hasRole.parent == parentTable.name)
	)

	# pages with no role are allowed
	if parent == "Page":

		pages_with_no_roles = (
			vmraid.qb.from_(parentTable)
			.select(parentTable.name, parentTable.modified, *columns)
			.where(subqry(no_of_roles) == 0)
		).run(as_dict=True)

		for p in pages_with_no_roles:
			if p.name not in has_role:
				has_role[p.name] = {"modified": p.modified, "title": p.title}

	elif parent == "Report":
		reports = vmraid.get_all(
			"Report",
			fields=["name", "report_type"],
			filters={"name": ("in", has_role.keys())},
			ignore_ifnull=True,
		)
		for report in reports:
			has_role[report.name]["report_type"] = report.report_type

	# Expire every six hours
	_cache.set_value("has_role:" + parent, has_role, vmraid.session.user, 21600)
	return has_role


def load_translations(bootinfo):
	messages = vmraid.get_lang_dict("boot")

	bootinfo["lang"] = vmraid.lang

	# load translated report names
	for name in bootinfo.user.all_reports:
		messages[name] = vmraid._(name)

	# only untranslated
	messages = {k: v for k, v in messages.items() if k != v}

	bootinfo["__messages"] = messages


def get_user_info():
	# get info for current user
	user_info = vmraid._dict()
	add_user_info(vmraid.session.user, user_info)

	if vmraid.session.user == "Administrator" and user_info.Administrator.email:
		user_info[user_info.Administrator.email] = user_info.Administrator

	return user_info


def get_user(bootinfo):
	"""get user info"""
	bootinfo.user = vmraid.get_user().load_user()


def add_home_page(bootinfo, docs):
	"""load home page"""
	if vmraid.session.user == "Guest":
		return
	home_page = vmraid.db.get_default("desktop:home_page")

	if home_page == "setup-wizard":
		bootinfo.setup_wizard_requires = vmraid.get_hooks("setup_wizard_requires")

	try:
		page = vmraid.desk.desk_page.get(home_page)
		docs.append(page)
		bootinfo["home_page"] = page.name
	except (vmraid.DoesNotExistError, vmraid.PermissionError):
		if vmraid.message_log:
			vmraid.message_log.pop()
		bootinfo["home_page"] = "Workspaces"


def add_timezone_info(bootinfo):
	system = bootinfo.sysdefaults.get("time_zone")
	import vmraid.utils.momentjs

	bootinfo.timezone_info = {"zones": {}, "rules": {}, "links": {}}
	vmraid.utils.momentjs.update(system, bootinfo.timezone_info)


def load_print(bootinfo, doclist):
	print_settings = vmraid.db.get_singles_dict("Print Settings")
	print_settings.doctype = ":Print Settings"
	doclist.append(print_settings)
	load_print_css(bootinfo, print_settings)


def load_print_css(bootinfo, print_settings):
	import vmraid.www.printview

	bootinfo.print_css = vmraid.www.printview.get_print_style(
		print_settings.print_style or "Redesign", for_legacy=True
	)


def get_unseen_notes():
	note = DocType("Note")
	nsb = DocType("Note Seen By").as_("nsb")

	return (
		vmraid.qb.from_(note)
		.select(note.name, note.title, note.content, note.notify_on_every_login)
		.where(
			(note.notify_on_every_login == 1)
			& (note.expire_notification_on > vmraid.utils.now())
			& (
				subqry(vmraid.qb.from_(nsb).select(nsb.user).where(nsb.parent == note.name)).notin(
					[vmraid.session.user]
				)
			)
		)
	).run(as_dict=1)


def get_success_action():
	return vmraid.get_all("Success Action", fields=["*"])


def get_link_preview_doctypes():
	from vmraid.utils import cint

	link_preview_doctypes = [d.name for d in vmraid.db.get_all("DocType", {"show_preview_popup": 1})]
	customizations = vmraid.get_all(
		"Property Setter", fields=["doc_type", "value"], filters={"property": "show_preview_popup"}
	)

	for custom in customizations:
		if not cint(custom.value) and custom.doc_type in link_preview_doctypes:
			link_preview_doctypes.remove(custom.doc_type)
		else:
			link_preview_doctypes.append(custom.doc_type)

	return link_preview_doctypes


def get_additional_filters_from_hooks():
	filter_config = vmraid._dict()
	filter_hooks = vmraid.get_hooks("filters_config")
	for hook in filter_hooks:
		filter_config.update(vmraid.get_attr(hook)())

	return filter_config


def add_layouts(bootinfo):
	# add routes for readable doctypes
	bootinfo.doctype_layouts = vmraid.get_all("DocType Layout", ["name", "route", "document_type"])


def get_desk_settings():
	role_list = vmraid.get_all("Role", fields=["*"], filters=dict(name=["in", vmraid.get_roles()]))
	desk_settings = {}

	from vmraid.core.doctype.role.role import desk_properties

	for role in role_list:
		for key in desk_properties:
			desk_settings[key] = desk_settings.get(key) or role.get(key)

	return desk_settings


def get_notification_settings():
	return vmraid.get_cached_doc("Notification Settings", vmraid.session.user)


@vmraid.whitelist()
def get_link_title_doctypes():
	dts = vmraid.get_all("DocType", {"show_title_field_in_link": 1})
	custom_dts = vmraid.get_all(
		"Property Setter",
		{"property": "show_title_field_in_link", "value": "1"},
		["doc_type as name"],
	)
	return [d.name for d in dts + custom_dts if d]


def set_time_zone(bootinfo):
	bootinfo.time_zone = {
		"system": get_time_zone(),
		"user": bootinfo.get("user_info", {}).get(vmraid.session.user, {}).get("time_zone", None)
		or get_time_zone(),
	}
