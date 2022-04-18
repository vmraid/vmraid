import vmraid
from vmraid.utils.password import get_decrypted_password


def execute():
	publishable_key = vmraid.db.sql(
		"select value from tabSingles where doctype='Stripe Settings' and field='publishable_key'"
	)
	if publishable_key:
		secret_key = get_decrypted_password(
			"Stripe Settings", "Stripe Settings", fieldname="secret_key", raise_exception=False
		)
		if secret_key:
			vmraid.reload_doc("integrations", "doctype", "stripe_settings")
			vmraid.db.commit()

			settings = vmraid.new_doc("Stripe Settings")
			settings.gateway_name = (
				vmraid.db.get_value("Global Defaults", None, "default_company") or "Stripe Settings"
			)
			settings.publishable_key = publishable_key
			settings.secret_key = secret_key
			settings.save(ignore_permissions=True)

	vmraid.db.delete("Singles", {"doctype": "Stripe Settings"})
