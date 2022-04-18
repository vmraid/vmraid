# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

from mimetypes import guess_type

from werkzeug.wrappers import Response

import vmraid
import vmraid.sessions
import vmraid.utils
from vmraid import _, is_whitelisted
from vmraid.core.doctype.server_script.server_script_utils import get_server_script_map
from vmraid.utils import cint
from vmraid.utils.csvutils import build_csv_response
from vmraid.utils.image import optimize_image
from vmraid.utils.response import build_response

ALLOWED_MIMETYPES = (
	"image/png",
	"image/jpeg",
	"application/pdf",
	"application/msword",
	"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	"application/vnd.ms-excel",
	"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	"application/vnd.oasis.opendocument.text",
	"application/vnd.oasis.opendocument.spreadsheet",
)


def handle():
	"""handle request"""

	cmd = vmraid.local.form_dict.cmd
	data = None

	if cmd != "login":
		data = execute_cmd(cmd)

	# data can be an empty string or list which are valid responses
	if data is not None:
		if isinstance(data, Response):
			# method returns a response object, pass it on
			return data

		# add the response to `message` label
		vmraid.response["message"] = data

	return build_response("json")


def execute_cmd(cmd, from_async=False):
	"""execute a request as python module"""
	for hook in vmraid.get_hooks("override_whitelisted_methods", {}).get(cmd, []):
		# override using the first hook
		cmd = hook
		break

	# via server script
	server_script = get_server_script_map().get("_api", {}).get(cmd)
	if server_script:
		return run_server_script(server_script)

	try:
		method = get_attr(cmd)
	except Exception as e:
		vmraid.throw(_("Failed to get method for command {0} with {1}").format(cmd, e))

	if from_async:
		method = method.queue

	if method != run_doc_method:
		is_whitelisted(method)
		is_valid_http_method(method)

	return vmraid.call(method, **vmraid.form_dict)


def run_server_script(server_script):
	response = vmraid.get_doc("Server Script", server_script).execute_method()

	# some server scripts return output using flags (empty dict by default),
	# while others directly modify vmraid.response
	# return flags if not empty dict (this overwrites vmraid.response.message)
	if response != {}:
		return response


def is_valid_http_method(method):
	if vmraid.flags.in_safe_exec:
		return

	http_method = vmraid.local.request.method

	if http_method not in vmraid.allowed_http_methods_for_whitelisted_func[method]:
		throw_permission_error()


def throw_permission_error():
	vmraid.throw(_("Not permitted"), vmraid.PermissionError)


@vmraid.whitelist(allow_guest=True)
def version():
	return vmraid.__version__


@vmraid.whitelist(allow_guest=True)
def logout():
	vmraid.local.login_manager.logout()
	vmraid.db.commit()


@vmraid.whitelist(allow_guest=True)
def web_logout():
	vmraid.local.login_manager.logout()
	vmraid.db.commit()
	vmraid.respond_as_web_page(
		_("Logged Out"), _("You have been successfully logged out"), indicator_color="green"
	)


@vmraid.whitelist()
def uploadfile():
	ret = None

	try:
		if vmraid.form_dict.get("from_form"):
			try:
				ret = vmraid.get_doc(
					{
						"doctype": "File",
						"attached_to_name": vmraid.form_dict.docname,
						"attached_to_doctype": vmraid.form_dict.doctype,
						"attached_to_field": vmraid.form_dict.docfield,
						"file_url": vmraid.form_dict.file_url,
						"file_name": vmraid.form_dict.filename,
						"is_private": vmraid.utils.cint(vmraid.form_dict.is_private),
						"content": vmraid.form_dict.filedata,
						"decode": True,
					}
				)
				ret.save()
			except vmraid.DuplicateEntryError:
				# ignore pass
				ret = None
				vmraid.db.rollback()
		else:
			if vmraid.form_dict.get("method"):
				method = vmraid.get_attr(vmraid.form_dict.method)
				is_whitelisted(method)
				ret = method()
	except Exception:
		vmraid.errprint(vmraid.utils.get_traceback())
		vmraid.response["http_status_code"] = 500
		ret = None

	return ret


