import vmraid
from vmraid.website.utils import build_response


class RedirectPage(object):
	def __init__(self, path, http_status_code=301):
		self.path = path
		self.http_status_code = http_status_code

	def can_render(self):
		return True

	def render(self):
		return build_response(
			self.path,
			"",
			301,
			{
				"Location": vmraid.flags.redirect_location or (vmraid.local.response or {}).get("location"),
				"Cache-Control": "no-store, no-cache, must-revalidate",
			},
		)
