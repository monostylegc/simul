"""통합 FEA 프레임워크.

FEM, Peridynamics, SPG 세 솔버를 동일한 API로 사용할 수 있다.
Method만 변경하면 나머지 코드는 동일하게 유지된다.

단일 물체 해석:
    from src.fea.framework import init, create_domain, Material, Solver, Method

    init()
    domain = create_domain(Method.FEM, dim=2, origin=(0, 0), size=(1.0, 0.2), n_divisions=(50, 10))

    left = domain.select(axis=0, value=0.0)
    right = domain.select(axis=0, value=1.0)
    domain.set_fixed(left)
    domain.set_force(right, [100.0, 0.0])

    mat = Material(E=1e6, nu=0.3, density=1000, dim=2)
    solver = Solver(domain, mat)
    result = solver.solve()
    u = solver.get_displacements()

다중 물체 접촉 해석:
    from src.fea.framework import init, create_domain, Material, Method, Scene, ContactType

    init()
    bone = create_domain(Method.SPG, dim=2, ...)
    screw = create_domain(Method.FEM, dim=2, ...)

    scene = Scene()
    scene.add(bone, bone_mat)
    scene.add(screw, screw_mat)
    scene.add_contact(bone, screw, method=ContactType.PENALTY, penalty=1e8)
    result = scene.solve(mode="static")
"""

from .runtime import init, Backend, Precision, get_backend, get_precision
from .domain import create_domain, Domain, Method
from .material import Material
from .solver import Solver
from .result import SolveResult
from .contact import ContactType
from .scene import Scene

__all__ = [
    "init",
    "Backend",
    "Precision",
    "get_backend",
    "get_precision",
    "create_domain",
    "Domain",
    "Method",
    "Material",
    "Solver",
    "SolveResult",
    "ContactType",
    "Scene",
]