@vmraid.whitelist(allow_guest=True)
def upload_file():
	user = None
	if vmraid.session.user == "Guest":
		if vmraid.get_system_settings("allow_guests_to_upload_files"):
			ignore_permissions = True
		else:
			return
	else:
		user = vmraid.get_doc("User", vmraid.session.user)
		ignore_permissions = False

	files = vmraid.request.files
	is_private = vmraid.form_dict.is_private
	doctype = vmraid.form_dict.doctype
	docname = vmraid.form_dict.docname
	fieldname = vmraid.form_dict.fieldname
	file_url = vmraid.form_dict.file_url
	folder = vmraid.form_dict.folder or "Home"
	method = vmraid.form_dict.method
	filename = vmraid.form_dict.file_name
	optimize = vmraid.form_dict.optimize
	content = None

	if "file" in files:
		file = files["file"]
		content = file.stream.read()
		filename = file.filename

		content_type = guess_type(filename)[0]
		if optimize and content_type.startswith("image/"):
			args = {"content": content, "content_type": content_type}
			if vmraid.form_dict.max_width:
				args["max_width"] = int(vmraid.form_dict.max_width)
			if vmraid.form_dict.max_height:
				args["max_height"] = int(vmraid.form_dict.max_height)
			content = optimize_image(**args)

	vmraid.local.uploaded_file = content
	vmraid.local.uploaded_filename = filename

	if not file_url and (vmraid.session.user == "Guest" or (user and not user.has_desk_access())):
		filetype = guess_type(filename)[0]
		if filetype not in ALLOWED_MIMETYPES:
			vmraid.throw(_("You can only upload JPG, PNG, PDF, or Microsoft documents."))

	if method:
		method = vmraid.get_attr(method)
		is_whitelisted(method)
		return method()
	else:
		ret = vmraid.get_doc(
			{
				"doctype": "File",
				"attached_to_doctype": doctype,
				"attached_to_name": docname,
				"attached_to_field": fieldname,
				"folder": folder,
				"file_name": filename,
				"file_url": file_url,
				"is_private": cint(is_private),
				"content": content,
			}
		)
		ret.save(ignore_permissions=ignore_permissions)
		return ret


def get_attr(cmd):
	"""get method object from cmd"""
	if "." in cmd:
		method = vmraid.get_attr(cmd)
	else:
		method = globals()[cmd]
	vmraid.log("method:" + cmd)
	return method


@vmraid.whitelist(allow_guest=True)
def ping():
	return "pong"


def run_doc_method(method, docs=None, dt=None, dn=None, arg=None, args=None):
	"""run a whitelisted controller method"""
	from inspect import getfullargspec

	if not args and arg:
		args = arg

	if dt:  # not called from a doctype (from a page)
		if not dn:
			dn = dt  # single
		doc = vmraid.get_doc(dt, dn)

	else:
		docs = vmraid.parse_json(docs)
		doc = vmraid.get_doc(docs)
		doc._original_modified = doc.modified
		doc.check_if_latest()

	if not doc or not doc.has_permission("read"):
		throw_permission_error()

	try:
		args = vmraid.parse_json(args)
	except ValueError:
		pass

	method_obj = getattr(doc, method)
	fn = getattr(method_obj, "__func__", method_obj)
	is_whitelisted(fn)
	is_valid_http_method(fn)

	fnargs = getfullargspec(method_obj).args

	if not fnargs or (len(fnargs) == 1 and fnargs[0] == "self"):
		response = doc.run_method(method)

	elif "args" in fnargs or not isinstance(args, dict):
		response = doc.run_method(method, args)

	else:
		response = doc.run_method(method, **args)

	vmraid.response.docs.append(doc)
	if response is None:
		return

	# build output as csv
	if cint(vmraid.form_dict.get("as_csv")):
		build_csv_response(response, _(doc.doctype).replace(" ", ""))
		return

	vmraid.response["message"] = response


# for backwards compatibility
runserverobj = run_doc_method
