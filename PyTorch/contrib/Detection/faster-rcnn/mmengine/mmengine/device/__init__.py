# Copyright (c) OpenMMLab. All rights reserved.
from .utils import (get_device, get_max_sdaa_memory, get_max_musa_memory,
                    is_sdaa_available, is_dipu_available, is_mlu_available,
                    is_mps_available, is_musa_available, is_npu_available,
                    is_npu_support_full_precision)

__all__ = [
    'get_max_sdaa_memory', 'get_device', 'is_sdaa_available',
    'is_mlu_available', 'is_mps_available', 'is_npu_available',
    'is_dipu_available', 'get_max_musa_memory', 'is_musa_available',
    'is_npu_support_full_precision'
]
