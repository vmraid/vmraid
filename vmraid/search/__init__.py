# Copyright (c) 2020, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid
from vmraid.search.full_text_search import FullTextSearch
from vmraid.search.website_search import WebsiteSearch
from vmraid.utils import cint


@vmraid.whitelist(allow_guest=True)
def web_search(query, scope=None, limit=20):
	limit = cint(limit)
	ws = WebsiteSearch(index_name="web_routes")
	return ws.search(query, scope, limit)
