class FulgencioError(RuntimeError):
    """Base error for expected application failures."""


class InvalidTransitionError(FulgencioError):
    """The requested conversation transition is not allowed."""


class AzureSqlError(FulgencioError):
    """Azure SQL could not complete a user lookup."""


class RobotUnavailableError(FulgencioError):
    """The robot is not idle and cannot accept another action."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f"El robot no está disponible: {status}")


class FirebaseError(FulgencioError):
    """Firebase could not read status or publish an action."""

