"""재료 라이브러리.

미리 정의된 생체역학 재료 속성.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Material:
    """재료 속성."""
    name: str
    E: float           # Young's modulus [MPa]
    nu: float          # Poisson's ratio
    rho: float         # 밀도 [kg/mm³]
    description: str = ""

    @property
    def K(self) -> float:
        """Bulk modulus [MPa]."""
        return self.E / (3 * (1 - 2 * self.nu))

    @property
    def mu(self) -> float:
        """Shear modulus [MPa]."""
        return self.E / (2 * (1 + self.nu))

    @property
    def lam(self) -> float:
        """Lamé's first parameter [MPa]."""
        return self.E * self.nu / ((1 + self.nu) * (1 - 2 * self.nu))


class MaterialLibrary:
    """생체역학 재료 라이브러리.

    미리 정의된 재료:
    - cortical_bone: 피질골 (E=17 GPa)
    - cancellous_bone: 해면골 (E=500 MPa)
    - disc: 추간판 (E=10 MPa)
    - ligament: 인대 (E=50 MPa)
    - cartilage: 연골 (E=10 MPa)
    - muscle: 근육 (E=1 MPa)
    """

    _materials: Dict[str, Material] = {
        # 뼈
        "cortical_bone": Material(
            name="cortical_bone",
            E=17000.0,      # 17 GPa
            nu=0.3,
            rho=1.85e-6,    # 1850 kg/m³
            description="피질골 (Cortical bone)"
        ),
        "cancellous_bone": Material(
            name="cancellous_bone",
            E=500.0,        # 500 MPa
            nu=0.3,
            rho=0.5e-6,     # 500 kg/m³
            description="해면골 (Cancellous/Trabecular bone)"
        ),
        "bone": Material(  # 일반 뼈 (cortical 기본)
            name="bone",
            E=17000.0,
            nu=0.3,
            rho=1.85e-6,
            description="뼈 (기본값: 피질골)"
        ),

        # 연부조직
        "disc": Material(
            name="disc",
            E=10.0,         # 10 MPa
            nu=0.45,
            rho=1.0e-6,     # 1000 kg/m³
            description="추간판 (Intervertebral disc)"
        ),
        "nucleus_pulposus": Material(
            name="nucleus_pulposus",
            E=1.0,          # 1 MPa (매우 부드러움)
            nu=0.49,        # 거의 비압축성
            rho=1.0e-6,
            description="수핵 (Nucleus pulposus)"
        ),
        "annulus_fibrosus": Material(
            name="annulus_fibrosus",
            E=50.0,         # 50 MPa
            nu=0.45,
            rho=1.0e-6,
            description="섬유륜 (Annulus fibrosus)"
        ),
        "ligament": Material(
            name="ligament",
            E=50.0,         # 50 MPa
            nu=0.4,
            rho=1.0e-6,
            description="인대 (Ligament)"
        ),
        "cartilage": Material(
            name="cartilage",
            E=10.0,         # 10 MPa
            nu=0.4,
            rho=1.1e-6,
            description="연골 (Cartilage)"
        ),
        "muscle": Material(
            name="muscle",
            E=1.0,          # 1 MPa
            nu=0.49,
            rho=1.06e-6,
            description="근육 (Muscle)"
        ),

        # 임플란트
        "titanium": Material(
            name="titanium",
            E=110000.0,     # 110 GPa
            nu=0.34,
            rho=4.5e-6,     # 4500 kg/m³
            description="티타늄 (Titanium alloy)"
        ),
        "peek": Material(
            name="peek",
            E=3500.0,       # 3.5 GPa
            nu=0.4,
            rho=1.3e-6,
            description="PEEK (Polyether ether ketone)"
        ),
        "stainless_steel": Material(
            name="stainless_steel",
            E=200000.0,     # 200 GPa
            nu=0.3,
            rho=8.0e-6,     # 8000 kg/m³
            description="스테인리스 스틸"
        ),
    }

    # 별칭
    _aliases = {
        "bone": "cortical_bone",
        "soft": "disc",
        "metal": "titanium",
    }

    @classmethod
    def get(cls, name: str) -> Material:
        """재료 가져오기.

        Args:
            name: 재료 이름 또는 별칭

        Returns:
            Material 객체

        Raises:
            KeyError: 재료를 찾을 수 없음
        """
        # 별칭 해결
        resolved = cls._aliases.get(name, name)

        if resolved in cls._materials:
            return cls._materials[resolved]

        raise KeyError(f"재료를 찾을 수 없습니다: {name}. "
                       f"사용 가능: {list(cls._materials.keys())}")

    @classmethod
    def list_materials(cls) -> Dict[str, str]:
        """사용 가능한 재료 목록."""
        return {name: mat.description for name, mat in cls._materials.items()}

    @classmethod
    def add_material(cls, material: Material):
        """사용자 정의 재료 추가."""
        cls._materials[material.name] = material

    @classmethod
    def create(cls, name: str, E: float, nu: float,
               rho: float = 1.0e-6, description: str = "") -> Material:
        """새 재료 생성 및 등록.

        Args:
            name: 재료 이름
            E: Young's modulus [MPa]
            nu: Poisson's ratio
            rho: 밀도 [kg/mm³]
            description: 설명

        Returns:
            생성된 Material 객체
        """
        material = Material(name=name, E=E, nu=nu, rho=rho, description=description)
        cls._materials[name] = material
        return material
