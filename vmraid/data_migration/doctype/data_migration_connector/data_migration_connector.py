# -*- coding: utf-8 -*-
# Copyright (c) 2017, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import os

import vmraid
from vmraid import _
from vmraid.model.document import Document
from vmraid.modules.export_file import create_init_py

from .connectors.base import BaseConnection
from .connectors.vmraid_connection import VMRaidConnection


class DataMigrationConnector(Document):
	def validate(self):
		if not (self.python_module or self.connector_type):
			vmraid.throw(_("Enter python module or select connector type"))

		if self.python_module:
			try:
				get_connection_class(self.python_module)
			except:
				vmraid.throw(vmraid._("Invalid module path"))

	def get_connection(self):
		if self.python_module:
			_class = get_connection_class(self.python_module)
			return _class(self)
		else:
			self.connection = VMRaidConnection(self)

		return self.connection


@vmraid.whitelist()
def create_new_connection(module, connection_name):
	if not vmraid.conf.get("developer_mode"):
		vmraid.msgprint(_("Please enable developer mode to create new connection"))
		return
	# create folder
	module_path = vmraid.get_module_path(module)
	connectors_folder = os.path.join(module_path, "connectors")
	vmraid.create_folder(connectors_folder)

	# create init py
	create_init_py(module_path, "connectors", "")

	connection_class = connection_name.replace(" ", "")
	file_name = vmraid.scrub(connection_name) + ".py"
	file_path = os.path.join(module_path, "connectors", file_name)

	# create boilerplate file
	with open(file_path, "w") as f:
		f.write(connection_boilerplate.format(connection_class=connection_class))

	# get python module string from file_path
	app_name = vmraid.db.get_value("Module Def", module, "app_name")
	python_module = os.path.relpath(file_path, "../apps/{0}".format(app_name)).replace(
		os.path.sep, "."
	)[:-3]

	return python_module


def get_connection_class(python_module):
	filename = python_module.rsplit(".", 1)[-1]
	classname = vmraid.unscrub(filename).replace(" ", "")
	module = vmraid.get_module(python_module)

	raise_error = False
	if hasattr(module, classname):
		_class = getattr(module, classname)
		if not issubclass(_class, BaseConnection):
			raise_error = True
	else:
		raise_error = True

	if raise_error:
		raise ImportError(filename)

	return _class


connection_boilerplate = """from vmraid.data_migration.doctype.data_migration_connector.connectors.base import BaseConnection

class {connection_class}(BaseConnection):
	def __init__(self, connector):
		# self.connector = connector
		# self.connection = YourModule(self.connector.username, self.get_password())
		# self.name_field = 'id'
		pass

	def get(self, remote_objectname, fields=None, filters=None, start=0, page_length=10):
		pass

	def insert(self, doctype, doc):
		pass

	def update(self, doctype, doc, migration_id):
		pass

	def delete(self, doctype, migration_id):
		pass

"""
