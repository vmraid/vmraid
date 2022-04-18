# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import os

from werkzeug.exceptions import NotFound
from werkzeug.middleware.shared_data import SharedDataMiddleware

import vmraid
from vmraid.utils import cstr, get_site_name


class StaticDataMiddleware(SharedDataMiddleware):
	def __call__(self, environ, start_response):
		self.environ = environ
		return super(StaticDataMiddleware, self).__call__(environ, start_response)

	def get_directory_loader(self, directory):
		def loader(path):
			site = get_site_name(vmraid.app._site or self.environ.get("HTTP_HOST"))
			path = os.path.join(directory, site, "public", "files", cstr(path))
			if os.path.isfile(path):
				return os.path.basename(path), self._opener(path)
			else:
				raise NotFound
				# return None, None

		return loader
