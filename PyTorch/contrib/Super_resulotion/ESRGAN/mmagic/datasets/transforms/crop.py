# Copyright (c) OpenMMLab. All rights reserved.
import math
import random

import cv2 as cv
import mmcv
import numpy as np
import torch
import torch_sdaa
from mmcv.transforms import BaseTransform
from mmengine.hub import get_config
from mmengine.registry import DefaultScope
from mmengine.utils import is_list_of, is_tuple_of
from torch.nn.modules.utils import _pair

from mmagic.registry import TRANSFORMS
from mmagic.utils import get_box_info, random_choose_unknown, try_import

mmdet_apis = try_import('mmdet.apis')


@TRANSFORMS.register_module()
class Crop(BaseTransform):
    """Crop data to specific size for training.

    Args:
        keys (Sequence[str]): The images to be cropped.
        crop_size (Tuple[int]): Target spatial size (h, w).
        random_crop (bool): If set to True, it will random crop
            image. Otherwise, it will work as center crop. Default: True.
        is_pad_zeros (bool, optional): Whether to pad the image with 0 if
            crop_size is greater than image size. Default: False.
    """

    def __init__(self, keys, crop_size, random_crop=True, is_pad_zeros=False):

        if not is_tuple_of(crop_size, int):
            raise TypeError(
                'Elements of crop_size must be int and crop_size must be'
                f' tuple, but got {type(crop_size[0])} in {type(crop_size)}')

        self.keys = keys
        self.crop_size = crop_size
        self.random_crop = random_crop
        self.is_pad_zeros = is_pad_zeros

    def _crop(self, data):
        """Crop the data.

        Args:
            data (Union[List, np.ndarray]): Input data to crop.

        Returns:
            tuple: cropped data and corresponding crop box.
        """
        if not isinstance(data, list):
            data_list = [data]
        else:
            data_list = data

        crop_bbox_list = []
        data_list_ = []

        for item in data_list:
            data_h, data_w = item.shape[:2]
            crop_h, crop_w = self.crop_size

            if self.is_pad_zeros:

                crop_y_offset, crop_x_offset = 0, 0

                if crop_h > data_h:
                    crop_y_offset = (crop_h - data_h) // 2
                if crop_w > data_w:
                    crop_x_offset = (crop_w - data_w) // 2

                if crop_y_offset > 0 or crop_x_offset > 0:
                    pad_width = [(2 * crop_y_offset, 2 * crop_y_offset),
                                 (2 * crop_x_offset, 2 * crop_x_offset)]
                    if item.ndim == 3:
                        pad_width.append((0, 0))
                    item = np.pad(
                        item,
                        tuple(pad_width),
                        mode='constant',
                        constant_values=0)

                data_h, data_w = item.shape[:2]

            crop_h = min(data_h, crop_h)
            crop_w = min(data_w, crop_w)

            if self.random_crop:
                x_offset = np.random.randint(0, data_w - crop_w + 1)
                y_offset = np.random.randint(0, data_h - crop_h + 1)
            else:
                x_offset = max(0, (data_w - crop_w)) // 2
                y_offset = max(0, (data_h - crop_h)) // 2

            crop_bbox = [x_offset, y_offset, crop_w, crop_h]
            item_ = item[y_offset:y_offset + crop_h,
                         x_offset:x_offset + crop_w, ...]
            crop_bbox_list.append(crop_bbox)
            data_list_.append(item_)

        if not isinstance(data, list):
            return data_list_[0], crop_bbox_list[0]
        return data_list_, crop_bbox_list

    def transform(self, results):
        """Transform function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation.

        Returns:
            dict: A dict containing the processed data and information.
        """

        for k in self.keys:
            data_, crop_bbox = self._crop(results[k])
            results[k] = data_
            results[k + '_crop_bbox'] = crop_bbox
        results['crop_size'] = self.crop_size
        return results

    def __repr__(self):

        repr_str = self.__class__.__name__
        repr_str += (f'keys={self.keys}, crop_size={self.crop_size}, '
                     f'random_crop={self.random_crop}')

        return repr_str


