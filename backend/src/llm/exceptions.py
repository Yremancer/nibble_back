class LlmError(Exception):
    pass


class LlmNotConfiguredError(LlmError):
    pass


class LlmRequestError(LlmError):
    pass


class LlmInvalidResponseError(LlmError):
    pass
