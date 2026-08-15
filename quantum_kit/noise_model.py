"""
Pure-Python noise models for quantum simulation.
Fully JSON-serializable, no qiskit-aer dependency.
"""

import json
import copy
import logging
from typing import Dict, Optional

logger = logging.getLogger("agent.quantum.noise")

NOISE_KINDS = {"depolarizing", "bitflip", "phaseflip", "amp_damping"}


class NoiseModel:
    """A JSON-serializable noise model for quantum circuits.

    Attributes:
        gate_errors: dict mapping gate name -> {"kind": str, "prob": float}
        readout_error: optional {"prob_0_to_1": float, "prob_1_to_0": float}
    """

    def __init__(self):
        self.gate_errors: Dict[str, dict] = {}
        self.readout_error: Optional[dict] = None

    def add_gate_error(self, gate: str, kind: str, prob: float):
        if kind not in NOISE_KINDS:
            raise ValueError(f"Unknown noise kind: {kind}. Use: {NOISE_KINDS}")
        self.gate_errors[gate] = {"kind": kind, "prob": prob}

    def set_readout_error(self, prob_0_to_1: float, prob_1_to_0: float):
        self.readout_error = {"prob_0_to_1": prob_0_to_1, "prob_1_to_0": prob_1_to_0}

    def to_dict(self) -> dict:
        d = {"gate_errors": self.gate_errors}
        if self.readout_error:
            d["readout_error"] = self.readout_error
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "NoiseModel":
        model = cls()
        model.gate_errors = copy.deepcopy(data.get("gate_errors", {}))
        model.readout_error = copy.deepcopy(data.get("readout_error"))
        return model

    def to_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_json(cls, path: str) -> "NoiseModel":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def generate_depolarizing(self, prob: float = 0.01):
        """Fill single-qubit gates with depolarizing noise at given probability."""
        for gate in ["u1", "u2", "u3", "h", "x", "y", "z", "s", "t", "rx", "ry", "rz"]:
            self.add_gate_error(gate, "depolarizing", prob)
        self.add_gate_error("cx", "depolarizing", prob * 2)
        self.add_gate_error("cz", "depolarizing", prob * 2)
        self.add_gate_error("swap", "depolarizing", prob * 2)

    def __repr__(self) -> str:
        gates = ", ".join(self.gate_errors.keys()) if self.gate_errors else "none"
        ro = f", readout={self.readout_error}" if self.readout_error else ""
        return f"NoiseModel(gates=[{gates}]{ro})"


def _apply_depolarizing(prob: float, num_qubits: int) -> list:
    """Return Kraus operators for depolarizing channel on n qubits."""
    import numpy as np
    from math import sqrt
    if num_qubits == 1:
        # ρ → (1-p)ρ + p/3 (XρX + YρY + ZρZ)
        I = np.eye(2, dtype=complex)
        X = np.array([[0,1],[1,0]], dtype=complex)
        Y = np.array([[0,-1j],[1j,0]], dtype=complex)
        Z = np.array([[1,0],[0,-1]], dtype=complex)
        return [sqrt(1 - prob) * I, sqrt(prob/3) * X, sqrt(prob/3) * Y, sqrt(prob/3) * Z]
    else:
        # Tensor product of single-qubit depolarizing on each qubit
        single = _apply_depolarizing(prob, 1)
        result = []
        from functools import reduce
        import itertools
        for combo in itertools.product(range(4), repeat=num_qubits):
            k = reduce(np.kron, [single[c] for c in combo])
            result.append(k)
        return result


def noisy_simulate(circuit, noise_model: NoiseModel, shots: int = 1024) -> dict:
    """Run a density-matrix simulation with noise using DensityMatrix.evolve."""
    from qiskit.quantum_info import DensityMatrix, Operator, Kraus
    import numpy as np

    n_qubits = circuit.num_qubits
    if n_qubits == 0:
        return {"success": False, "error": "Empty circuit"}

    rho = DensityMatrix.from_int(0, 2 ** n_qubits)
    qubit_indices = {q: i for i, q in enumerate(circuit.qubits)}

    for inst, qargs, cargs in circuit.data:
        name = inst.name
        if name == "measure":
            continue
        qids = [qubit_indices[q] for q in qargs]
        rho = rho.evolve(Operator(inst), qargs=qids)

        err_cfg = noise_model.gate_errors.get(name)
        if err_cfg and err_cfg["kind"] == "depolarizing":
            nq = len(qids)
            ks = _apply_depolarizing(err_cfg["prob"], nq)
            rho = rho.evolve(Kraus(ks), qargs=qids)

    probs = rho.probabilities_dict()
    counts = {k: int(v * shots) for k, v in probs.items()}
    total = sum(counts.values())
    if total < shots and counts:
        counts[max(counts, key=counts.get)] += shots - total

    return {
        "success": True,
        "counts": counts,
        "metadata": {"shots": shots, "noise_model": str(noise_model)},
    }

