class Logger:
    """
    #TODO: Logger
    Log level (default to 1, in settings.toml default to 3):
        0: No logs at all
        1: Log "Which extension has been used in which page, and processed which page, which errors"
        2: Leven 1 and "The original and last processed version's contents"
        3: Level 1 and "Original and every step of process/extension, for debugging"
    """

logger: Logger = Logger()
