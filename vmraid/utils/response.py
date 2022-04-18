# Copyright (c) 2022, VMRaid and Contributors
# License: MIT. See LICENSE

import datetime
import decimal
import json
import mimetypes
import os
from urllib.parse import quote

import werkzeug.utils
from werkzeug.exceptions import Forbidden, NotFound
from werkzeug.local import LocalProxy
from werkzeug.wrappers import Response
from werkzeug.wsgi import wrap_file

import vmraid
import vmraid.model.document
import vmraid.sessions
import vmraid.utils
from vmraid import _
from vmraid.core.doctype.access_log.access_log import make_access_log
from vmraid.utils import cint, format_timedelta


def report_error(status_code):
	"""Build error. Show traceback in developer mode"""
	allow_traceback = (
		cint(vmraid.db.get_system_setting("allow_error_traceback")) if vmraid.db else True
	)
	if (
		allow_traceback
		and (status_code != 404 or vmraid.conf.logging)
		and not vmraid.local.flags.disable_traceback
	):
		traceback = vmraid.utils.get_traceback()
		if traceback:
			vmraid.errprint(traceback)
			vmraid.local.response.exception = traceback.splitlines()[-1]

	response = build_response("json")
	response.status_code = status_code
	return response


def build_response(response_type=None):
	if "docs" in vmraid.local.response and not vmraid.local.response.docs:
		del vmraid.local.response["docs"]

	response_type_map = {
		"csv": as_csv,
		"txt": as_txt,
		"download": as_raw,
		"json": as_json,
		"pdf": as_pdf,
		"page": as_page,
		"redirect": redirect,
		"binary": as_binary,
	}

	return response_type_map[vmraid.response.get("type") or response_type]()


def as_csv():
	response = Response()
	response.mimetype = "text/csv"
	response.charset = "utf-8"
	response.headers["Content-Disposition"] = (
		'attachment; filename="%s.csv"' % vmraid.response["doctype"].replace(" ", "_")
	).encode("utf-8")
	response.data = vmraid.response["result"]
	return response


def as_txt():
	response = Response()
	response.mimetype = "text"
	response.charset = "utf-8"
	response.headers["Content-Disposition"] = (
		'attachment; filename="%s.txt"' % vmraid.response["doctype"].replace(" ", "_")
	).encode("utf-8")
	response.data = vmraid.response["result"]
	return response


def as_raw():
	response = Response()
	response.mimetype = (
		vmraid.response.get("content_type")
		or mimetypes.guess_type(vmraid.response["filename"])[0]
		or "application/unknown"
	)
	response.headers["Content-Disposition"] = (
		f'{vmraid.response.get("display_content_as","attachment")}; filename="{vmraid.response["filename"].replace(" ", "_")}"'
	).encode("utf-8")
	response.data = vmraid.response["filecontent"]
	return response


def as_json():
	make_logs()
	response = Response()
	if vmraid.local.response.http_status_code:
		response.status_code = vmraid.local.response["http_status_code"]
		del vmraid.local.response["http_status_code"]

	response.mimetype = "application/json"
	response.charset = "utf-8"
	response.data = json.dumps(vmraid.local.response, default=json_handler, separators=(",", ":"))
	return response


def as_pdf():
	response = Response()
	response.mimetype = "application/pdf"
	encoded_filename = quote(vmraid.response["filename"].replace(" ", "_"))
	response.headers["Content-Disposition"] = (
		'filename="%s"' % vmraid.response["filename"].replace(" ", "_")
		+ ";filename*=utf-8''%s" % encoded_filename
	).encode("utf-8")
	response.data = vmraid.response["filecontent"]
	return response


def as_binary():
	response = Response()
	response.mimetype = "application/octet-stream"
	response.headers["Content-Disposition"] = (
		'filename="%s"' % vmraid.response["filename"].replace(" ", "_")
	).encode("utf-8")
	response.data = vmraid.response["filecontent"]
	return response


