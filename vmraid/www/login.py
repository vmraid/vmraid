# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import json

import vmraid
import vmraid.utils
from vmraid import _
from vmraid.auth import LoginManager
from vmraid.integrations.doctype.ldap_settings.ldap_settings import LDAPSettings
from vmraid.integrations.oauth2_logins import decoder_compat
from vmraid.utils.html_utils import get_icon_html
from vmraid.utils.jinja import guess_is_path
from vmraid.utils.oauth import get_oauth2_authorize_url, get_oauth_keys
from vmraid.utils.oauth import login_oauth_user as _login_oauth_user
from vmraid.utils.oauth import login_via_oauth2, login_via_oauth2_id_token, redirect_post_login
from vmraid.utils.password import get_decrypted_password
from vmraid.website.utils import get_home_page

no_cache = True


def get_context(context):
	redirect_to = vmraid.local.request.args.get("redirect-to")

	if vmraid.session.user != "Guest":
		if not redirect_to:
			if vmraid.session.data.user_type == "Website User":
				redirect_to = get_home_page()
			else:
				redirect_to = "/app"

		if redirect_to != "login":
			vmraid.local.flags.redirect_location = redirect_to
			raise vmraid.Redirect

	# get settings from site config
	context.no_header = True
	context.for_test = "login.html"
	context["title"] = "Login"
	context["provider_logins"] = []
	context["disable_signup"] = vmraid.utils.cint(
		vmraid.db.get_single_value("Website Settings", "disable_signup")
	)
	context["logo"] = (
		vmraid.db.get_single_value("Website Settings", "app_logo")
		or vmraid.get_hooks("app_logo_url")[-1]
	)
	context["app_name"] = (
		vmraid.db.get_single_value("Website Settings", "app_name")
		or vmraid.get_system_settings("app_name")
		or _("VMRaid")
	)

	signup_form_template = vmraid.get_hooks("signup_form_template")
	if signup_form_template and len(signup_form_template) and signup_form_template[0]:
		path = signup_form_template[0]
		if not guess_is_path(path):
			path = vmraid.get_attr(signup_form_template[0])()
	else:
		path = "vmraid/templates/signup.html"
	if path:
		context["signup_form_template"] = vmraid.get_template(path).render()

	providers = [
		i.name
		for i in vmraid.get_all("Social Login Key", filters={"enable_social_login": 1}, order_by="name")
	]
	for provider in providers:
		client_id, base_url = vmraid.get_value("Social Login Key", provider, ["client_id", "base_url"])
		client_secret = get_decrypted_password("Social Login Key", provider, "client_secret")
		provider_name = vmraid.get_value("Social Login Key", provider, "provider_name")

		icon = None
		icon_url = vmraid.get_value("Social Login Key", provider, "icon")
		if icon_url:
			if provider_name != "Custom":
				icon = "<img src='{0}' alt={1}>".format(icon_url, provider_name)
			else:
				icon = get_icon_html(icon_url, small=True)

		if get_oauth_keys(provider) and client_secret and client_id and base_url:
			context.provider_logins.append(
				{
					"name": provider,
					"provider_name": provider_name,
					"auth_url": get_oauth2_authorize_url(provider, redirect_to),
					"icon": icon,
				}
			)
			context["social_login"] = True
	ldap_settings = LDAPSettings.get_ldap_client_settings()
	context["ldap_settings"] = ldap_settings

	login_label = [_("Email")]

	if vmraid.utils.cint(vmraid.get_system_settings("allow_login_using_mobile_number")):
		login_label.append(_("Mobile"))

	if vmraid.utils.cint(vmraid.get_system_settings("allow_login_using_user_name")):
		login_label.append(_("Username"))

	context["login_label"] = " {0} ".format(_("or")).join(login_label)

	return context


@vmraid.whitelist(allow_guest=True)
def login_via_google(code, state):
	login_via_oauth2("google", code, state, decoder=decoder_compat)


@vmraid.whitelist(allow_guest=True)
def login_via_github(code, state):
	login_via_oauth2("github", code, state)


@vmraid.whitelist(allow_guest=True)
def login_via_facebook(code, state):
	login_via_oauth2("facebook", code, state, decoder=decoder_compat)


@vmraid.whitelist(allow_guest=True)
def login_via_vmraid(code, state):
	login_via_oauth2("vmraid", code, state, decoder=decoder_compat)


@vmraid.whitelist(allow_guest=True)
def login_via_office365(code, state):
	login_via_oauth2_id_token("office_365", code, state, decoder=decoder_compat)


@vmraid.whitelist(allow_guest=True)
def login_via_token(login_token):
	sid = vmraid.cache().get_value("login_token:{0}".format(login_token), expires=True)
	if not sid:
		vmraid.respond_as_web_page(_("Invalid Request"), _("Invalid Login Token"), http_status_code=417)
		return

	vmraid.local.form_dict.sid = sid
	vmraid.local.login_manager = LoginManager()

	redirect_post_login(
		desk_user=vmraid.db.get_value("User", vmraid.session.user, "user_type") == "System User"
	)
