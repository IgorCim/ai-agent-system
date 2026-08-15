"""
Quantum Tools for Agent
- Simulate circuits (Aer or fallback basic simulator)
- Load/save noise models from JSON (pure Python, no aer dependency)
- Run on real IBM hardware (requires API key)
"""

import json
import logging
from typing import Optional

from qiskit import QuantumCircuit

logger = logging.getLogger("agent.quantum")

# Try Aer first, fall back to basic + pure noise
try:
    from qiskit_aer import AerSimulator
    HAS_AER = True
except Exception as e:
    logger.warning(f"qiskit-aer not available ({e}), using pure-Python fallback")
    HAS_AER = False

try:
    from quantum_kit.noise_model import NoiseModel, noisy_simulate
    HAS_PURE_NOISE = True
except Exception as e:
    logger.warning(f"pure noise model not available: {e}")
    HAS_PURE_NOISE = False


def _basic_simulate(circuit: QuantumCircuit, shots: int = 1024) -> dict:
    from qiskit.quantum_info import Statevector
    try:
        circ = circuit.remove_final_measurements(inplace=False)
        sv = Statevector.from_instruction(circ)
        probs = sv.probabilities_dict()
        counts = {k: int(v * shots) for k, v in probs.items()}
        total = sum(counts.values())
        if total < shots and counts:
            counts[max(counts, key=counts.get)] += shots - total
        return {"success": True, "counts": counts, "metadata": {"shots": shots, "simulator": "basic_statevector"}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def simulate(circuit: QuantumCircuit, shots: int = 1024, noise_model=None) -> dict:
    if noise_model is not None:
        if HAS_PURE_NOISE and isinstance(noise_model, NoiseModel):
            return noisy_simulate(circuit, noise_model, shots)
        elif HAS_AER:
            return _aer_simulate(circuit, shots, noise_model)
        else:
            return {"success": False, "error": "Noise model requires qiskit-aer or pure noise module"}
    if HAS_AER:
        return _aer_simulate(circuit, shots)
    return _basic_simulate(circuit, shots)


def _aer_simulate(circuit: QuantumCircuit, shots: int = 1024, noise_model=None) -> dict:
    try:
        from qiskit_aer import AerSimulator
        from qiskit import transpile
        sim = AerSimulator(noise_model=noise_model) if noise_model else AerSimulator()
        compiled = transpile(circuit, sim)
        result = sim.run(compiled, shots=shots).result()
        counts = result.get_counts()
        return {"success": True, "counts": counts, "metadata": {"shots": shots, "has_noise": noise_model is not None}}
    except Exception as e:
        logger.warning(f"Aer simulation failed ({e}), falling back to basic")
        return _basic_simulate(circuit, shots)


def load_noise_model(path: str):
    """Load noise model from JSON file. Returns NoiseModel (pure) if aer unavailable."""
    if HAS_PURE_NOISE:
        try:
            return NoiseModel.from_json(path)
        except Exception as e:
            logger.error(f"Failed to load noise model via pure: {e}")
    if HAS_AER:
        try:
            from qiskit_aer.noise import NoiseModel as AerNoiseModel
            with open(path, 'r') as f:
                data = json.load(f)
            return AerNoiseModel.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load noise model via aer: {e}")
    return None


def generate_default_noise(prob: float = 0.01) -> Optional[dict]:
    """Generate a default depolarizing noise model and return it as dict."""
    if HAS_PURE_NOISE:
        model = NoiseModel()
        model.generate_depolarizing(prob)
        return {"model": model, "description": f"Depolarizing noise p={prob}"}
    return {"model": None, "description": "Noise model unavailable (install qiskit-aer or quantum_kit.noise_model)"}


def run_on_real(circuit: QuantumCircuit, api_key: str, backend_name: str = "ibm_brisbane", shots: int = 1024) -> dict:
    try:
        from qiskit_ibm_runtime import QiskitRuntimeService, Sampler
        service = QiskitRuntimeService(channel="ibm_quantum", token=api_key)
        backend = service.backend(backend_name)
        sampler = Sampler(backend)
        job = sampler.run(circuits=circuit, shots=shots)
        result = job.result()
        quasi_dist = result.quasi_dists[0]
        counts = {k: int(v * shots) for k, v in quasi_dist.items()}
        return {
            "success": True,
            "counts": counts,
            "shots": shots,
            "backend": backend_name,
            "job_id": job.job_id(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