def make_logs(response=None):
	"""make strings for msgprint and errprint"""
	if not response:
		response = vmraid.local.response

	if vmraid.error_log:
		response["exc"] = json.dumps([vmraid.utils.cstr(d["exc"]) for d in vmraid.local.error_log])

	if vmraid.local.message_log:
		response["_server_messages"] = json.dumps(
			[vmraid.utils.cstr(d) for d in vmraid.local.message_log]
		)

	if vmraid.debug_log and vmraid.conf.get("logging") or False:
		response["_debug_messages"] = json.dumps(vmraid.local.debug_log)

	if vmraid.flags.error_message:
		response["_error_message"] = vmraid.flags.error_message


def json_handler(obj):
	"""serialize non-serializable data for json"""
	from collections.abc import Iterable

	if isinstance(obj, (datetime.date, datetime.datetime, datetime.time)):
		return str(obj)

	elif isinstance(obj, datetime.timedelta):
		return format_timedelta(obj)

	elif isinstance(obj, decimal.Decimal):
		return float(obj)

	elif isinstance(obj, LocalProxy):
		return str(obj)

	elif isinstance(obj, vmraid.model.document.BaseDocument):
		doc = obj.as_dict(no_nulls=True)
		return doc

	elif isinstance(obj, Iterable):
		return list(obj)

	elif type(obj) == type or isinstance(obj, Exception):
		return repr(obj)

	else:
		raise TypeError(
			"""Object of type %s with value of %s is not JSON serializable""" % (type(obj), repr(obj))
		)


def as_page():
	"""print web page"""
	from vmraid.website.serve import get_response

	return get_response(
		vmraid.response["route"], http_status_code=vmraid.response.get("http_status_code")
	)


def redirect():
	return werkzeug.utils.redirect(vmraid.response.location)


def download_backup(path):
	try:
		vmraid.only_for(("System Manager", "Administrator"))
		make_access_log(report_name="Backup")
	except vmraid.PermissionError:
		raise Forbidden(
			_("You need to be logged in and have System Manager Role to be able to access backups.")
		)

	return send_private_file(path)


def download_private_file(path):
	"""Checks permissions and sends back private file"""

	files = vmraid.db.get_all("File", {"file_url": path})
	can_access = False
	# this file might be attached to multiple documents
	# if the file is accessible from any one of those documents
	# then it should be downloadable
	for f in files:
		_file = vmraid.get_doc("File", f)
		can_access = _file.is_downloadable()
		if can_access:
			make_access_log(doctype="File", document=_file.name, file_type=os.path.splitext(path)[-1][1:])
			break

	if not can_access:
		raise Forbidden(_("You don't have permission to access this file"))

	return send_private_file(path.split("/private", 1)[1])


def send_private_file(path):
	path = os.path.join(vmraid.local.conf.get("private_path", "private"), path.strip("/"))
	filename = os.path.basename(path)

	if vmraid.local.request.headers.get("X-Use-X-Accel-Redirect"):
		path = "/protected/" + path
		response = Response()
		response.headers["X-Accel-Redirect"] = quote(vmraid.utils.encode(path))

	else:
		filepath = vmraid.utils.get_site_path(path)
		try:
			f = open(filepath, "rb")
		except IOError:
			raise NotFound

		response = Response(wrap_file(vmraid.local.request.environ, f), direct_passthrough=True)

	# no need for content disposition and force download. let browser handle its opening.
	# Except for those that can be injected with scripts.

	extension = os.path.splitext(path)[1]
	blacklist = [".svg", ".html", ".htm", ".xml"]

	if extension.lower() in blacklist:
		response.headers.add("Content-Disposition", "attachment", filename=filename.encode("utf-8"))

	response.mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"

	return response


def handle_session_stopped():
	from vmraid.website.serve import get_response

	vmraid.respond_as_web_page(
		_("Updating"),
		_("The system is being updated. Please refresh again after a few moments."),
		http_status_code=503,
		indicator_color="orange",
		fullpage=True,
		primary_action=None,
	)
	return get_response("message", http_status_code=503)
