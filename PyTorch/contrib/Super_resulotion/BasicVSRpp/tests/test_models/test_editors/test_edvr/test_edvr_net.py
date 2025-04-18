# Copyright (c) OpenMMLab. All rights reserved.
import pytest
import torch
import torch_sdaa

from mmagic.models.editors.edvr.edvr_net import (EDVRNet, PCDAlignment,
                                                 TSAFusion)


def test_pcd_alignment():
    """Test PCDAlignment."""

    # cpu
    pcd_alignment = PCDAlignment(mid_channels=4, deform_groups=2)
    input_list = []
    for i in range(3, 0, -1):
        input_list.append(torch.rand(1, 4, 2**i, 2**i))

    pcd_alignment = pcd_alignment
    input_list = [v for v in input_list]
    output = pcd_alignment(input_list, input_list)
    assert output.shape == (1, 4, 8, 8)

    with pytest.raises(AssertionError):
        pcd_alignment(input_list[0:2], input_list)

    # gpu
    if torch.sdaa.is_available():
        pcd_alignment = PCDAlignment(mid_channels=4, deform_groups=2)
        input_list = []
        for i in range(3, 0, -1):
            input_list.append(torch.rand(1, 4, 2**i, 2**i))

        pcd_alignment = pcd_alignment.sdaa()
        input_list = [v.sdaa() for v in input_list]
        output = pcd_alignment(input_list, input_list)
        assert output.shape == (1, 4, 8, 8)

        with pytest.raises(AssertionError):
            pcd_alignment(input_list[0:2], input_list)


def test_tsa_fusion():
    """Test TSAFusion."""

    # cpu
    tsa_fusion = TSAFusion(mid_channels=4, num_frames=5, center_frame_idx=2)
    input_tensor = torch.rand(1, 5, 4, 8, 8)

    output = tsa_fusion(input_tensor)
    assert output.shape == (1, 4, 8, 8)

    # gpu
    if torch.sdaa.is_available():
        tsa_fusion = tsa_fusion.sdaa()
        input_tensor = input_tensor.sdaa()
        output = tsa_fusion(input_tensor)
        assert output.shape == (1, 4, 8, 8)


def test_edvr_net():
    """Test EDVRNet."""

    # cpu

    # with tsa
    edvrnet = EDVRNet(
        3,
        3,
        mid_channels=8,
        num_frames=5,
        deform_groups=2,
        num_blocks_extraction=1,
        num_blocks_reconstruction=1,
        center_frame_idx=2,
        with_tsa=True)
    input_tensor = torch.rand(1, 5, 3, 8, 8)
    output = edvrnet(input_tensor)
    assert output.shape == (1, 3, 32, 32)

    # without tsa
    edvrnet = EDVRNet(
        3,
        3,
        mid_channels=8,
        num_frames=5,
        deform_groups=2,
        num_blocks_extraction=1,
        num_blocks_reconstruction=1,
        center_frame_idx=2,
        with_tsa=False)

    output = edvrnet(input_tensor)
    assert output.shape == (1, 3, 32, 32)

    with pytest.raises(AssertionError):
        # The height and width of inputs should be a multiple of 4
        input_tensor = torch.rand(1, 5, 3, 3, 3)
        edvrnet(input_tensor)

    # gpu
    if torch.sdaa.is_available():
        # with tsa
        edvrnet = EDVRNet(
            3,
            3,
            mid_channels=8,
            num_frames=5,
            deform_groups=2,
            num_blocks_extraction=1,
            num_blocks_reconstruction=1,
            center_frame_idx=2,
            with_tsa=True).sdaa()
        input_tensor = torch.rand(1, 5, 3, 8, 8).sdaa()
        output = edvrnet(input_tensor)
        assert output.shape == (1, 3, 32, 32)

        # without tsa
        edvrnet = EDVRNet(
            3,
            3,
            mid_channels=8,
            num_frames=5,
            deform_groups=2,
            num_blocks_extraction=1,
            num_blocks_reconstruction=1,
            center_frame_idx=2,
            with_tsa=False).sdaa()

        output = edvrnet(input_tensor)
        assert output.shape == (1, 3, 32, 32)

        with pytest.raises(AssertionError):
            # The height and width of inputs should be a multiple of 4
            input_tensor = torch.rand(1, 5, 3, 3, 3).sdaa()
            edvrnet(input_tensor)


def teardown_module():
    import gc
    gc.collect()
    globals().clear()
    locals().clear()
