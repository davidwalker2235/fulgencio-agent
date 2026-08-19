from __future__ import annotations

from typing import Any

from app.agent.state_machine import ConversationStateMachine
from app.domain.errors import FulgencioError, InvalidTransitionError, RobotUnavailableError
from app.domain.models import Experience, ToolResult
from app.domain.ports import RobotGateway, UserRepository


class ToolExecutor:
    def __init__(
        self,
        machine: ConversationStateMachine,
        users: UserRepository,
        robot: RobotGateway,
    ) -> None:
        self.machine = machine
        self._users = users
        self._robot = robot
        self._results: dict[str, ToolResult] = {}

    async def execute(self, call_id: str, name: str, arguments: dict[str, Any]) -> ToolResult:
        cached = self._results.get(call_id)
        if cached is not None:
            return cached
        if not self.machine.register_call(call_id):
            return ToolResult(name, "error", "Llamada duplicada o sin identificador")

        try:
            result = await self._dispatch(name, arguments)
        except (ValueError, TypeError, KeyError, FulgencioError) as exc:
            result = ToolResult(name, "error", str(exc))
        self._results[call_id] = result
        return result

    async def _dispatch(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name == "choose_experience":
            return await self._choose_experience(arguments)
        if name == "capture_number":
            return self._capture_number(arguments)
        if name == "confirm_number":
            return await self._confirm_number(arguments)
        raise InvalidTransitionError(f"Herramienta desconocida: {name}")

    async def _choose_experience(self, arguments: dict[str, Any]) -> ToolResult:
        experience = Experience(arguments["experience"])
        self.machine.choose_experience(experience)
        if experience is Experience.CARICATURE:
            return ToolResult(
                "choose_experience", "ok", "Opción caricatura seleccionada; solicita el número"
            )

        await self._require_idle()
        await self._robot.publish_gift()
        self.machine.finish_gift()
        return ToolResult("choose_experience", "ok", "El regalo se ha solicitado correctamente")

    def _capture_number(self, arguments: dict[str, Any]) -> ToolResult:
        value = arguments["number"]
        if isinstance(value, bool):
            raise ValueError("El número debe ser un entero positivo")
        number = int(value)
        if number != value:
            raise ValueError("El número debe ser un entero positivo")
        self.machine.capture_number(number)
        return ToolResult(
            "capture_number",
            "ok",
            "Número capturado; pide confirmación explícita",
            {"number": number},
        )

    async def _confirm_number(self, arguments: dict[str, Any]) -> ToolResult:
        confirmed = arguments["confirmed"]
        if not isinstance(confirmed, bool):
            raise ValueError("La confirmación debe ser true o false")
        if not confirmed:
            self.machine.reject_number()
            return ToolResult(
                "confirm_number", "ok", "Número rechazado; vuelve a pedirlo"
            )

        user_id = self.machine.pending_number
        if user_id is None:
            raise InvalidTransitionError("No hay un número pendiente")
        user = await self._users.get_by_id(user_id)
        if user is None:
            self.machine.reset_number()
            return ToolResult(
                "confirm_number", "not_found", "No existe un usuario con ese número; pide otro"
            )
        if not user.has_caricature:
            self.machine.reset_number()
            return ToolResult(
                "confirm_number",
                "not_found",
                "El usuario no tiene caricatura disponible; pide otro número",
            )

        await self._require_idle()
        await self._robot.publish_caricature(user)
        self.machine.start_drawing()
        return ToolResult(
            "confirm_number", "ok", "La caricatura se ha enviado al robot"
        )

    async def _require_idle(self) -> None:
        status = (await self._robot.get_status()).strip().lower()
        if status != "idle":
            raise RobotUnavailableError(status or "unknown")
