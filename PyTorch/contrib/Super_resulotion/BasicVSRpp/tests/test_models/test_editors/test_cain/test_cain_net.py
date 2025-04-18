# Copyright (c) OpenMMLab. All rights reserved.
import platform

import pytest
import torch
import torch_sdaa

from mmagic.registry import MODELS


@pytest.mark.skipif(
    'win' in platform.system().lower() and 'cu' in torch.__version__,
    reason='skip on windows-sdaa due to limited RAM.')
def test_cain_net_cpu():

    model_cfg = dict(type='CAINNet')

    # build model
    model = MODELS.build(model_cfg)

    # test attributes
    assert model.__class__.__name__ == 'CAINNet'

    # prepare data
    inputs0 = torch.rand(1, 2, 3, 5, 5)
    inputs = torch.rand(1, 2, 3, 256, 248)
    target = torch.rand(1, 3, 256, 248)

    # test on cpu
    output = model(inputs)
    output = model(inputs, padding_flag=True)
    model(inputs0, padding_flag=True)
    assert torch.is_tensor(output)
    assert output.shape == target.shape
    with pytest.raises(AssertionError):
        output = model(inputs[:, :1])

    model_cfg = dict(type='CAINNet', norm='in')
    model = MODELS.build(model_cfg)
    model(inputs)
    model_cfg = dict(type='CAINNet', norm='bn')
    model = MODELS.build(model_cfg)
    model(inputs)
    with pytest.raises(ValueError):
        model_cfg = dict(type='CAINNet', norm='lys')
        MODELS.build(model_cfg)


@pytest.mark.skipif(
    'win' in platform.system().lower() and 'cu' in torch.__version__,
    reason='skip on windows-sdaa due to limited RAM.')
def test_cain_net_cuda():

    # prepare data
    inputs0 = torch.rand(1, 2, 3, 5, 5)
    target0 = torch.rand(1, 3, 5, 5)
    inputs = torch.rand(1, 2, 3, 256, 248)
    target = torch.rand(1, 3, 256, 248)

    model_cfg = dict(type='CAINNet', norm='bn')
    model = MODELS.build(model_cfg)

    # test on gpu
    if torch.sdaa.is_available():
        model = model.sdaa()
        inputs = inputs.sdaa()
        target = target.sdaa()
        output = model(inputs)
        output = model(inputs, True)
        assert torch.is_tensor(output)
        assert output.shape == target.shape
        inputs0 = inputs0.sdaa()
        target0 = target0.sdaa()
        model(inputs0, padding_flag=True)

        model_cfg = dict(type='CAINNet', norm='in')
        model = MODELS.build(model_cfg).sdaa()
        model(inputs)
        model_cfg = dict(type='CAINNet', norm='bn')
        model = MODELS.build(model_cfg).sdaa()
        model(inputs)
        with pytest.raises(ValueError):
            model_cfg = dict(type='CAINNet', norm='lys')
            MODELS.build(model_cfg).sdaa()


def teardown_module():
    import gc
    gc.collect()
    globals().clear()
    locals().clear()
