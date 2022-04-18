import vmraid


def execute():
	vmraid.delete_doc_if_exists("DocType", "Post")
	vmraid.delete_doc_if_exists("DocType", "Post Comment")