@TRANSFORMS.register_module()
class CropLike(BaseTransform):
    """Crop/pad the image in the target_key according to the size of image in
    the reference_key .

    Args:
        target_key (str): The key needs to be cropped.
        reference_key (str | None): The reference key, need its size.
            Default: None.
    """

    def __init__(self, target_key, reference_key=None):

        assert reference_key and target_key
        self.target_key = target_key
        self.reference_key = reference_key

    def transform(self, results):
        """Transform function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation.
                Require self.target_key and self.reference_key.

        Returns:
            dict: A dict containing the processed data and information.
                Modify self.target_key.
        """

        size = results[self.reference_key].shape
        old_image = results[self.target_key]
        old_size = old_image.shape
        h, w = old_size[:2]
        new_size = size[:2] + old_size[2:]
        h_cover, w_cover = min(h, size[0]), min(w, size[1])

        format_image = np.zeros(new_size, dtype=old_image.dtype)
        format_image[:h_cover, :w_cover] = old_image[:h_cover, :w_cover]
        results[self.target_key] = format_image

        return results

    def __repr__(self):

        return (self.__class__.__name__ + f' target_key={self.target_key}, ' +
                f'reference_key={self.reference_key}')


@TRANSFORMS.register_module()
class FixedCrop(BaseTransform):
    """Crop paired data (at a specific position) to specific size for training.

    Args:
        keys (Sequence[str]): The images to be cropped.
        crop_size (Tuple[int]): Target spatial size (h, w).
        crop_pos (Tuple[int]): Specific position (x, y). If set to None,
            random initialize the position to crop paired data batch.
            Default: None.
    """

    def __init__(self, keys, crop_size, crop_pos=None):

        if not is_tuple_of(crop_size, int):
            raise TypeError(
                'Elements of crop_size must be int and crop_size must be'
                f' tuple, but got {type(crop_size[0])} in {type(crop_size)}')
        if not is_tuple_of(crop_pos, int) and (crop_pos is not None):
            raise TypeError(
                'Elements of crop_pos must be int and crop_pos must be'
                f' tuple or None, but got {type(crop_pos[0])} in '
                f'{type(crop_pos)}')

        self.keys = keys
        self.crop_size = crop_size
        self.crop_pos = crop_pos

    def _crop(self, data, x_offset, y_offset, crop_w, crop_h):
        """Crop the data.

        Args:
            data (Union[List, np.ndarray]): Input data to crop.
            x_offset (int): The offset of x axis.
            y_offset (int): The offset of y axis.
            crop_w (int): The width of crop bbox.
            crop_h (int): The height of crop bbox.

        Returns:
            tuple: cropped data and corresponding crop box.
        """
        crop_bbox = [x_offset, y_offset, crop_w, crop_h]
        data_ = data[y_offset:y_offset + crop_h, x_offset:x_offset + crop_w,
                     ...]

        return data_, crop_bbox

    def transform(self, results):
        """Transform function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation.

        Returns:
            dict: A dict containing the processed data and information.
        """

        if isinstance(results[self.keys[0]], list):
            data_h, data_w = results[self.keys[0]][0].shape[:2]
        else:
            data_h, data_w = results[self.keys[0]].shape[:2]
        crop_h, crop_w = self.crop_size
        crop_h = min(data_h, crop_h)
        crop_w = min(data_w, crop_w)

        if self.crop_pos is None:
            x_offset = np.random.randint(0, data_w - crop_w + 1)
            y_offset = np.random.randint(0, data_h - crop_h + 1)
        else:
            x_offset, y_offset = self.crop_pos
            crop_w = min(data_w - x_offset, crop_w)
            crop_h = min(data_h - y_offset, crop_h)

        for k in self.keys:
            images = results[k]
            is_list = isinstance(images, list)
            if not is_list:
                images = [images]
            cropped_images = []
            crop_bbox = None
            for image in images:
                # In fixed crop for paired images, sizes should be the same
                if (image.shape[0] != data_h or image.shape[1] != data_w):
                    raise ValueError(
                        'The sizes of paired images should be the same. '
                        f'Expected ({data_h}, {data_w}), '
                        f'but got ({image.shape[0]}, '
                        f'{image.shape[1]}).')
                data_, crop_bbox = self._crop(image, x_offset, y_offset,
                                              crop_w, crop_h)
                cropped_images.append(data_)
            results[k + '_crop_bbox'] = crop_bbox
            if not is_list:
                cropped_images = cropped_images[0]
            results[k] = cropped_images
        results['crop_size'] = self.crop_size
        results['crop_pos'] = self.crop_pos

        return results

    def __repr__(self):

        repr_str = self.__class__.__name__
        repr_str += (f'keys={self.keys}, crop_size={self.crop_size}, '
                     f'crop_pos={self.crop_pos}')

        return repr_str


