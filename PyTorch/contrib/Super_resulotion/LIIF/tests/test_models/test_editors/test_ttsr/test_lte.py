# Copyright (c) OpenMMLab. All rights reserved.
import torch
import torch_sdaa

from mmagic.registry import MODELS


def test_lte():
    model_cfg = dict(
        type='LTE',
        requires_grad=False,
        pixel_range=1.,
        load_pretrained_vgg=False)

    lte = MODELS.build(model_cfg)
    assert lte.__class__.__name__ == 'LTE'

    x = torch.rand(2, 3, 64, 64)

    x_level3, x_level2, x_level1 = lte(x)
    assert x_level1.shape == (2, 64, 64, 64)
    assert x_level2.shape == (2, 128, 32, 32)
    assert x_level3.shape == (2, 256, 16, 16)


def teardown_module():
    import gc
    gc.collect()
    globals().clear()
    locals().clear()
