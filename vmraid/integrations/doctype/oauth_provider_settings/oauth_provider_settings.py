# -*- coding: utf-8 -*-
# Copyright (c) 2015, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid import _
from vmraid.model.document import Document


class OAuthProviderSettings(Document):
	pass


def get_oauth_settings():
	"""Returns oauth settings"""
	out = vmraid._dict(
		{
			"skip_authorization": vmraid.db.get_value("OAuth Provider Settings", None, "skip_authorization")
		}
	)

	return out