@TRANSFORMS.register_module()
class ModCrop(BaseTransform):
    """Mod crop images, used during testing.

    Required keys are "scale" and "KEY",
    added or modified keys are "KEY".

    Args:
        key (str): The key of image. Default: 'gt'
    """

    def __init__(self, key='gt') -> None:
        super().__init__()

        self.key = key

    def transform(self, results):
        """Transform function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation.

        Returns:
            dict: A dict containing the processed data and information.
        """

        img = results[self.key].copy()
        scale = results['scale']
        if img.ndim in [2, 3]:
            h, w = img.shape[0], img.shape[1]
            h_remainder, w_remainder = h % scale, w % scale
            img = img[:h - h_remainder, :w - w_remainder, ...]
        else:
            raise ValueError(f'Wrong img ndim: {img.ndim}.')
        results[self.key] = img

        return results

    def __repr__(self):

        repr_str = self.__class__.__name__
        repr_str += f'(key={self.key})'

        return repr_str


@TRANSFORMS.register_module()
class PairedRandomCrop(BaseTransform):
    """Paired random crop.

    It crops a pair of img and gt images with corresponding locations.
    It also supports accepting img list and gt list.
    Required keys are "scale", "lq_key", and "gt_key",
    added or modified keys are "lq_key" and "gt_key".

    Args:
        gt_patch_size (int): cropped gt patch size.
        lq_key (str): Key of LQ img. Default: 'img'.
        gt_key (str): Key of GT img. Default: 'gt'.
    """

    def __init__(self, gt_patch_size, lq_key='img', gt_key='gt'):

        self.gt_patch_size = gt_patch_size
        self.lq_key = lq_key
        self.gt_key = gt_key

    def transform(self, results):
        """Transform function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation.

        Returns:
            dict: A dict containing the processed data and information.
        """

        scale = results['scale']
        lq_patch_size = self.gt_patch_size // scale

        lq_is_list = isinstance(results[self.lq_key], list)
        if not lq_is_list:
            results[self.lq_key] = [results[self.lq_key]]
        gt_is_list = isinstance(results[self.gt_key], list)
        if not gt_is_list:
            results[self.gt_key] = [results[self.gt_key]]

        h_lq, w_lq, _ = results[self.lq_key][0].shape
        h_gt, w_gt, _ = results[self.gt_key][0].shape

        if h_gt != h_lq * scale or w_gt != w_lq * scale:
            raise ValueError(
                f'Scale mismatches. GT ({h_gt}, {w_gt}) is not {scale}x '
                f'multiplication of LQ ({h_lq}, {w_lq}).')
        if h_lq < lq_patch_size or w_lq < lq_patch_size:
            raise ValueError(
                f'LQ ({h_lq}, {w_lq}) is smaller than patch size '
                f'({lq_patch_size}, {lq_patch_size}). Please check '
                f'{results[f"{self.lq_key}_path"]} and '
                f'{results[f"{self.gt_key}_path"]}.')

        # randomly choose top and left coordinates for img patch
        top = np.random.randint(h_lq - lq_patch_size + 1)
        left = np.random.randint(w_lq - lq_patch_size + 1)
        # crop img patch
        results[self.lq_key] = [
            v[top:top + lq_patch_size, left:left + lq_patch_size, ...]
            for v in results[self.lq_key]
        ]
        # crop corresponding gt patch
        top_gt, left_gt = int(top * scale), int(left * scale)
        results[self.gt_key] = [
            v[top_gt:top_gt + self.gt_patch_size,
              left_gt:left_gt + self.gt_patch_size, ...]
            for v in results[self.gt_key]
        ]

        if not lq_is_list:
            results[self.lq_key] = results[self.lq_key][0]
        if not gt_is_list:
            results[self.gt_key] = results[self.gt_key][0]

        return results

    def __repr__(self):

        repr_str = self.__class__.__name__
        repr_str += (f'(gt_patch_size={self.gt_patch_size}, '
                     f'lq_key={self.lq_key}, '
                     f'gt_key={self.gt_key})')

        return repr_str


