"""High-fidelity evaluation placeholder (fail closed).

SU2 is installed on this workstation, but no validated SU2-to-RCAIDE coupling
exists yet. Phase I therefore refuses to produce high-fidelity numbers: any call
raises instead of returning a fabricated aerodynamic value. P3 owns the analysis
identity, mesh convergence and pairing work.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

MESSAGE = (
    "high-fidelity evaluation is not implemented in Phase I P2; "
    "SU2 is installed but there is no validated coupling, mesh convergence "
    "study or acceptance protocol yet. No value was produced."
)


class HighFidelityBackend:
    """Fail-closed stand-in that never invents a high-fidelity observation."""

    def __init__(self, design_space: Any = None, task: Any = None) -> None:
        self.design_space = design_space
        self.task = task
        self.names = tuple(getattr(design_space, "names", ()))

    def preflight(self) -> Dict[str, Any]:
        raise NotImplementedError(MESSAGE)

    def evaluate(
        self,
        design: Mapping[str, float],
        task: Any = None,
        fidelity: str = "su2_euler",
        purpose: str = "search",
    ) -> Dict[str, Any]:
        raise NotImplementedError(MESSAGE)
