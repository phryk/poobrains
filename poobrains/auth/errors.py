import werkzeug

class PermissionDenied(werkzeug.exceptions.HTTPException):
    code = 403
