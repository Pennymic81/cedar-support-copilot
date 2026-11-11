from django.http import HttpResponse

PUBLIC_PREFIXES = ("/api/chat/", "/static/widget/")


class WidgetCorsMiddleware:
    """Let the chat widget call the public chat API from any website.

    Only the widget endpoints get these headers. They use no cookies (the widget key and
    conversation token are sent explicitly), so allowing any origin is safe here.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        public = request.path.startswith(PUBLIC_PREFIXES)
        if public and request.method == "OPTIONS":
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if public:
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type"
            response["Access-Control-Max-Age"] = "86400"
        return response
