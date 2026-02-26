"""FEM→PD/SPG 자동 전환 기준.

FEM 해석 결과(응력/변형률)에서 PD/SPG로 전환할 요소를 판별한다.
기준을 초과하는 요소 + 인접 요소(버퍼 레이어)를 PD 영역으로 지정한다.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SwitchingCriteria:
    """FEM→PD/SPG 전환 판별 기준.

    두 기준 중 하나라도 초과하면 전환 대상으로 판별한다.

    Args:
        von_mises_threshold: Von Mises 응력 임계값 [Pa]
        max_strain_threshold: 최대 주변형률 임계값
        buffer_layers: 인접 요소 확장 레이어 수 (전환 영역 안정화)
    """
    von_mises_threshold: Optional[float] = None
    max_strain_threshold: Optional[float] = None
    buffer_layers: int = 1

    def evaluate(
        self,
        gauss_stress: np.ndarray,
        gauss_strain: Optional[np.ndarray],
        n_elements: int,
        n_gauss: int,
        elements: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """전환 대상 요소 마스크 반환.

        Args:
            gauss_stress: (total_gauss, dim, dim) 가우스점 응력 텐서
            gauss_strain: (total_gauss, dim, dim) 가우스점 변형률 텐서 (None 가능)
            n_elements: 요소 수
            n_gauss: 요소당 가우스점 수
            elements: (n_elements, npe) 요소 연결 (buffer 확장 시 필요)

        Returns:
            (n_elements,) bool — PD 전환 대상 요소 마스크
        """
        mask = np.zeros(n_elements, dtype=bool)

        # 1. Von Mises 응력 기준
        if self.von_mises_threshold is not None:
            vm = _compute_element_von_mises(gauss_stress, n_elements, n_gauss)
            mask |= (vm > self.von_mises_threshold)

        # 2. 최대 주변형률 기준
        if self.max_strain_threshold is not None and gauss_strain is not None:
            max_strain = _compute_element_max_principal_strain(
                gauss_strain, n_elements, n_gauss,
            )
            mask |= (max_strain > self.max_strain_threshold)

        # 3. 버퍼 레이어 확장 (인접 요소 포함)
        if self.buffer_layers > 0 and elements is not None:
            mask = _expand_mask_by_adjacency(mask, elements, self.buffer_layers)

        return mask


def _compute_element_von_mises(
    gauss_stress: np.ndarray,
    n_elements: int,
    n_gauss: int,
) -> np.ndarray:
    """요소별 최대 Von Mises 응력 계산.

    Args:
        gauss_stress: (total_gauss, dim, dim) 가우스점 응력
        n_elements: 요소 수
        n_gauss: 요소당 가우스점 수

    Returns:
        (n_elements,) 요소별 최대 Von Mises 응력
    """
    dim = gauss_stress.shape[1]
    total_gp = n_elements * n_gauss

    if dim == 3:
        # σ_vm = sqrt(0.5 * [(σ11-σ22)² + (σ22-σ33)² + (σ33-σ11)²
        #                     + 6*(σ12² + σ23² + σ13²)])
        s11 = gauss_stress[:, 0, 0]
        s22 = gauss_stress[:, 1, 1]
        s33 = gauss_stress[:, 2, 2]
        s12 = gauss_stress[:, 0, 1]
        s23 = gauss_stress[:, 1, 2]
        s13 = gauss_stress[:, 0, 2]

        vm = np.sqrt(0.5 * (
            (s11 - s22)**2 + (s22 - s33)**2 + (s33 - s11)**2
            + 6.0 * (s12**2 + s23**2 + s13**2)
        ))
    else:
        # 2D: σ_vm = sqrt(σ11² - σ11·σ22 + σ22² + 3·σ12²)
        s11 = gauss_stress[:, 0, 0]
        s22 = gauss_stress[:, 1, 1]
        s12 = gauss_stress[:, 0, 1]

        vm = np.sqrt(s11**2 - s11 * s22 + s22**2 + 3.0 * s12**2)

    # 요소별 최대값
    vm_per_elem = vm.reshape(n_elements, n_gauss).max(axis=1)
    return vm_per_elem


def _compute_element_max_principal_strain(
    gauss_strain: np.ndarray,
    n_elements: int,
    n_gauss: int,
) -> np.ndarray:
    """요소별 최대 주변형률 계산.

    Args:
        gauss_strain: (total_gauss, dim, dim) 가우스점 변형률
        n_elements: 요소 수
        n_gauss: 요소당 가우스점 수

    Returns:
        (n_elements,) 요소별 최대 주변형률
    """
    # 각 가우스점의 최대 고유값 (주변형률)
    eigenvalues = np.linalg.eigvalsh(gauss_strain)  # (total_gp, dim)
    max_principal = eigenvalues.max(axis=1)  # (total_gp,)

    # 요소별 최대값
    return max_principal.reshape(n_elements, n_gauss).max(axis=1)


def _expand_mask_by_adjacency(
    mask: np.ndarray,
    elements: np.ndarray,
    n_layers: int,
) -> np.ndarray:
    """노드 인접성 기반으로 마스크를 확장한다.

    전환 대상 요소와 노드를 공유하는 인접 요소도 PD 영역에 포함시켜
    인터페이스 안정성을 확보한다.

    Args:
        mask: (n_elements,) 현재 전환 마스크
        elements: (n_elements, npe) 요소 연결
        n_layers: 확장 레이어 수

    Returns:
        확장된 마스크 (n_elements,)
    """
    expanded = mask.copy()

    for _ in range(n_layers):
        # 현재 전환 대상 요소가 사용하는 노드 집합
        flagged_elem_indices = np.where(expanded)[0]
        if len(flagged_elem_indices) == 0:
            break

        flagged_nodes = set(elements[flagged_elem_indices].ravel())

        # 해당 노드를 공유하는 모든 요소를 마스크에 추가
        for e_idx in range(len(elements)):
            if expanded[e_idx]:
                continue
            elem_nodes = set(elements[e_idx])
            if elem_nodes & flagged_nodes:
                expanded[e_idx] = True

    return expanded
