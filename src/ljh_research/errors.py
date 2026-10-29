class ResearchError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def require(condition, code, message, details=None):
    if not condition:
        raise ResearchError(code, message, details)
