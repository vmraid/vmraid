# Copyright (c) 2021, VMRaid and Contributors
# License: MIT. See LICENSE
import json

import vmraid
from vmraid import _
from vmraid.integrations.doctype.paytm_settings.paytm_settings import (
	get_paytm_config,
	get_paytm_params,
)


def get_context(context):
	context.no_cache = 1
	paytm_config = get_paytm_config()

	try:
		doc = vmraid.get_doc("Integration Request", vmraid.form_dict["order_id"])

		context.payment_details = get_paytm_params(json.loads(doc.data), doc.name, paytm_config)

		context.url = paytm_config.url

	except Exception:
		vmraid.log_error()
		vmraid.redirect_to_message(
			_("Invalid Token"),
			_("Seems token you are using is invalid!"),
			http_status_code=400,
			indicator_color="red",
		)

		vmraid.local.flags.redirect_location = vmraid.local.response.location
		raise vmraid.Redirect