@TRANSFORMS.register_module()
class RandomResizedCrop(BaseTransform):
    """Crop data to random size and aspect ratio.

    A crop of a random proportion of the original image
    and a random aspect ratio of the original aspect ratio is made.
    The cropped image is finally resized to a given size specified
    by 'crop_size'. Modified keys are the attributes specified in "keys".

    This code is partially adopted from
    torchvision.transforms.RandomResizedCrop:
    [https://pytorch.org/vision/stable/_modules/torchvision/transforms/\
        transforms.html#RandomResizedCrop].

    Args:
        keys (list[str]): The images to be resized and random-cropped.
        crop_size (int | tuple[int]): Target spatial size (h, w).
        scale (tuple[float], optional): Range of the proportion of the original
            image to be cropped. Default: (0.08, 1.0).
        ratio (tuple[float], optional): Range of aspect ratio of the crop.
            Default: (3. / 4., 4. / 3.).
        interpolation (str, optional): Algorithm used for interpolation.
            It can be only either one of the following:
            "nearest" | "bilinear" | "bicubic" | "area" | "lanczos".
            Default: "bilinear".
    """

    def __init__(self,
                 keys,
                 crop_size,
                 scale=(0.08, 1.0),
                 ratio=(3. / 4., 4. / 3.),
                 interpolation='bilinear'):

        assert keys, 'Keys should not be empty.'
        if isinstance(crop_size, int):
            crop_size = (crop_size, crop_size)
        elif not is_tuple_of(crop_size, int):
            raise TypeError('"crop_size" must be an integer '
                            'or a tuple of integers, but got '
                            f'{type(crop_size)}')
        if not is_tuple_of(scale, float):
            raise TypeError('"scale" must be a tuple of float, '
                            f'but got {type(scale)}')
        if not is_tuple_of(ratio, float):
            raise TypeError('"ratio" must be a tuple of float, '
                            f'but got {type(ratio)}')

        self.keys = keys
        self.crop_size = crop_size
        self.scale = scale
        self.ratio = ratio
        self.interpolation = interpolation

    def get_params(self, data):
        """Get parameters for a random sized crop.

        Args:
            data (np.ndarray): Image of type numpy array to be cropped.

        Returns:
            A tuple containing the coordinates of the top left corner
            and the chosen crop size.
        """

        data_h, data_w = data.shape[:2]
        area = data_h * data_w

        for _ in range(10):
            target_area = random.uniform(*self.scale) * area
            log_ratio = (math.log(self.ratio[0]), math.log(self.ratio[1]))
            aspect_ratio = math.exp(random.uniform(*log_ratio))

            crop_w = int(round(math.sqrt(target_area * aspect_ratio)))
            crop_h = int(round(math.sqrt(target_area / aspect_ratio)))

            if 0 < crop_w <= data_w and 0 < crop_h <= data_h:
                top = random.randint(0, data_h - crop_h)
                left = random.randint(0, data_w - crop_w)
                return top, left, crop_h, crop_w

        # Fall back to center crop
        in_ratio = float(data_w) / float(data_h)
        if (in_ratio < min(self.ratio)):
            crop_w = data_w
            crop_h = int(round(crop_w / min(self.ratio)))
        elif (in_ratio > max(self.ratio)):
            crop_h = data_h
            crop_w = int(round(crop_h * max(self.ratio)))
        else:  # whole image
            crop_w = data_w
            crop_h = data_h
        top = (data_h - crop_h) // 2
        left = (data_w - crop_w) // 2

        return top, left, crop_h, crop_w

    def transform(self, results):
        """Transform function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation.

        Returns:
            dict: A dict containing the processed data and information.
        """

        for k in self.keys:
            top, left, crop_h, crop_w = self.get_params(results[k])
            crop_bbox = [top, left, crop_w, crop_h]
            results[k] = results[k][top:top + crop_h, left:left + crop_w, ...]
            results[k] = mmcv.imresize(
                results[k],
                self.crop_size,
                return_scale=False,
                interpolation=self.interpolation)
            results[k + '_crop_bbox'] = crop_bbox

        return results

    def __repr__(self):

        repr_str = self.__class__.__name__
        repr_str += (f'(keys={self.keys}, crop_size={self.crop_size}, '
                     f'scale={self.scale}, ratio={self.ratio}, '
                     f'interpolation={self.interpolation})')

        return repr_str


