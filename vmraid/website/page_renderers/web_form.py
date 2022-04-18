import vmraid
from vmraid.website.page_renderers.document_page import DocumentPage


class WebFormPage(DocumentPage):
	def can_render(self):
		webform_name = vmraid.db.exists("Web Form", {"route": self.path}, cache=True)
		if webform_name:
			self.doctype = "Web Form"
			self.docname = webform_name
		return bool(webform_name)
