import click

import vmraid


def execute():
	vmraid.delete_doc_if_exists("DocType", "Chat Message")
	vmraid.delete_doc_if_exists("DocType", "Chat Message Attachment")
	vmraid.delete_doc_if_exists("DocType", "Chat Profile")
	vmraid.delete_doc_if_exists("DocType", "Chat Token")
	vmraid.delete_doc_if_exists("DocType", "Chat Room User")
	vmraid.delete_doc_if_exists("DocType", "Chat Room")
	vmraid.delete_doc_if_exists("Module Def", "Chat")

	click.secho(
		"Chat Module is moved to a separate app and is removed from VMRaid in version-13.\n"
		"Please install the app to continue using the chat feature: https://github.com/vmraid/chat",
		fg="yellow",
	)
