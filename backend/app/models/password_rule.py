class PasswordRule:
    def __init__(self, message, predicate):
        self.message = message
        self._predicate = predicate

    def passes(self, password):
        return self._predicate(password)


PASSWORD_RULES = (
    PasswordRule("Use at least 8 characters.", lambda value: len(value) >= 8),
    PasswordRule("Include a lowercase letter.", lambda value: any(c.islower() for c in value)),
    PasswordRule("Include an uppercase letter.", lambda value: any(c.isupper() for c in value)),
    PasswordRule("Include a number.", lambda value: any(c.isdigit() for c in value)),
    PasswordRule("Include a symbol.", lambda value: any(not c.isalnum() for c in value)),
)