@TRANSFORMS.register_module()
class CropAroundCenter(BaseTransform):
    """Randomly crop the images around unknown area in the center 1/4 images.

    This cropping strategy is adopted in GCA matting. The `unknown area` is the
    same as `semi-transparent area`.
    https://arxiv.org/pdf/2001.04069.pdf

    It retains the center 1/4 images and resizes the images to 'crop_size'.
    Required keys are "fg", "bg", "trimap" and "alpha", added or modified keys
    are "crop_bbox", "fg", "bg", "trimap" and "alpha".

    Args:
        crop_size (int | tuple): Desired output size. If int, square crop is
            applied.
    """

    def __init__(self, crop_size):
        if is_tuple_of(crop_size, int):
            assert len(crop_size) == 2, 'length of crop_size must be 2.'
        elif not isinstance(crop_size, int):
            raise TypeError('crop_size must be int or a tuple of int, but got '
                            f'{type(crop_size)}')
        self.crop_size = _pair(crop_size)

    def transform(self, results):
        """Transform function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation.

        Returns:
            dict: A dict containing the processed data and information.
        """

        fg = results['fg']
        alpha = results['alpha']
        trimap = results['trimap']
        bg = results['bg']
        h, w = fg.shape[:2]
        assert bg.shape == fg.shape, (f'shape of bg {bg.shape} should be the '
                                      f'same as fg {fg.shape}.')

        crop_h, crop_w = self.crop_size
        # Make sure h >= crop_h, w >= crop_w. If not, rescale imgs
        rescale_ratio = max(crop_h / h, crop_w / w)
        if rescale_ratio > 1:
            assert alpha.ndim == trimap.ndim
            ext_dim = (alpha.ndim == 3)

            new_h = max(int(h * rescale_ratio), crop_h)
            new_w = max(int(w * rescale_ratio), crop_w)
            fg = mmcv.imresize(fg, (new_w, new_h), interpolation='nearest')
            alpha = mmcv.imresize(
                alpha, (new_w, new_h), interpolation='nearest')
            trimap = mmcv.imresize(
                trimap, (new_w, new_h), interpolation='nearest')
            bg = mmcv.imresize(bg, (new_w, new_h), interpolation='bicubic')
            h, w = new_h, new_w

            if ext_dim:
                # mmcv.imresize will squeeze
                alpha = alpha[..., None]
                trimap = trimap[..., None]

        # resize to 1/4 to ignore small unknown patches
        small_trimap = mmcv.imresize(
            trimap, (w // 4, h // 4), interpolation='nearest')
        assert small_trimap.ndim == 2
        # find unknown area in center 1/4 region
        margin_h, margin_w = crop_h // 2, crop_w // 2
        sample_area = small_trimap[margin_h // 4:(h - margin_h) // 4,
                                   margin_w // 4:(w - margin_w) // 4]
        unknown_xs, unknown_ys = np.where(sample_area == 128)
        unknown_num = len(unknown_xs)
        if unknown_num < 10:
            # too few unknown area in the center, crop from the whole image
            top = np.random.randint(0, h - crop_h + 1)
            left = np.random.randint(0, w - crop_w + 1)
        else:
            idx = np.random.randint(unknown_num)
            top = unknown_xs[idx] * 4
            left = unknown_ys[idx] * 4
        bottom = top + crop_h
        right = left + crop_w

        results['fg'] = fg[top:bottom, left:right]
        results['alpha'] = alpha[top:bottom, left:right]
        results['trimap'] = trimap[top:bottom, left:right]
        results['bg'] = bg[top:bottom, left:right]
        results['crop_bbox'] = (left, top, right, bottom)

        return results

    def __repr__(self):

        return self.__class__.__name__ + f'(crop_size={self.crop_size})'


@TRANSFORMS.register_module()
class CropAroundFg(BaseTransform):
    """Crop around the whole foreground in the segmentation mask.

    Required keys are "seg" and the keys in argument `keys`.
    Meanwhile, "seg" must be in argument `keys`. Added or modified keys are
    "crop_bbox" and the keys in argument `keys`.

    Args:
        keys (Sequence[str]): The images to be cropped. It must contain
            'seg'.
        bd_ratio_range (tuple, optional): The range of the boundary (bd) ratio
            to select from. The boundary ratio is the ratio of the boundary to
            the minimal bbox that contains the whole foreground given by
            segmentation. Default to (0.1, 0.4).
        test_mode (bool): Whether use test mode. In test mode, the tight crop
            area of foreground will be extended to the a square.
            Default to False.
    """

    def __init__(self, keys, bd_ratio_range=(0.1, 0.4), test_mode=False):

        if 'seg' not in keys:
            raise ValueError(f'"seg" must be in keys, but got {keys}')
        if (not is_tuple_of(bd_ratio_range, float)
                or len(bd_ratio_range) != 2):
            raise TypeError('bd_ratio_range must be a tuple of 2 int, but got '
                            f'{bd_ratio_range}')
        self.keys = keys
        self.bd_ratio_range = bd_ratio_range
        self.test_mode = test_mode

    def transform(self, results):
        """Transform function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation.

        Returns:
            dict: A dict containing the processed data and information.
        """

        seg = results['seg']
        height, width = seg.shape[:2]

        # get foreground bbox
        fg_coor = np.array(np.where(seg))
        top, left = np.amin(fg_coor, axis=1)
        bottom, right = np.amax(fg_coor, axis=1)

        # enlarge bbox
        long_side = np.maximum(bottom - top, right - left)
        if self.test_mode:
            bottom = top + long_side
            right = left + long_side
        boundary_ratio = np.random.uniform(*self.bd_ratio_range)
        boundary = int(np.round(boundary_ratio * long_side))
        # NOTE: Different from the original repo, we keep track of the four
        # corners of the bbox (left, top, right, bottom) while the original
        # repo use (top, left, height, width) to represent bbox. This may
        # introduce an difference of 1 pixel.
        top = max(top - boundary, 0)
        left = max(left - boundary, 0)
        bottom = min(bottom + boundary, height)
        right = min(right + boundary, width)

        for key in self.keys:
            results[key] = results[key][top:bottom, left:right]
        results['crop_bbox'] = (left, top, right, bottom)

        return results


@TRANSFORMS.register_module()
class CropAroundUnknown(BaseTransform):
    """Crop around unknown area with a randomly selected scale.

    Randomly select the w and h from a list of (w, h).
    Required keys are the keys in argument `keys`, added or
    modified keys are "crop_bbox" and the keys in argument `keys`.
    This class assumes value of "alpha" ranges from 0 to 255.

    Args:
        keys (Sequence[str]): The images to be cropped. It must contain
            'alpha'. If unknown_source is set to 'trimap', then it must also
            contain 'trimap'.
        crop_sizes (list[int | tuple[int]]): List of (w, h) to be selected.
        unknown_source (str, optional): Unknown area to select from. It must be
            'alpha' or 'trimap'. Default to 'alpha'.
        interpolations (str | list[str], optional): Interpolation method of
            mmcv.imresize. The interpolation operation will be applied when
            image size is smaller than the crop_size. If given as a list of
            str, it should have the same length as `keys`. Or if given as a
            str all the keys will be resized with the same method.
            Default to 'bilinear'.
    """

    def __init__(self,
                 keys,
                 crop_sizes,
                 unknown_source='alpha',
                 interpolations='bilinear'):
        if 'alpha' not in keys:
            raise ValueError(f'"alpha" must be in keys, but got {keys}')
        self.keys = keys

        if not isinstance(crop_sizes, list):
            raise TypeError(
                f'Crop sizes must be list, but got {type(crop_sizes)}.')
        self.crop_sizes = [_pair(crop_size) for crop_size in crop_sizes]
        if not is_tuple_of(self.crop_sizes[0], int):
            raise TypeError('Elements of crop_sizes must be int or tuple of '
                            f'int, but got {type(self.crop_sizes[0][0])}.')

        if unknown_source not in ['alpha', 'trimap']:
            raise ValueError('unknown_source must be "alpha" or "trimap", '
                             f'but got {unknown_source}')
        if unknown_source not in keys:
            # it could only be trimap, since alpha is checked before
            raise ValueError(
                'if unknown_source is "trimap", it must also be set in keys')
        self.unknown_source = unknown_source

        if isinstance(interpolations, str):
            self.interpolations = [interpolations] * len(self.keys)
        elif is_list_of(interpolations, str) and len(interpolations) == len(
                self.keys):
            self.interpolations = interpolations
        else:
            raise TypeError(
                'interpolations must be a str or list of str with '
                f'the same length as keys, but got {interpolations}')

    def transform(self, results):
        """Transform function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation.

        Returns:
            dict: A dict containing the processed data and information.
        """

        h, w = results[self.keys[0]].shape[:2]

        rand_ind = np.random.randint(len(self.crop_sizes))
        crop_h, crop_w = self.crop_sizes[rand_ind]

        # Make sure h >= crop_h, w >= crop_w. If not, rescale imgs
        rescale_ratio = max(crop_h / h, crop_w / w)
        if rescale_ratio > 1:

            h = max(int(h * rescale_ratio), crop_h)
            w = max(int(w * rescale_ratio), crop_w)
            for key, interpolation in zip(self.keys, self.interpolations):
                ext_dim = (results[key].ndim == 3) and (results[key].shape[-1]
                                                        == 1)
                results[key] = mmcv.imresize(
                    results[key], (w, h), interpolation=interpolation)
                if ext_dim:
                    results[key] = results[key][..., None]

        # Select the cropping top-left point which is an unknown pixel
        if self.unknown_source == 'alpha':
            unknown = (results['alpha'] > 0) & (results['alpha'] < 255)
        else:
            unknown = results['trimap'] == 128
        top, left = random_choose_unknown(unknown.squeeze(), (crop_h, crop_w))

        bottom = top + crop_h
        right = left + crop_w

        for key in self.keys:
            results[key] = results[key][top:bottom, left:right]
        results['crop_bbox'] = (left, top, right, bottom)

        return results

    def __repr__(self):

        repr_str = self.__class__.__name__
        repr_str += (f'(keys={self.keys}, crop_sizes={self.crop_sizes}, '
                     f"unknown_source='{self.unknown_source}', "
                     f'interpolations={self.interpolations})')

        return repr_str


@TRANSFORMS.register_module()
class RandomCropLongEdge(BaseTransform):
    """Random crop the given image by the long edge.

    Args:
        keys (list[str]): The images to be cropped.
    """

    def __init__(self, keys='img'):
        assert keys, 'Keys should not be empty.'
        if not isinstance(keys, list):
            keys = [keys]
        self.keys = keys

    def transform(self, results):
        """Call function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation.

        Returns:
            dict: A dict containing the processed data and information.
        """

        for key in self.keys:
            img = results[key]
            img_height, img_width = img.shape[:2]
            crop_size = min(img_height, img_width)
            y1 = 0 if img_height == crop_size else \
                np.random.randint(0, img_height - crop_size)
            x1 = 0 if img_width == crop_size else \
                np.random.randint(0, img_width - crop_size)
            y2, x2 = y1 + crop_size - 1, x1 + crop_size - 1

            img = mmcv.imcrop(img, bboxes=np.array([x1, y1, x2, y2]))
            results[key] = img

        return results

    def __repr__(self):
        repr_str = self.__class__.__name__
        repr_str += (f'(keys={self.keys})')
        return repr_str


@TRANSFORMS.register_module()
class CenterCropLongEdge(BaseTransform):
    """Center crop the given image by the long edge.

    Args:
        keys (list[str]): The images to be cropped.
    """

    def __init__(self, keys='img'):
        assert keys, 'Keys should not be empty.'
        if not isinstance(keys, list):
            keys = [keys]
        self.keys = keys

    def transform(self, results):
        """Call function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation.

        Returns:
            dict: A dict containing the processed data and information.
        """

        for key in self.keys:
            img = results[key]
            img_height, img_width = img.shape[:2]
            crop_size = min(img_height, img_width)
            y1 = 0 if img_height == crop_size else \
                int(round(img_height - crop_size) / 2)
            x1 = 0 if img_width == crop_size else \
                int(round(img_width - crop_size) / 2)
            y2 = y1 + crop_size - 1
            x2 = x1 + crop_size - 1

            img = mmcv.imcrop(img, bboxes=np.array([x1, y1, x2, y2]))
            results[key] = img

        return results

    def __repr__(self):
        repr_str = self.__class__.__name__
        repr_str += (f'(keys={self.keys})')
        return repr_str


@TRANSFORMS.register_module()
class InstanceCrop(BaseTransform):
    """Use maskrcnn to detect instances on image.

    Mask R-CNN is used to detect the instance on the image
    pred_bbox is used to segment the instance on the image

    Args:
        config_file (str): config file name relative to detectron2's "configs/"
        key (str): Unused
        box_num_upbound (int):The upper limit on the number of instances
            in the figure
    """

    def __init__(self,
                 config_file,
                 from_pretrained=None,
                 key='img',
                 box_num_upbound=-1,
                 finesize=256):

        assert mmdet_apis is not None, (
            "Cannot import 'mmdet'. Please install 'mmdet' via "
            "\"mim install 'mmdet >= 3.0.0'\".")

        cfg = get_config(config_file, pretrained=True)

        # loading checkpoint from local path
        if from_pretrained is not None:
            cfg.model.backbone.init_cfg.checkpoint = from_pretrained

        with DefaultScope.overwrite_default_scope('mmdet'):
            self.predictor = mmdet_apis.init_detector(cfg, cfg.model_path)

        self.key = key
        self.box_num_upbound = box_num_upbound
        self.final_size = finesize

    def transform(self, results: dict) -> dict:
        """The transform function of InstanceCrop.

        Args:
            results (dict): A dict containing the necessary information and
                data for Conversion

        Returns:
            results (dict): A dict containing the processed data
                and information.
        """
        # get consistent box prediction based on L channel

        full_img = results['img']
        full_img_size = results['ori_img_shape'][:-1][::-1]
        pred_bbox, pred_scores = self.predict_bbox(full_img)

        if self.box_num_upbound > 0 and pred_bbox.shape[
                0] > self.box_num_upbound:
            index_mask = np.argsort(pred_scores, axis=0)
            index_mask = index_mask[pred_scores.shape[0] -
                                    self.box_num_upbound:pred_scores.shape[0]]
            pred_bbox = pred_bbox[index_mask]

        # get cropped images and box info
        cropped_img_list = []
        index_list = range(len(pred_bbox))
        box_info, box_info_2x, box_info_4x, box_info_8x = np.zeros(
            (4, len(index_list), 6))
        for i in index_list:
            startx, starty, endx, endy = pred_bbox[i]
            cropped_img = full_img[starty:endy, startx:endx, :]
            cropped_img_list.append(cropped_img)
            box_info[i] = np.array(
                get_box_info(pred_bbox[i], full_img_size, self.final_size))
            box_info_2x[i] = np.array(
                get_box_info(pred_bbox[i], full_img_size,
                             self.final_size // 2))
            box_info_4x[i] = np.array(
                get_box_info(pred_bbox[i], full_img_size,
                             self.final_size // 4))
            box_info_8x[i] = np.array(
                get_box_info(pred_bbox[i], full_img_size,
                             self.final_size // 8))

        # update results
        if len(pred_bbox) > 0:
            results['cropped_img'] = cropped_img_list
            results['box_info'] = torch.from_numpy(box_info).type(torch.long)
            results['box_info_2x'] = torch.from_numpy(box_info_2x).type(
                torch.long)
            results['box_info_4x'] = torch.from_numpy(box_info_4x).type(
                torch.long)
            results['box_info_8x'] = torch.from_numpy(box_info_8x).type(
                torch.long)
            results['empty_box'] = False
        else:
            results['empty_box'] = True
        return results

    def predict_bbox(self, image):
        lab_image = cv.cvtColor(image, cv.COLOR_BGR2LAB)
        l_channel, _, _ = cv.split(lab_image)
        l_stack = np.stack([l_channel, l_channel, l_channel], axis=2)

        with DefaultScope.overwrite_default_scope('mmdet'):
            with torch.no_grad():
                results = mmdet_apis.inference_detector(
                    self.predictor, l_stack)

        bboxes = results.pred_instances.bboxes.cpu().numpy().astype(np.int32)
        scores = results.pred_instances.scores.cpu().numpy()
        index_mask = [i for i, x in enumerate(scores) if x >= 0.7]
        scores = np.array(scores[index_mask])
        bboxes = np.array(bboxes[index_mask])
        return bboxes, scores
