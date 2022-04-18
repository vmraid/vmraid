import vmraid


# no context object is accepted
def get_context():
	context = vmraid._dict()
	context.body = "Custom Content"
	return context
