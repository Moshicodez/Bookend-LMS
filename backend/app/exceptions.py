class ServiceError(Exception):
    pass


class ValidationError(ServiceError):
    pass


class NotFoundError(ServiceError):
    pass


class PermissionDenied(ServiceError):
    pass