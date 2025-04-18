# Copyright (c) 2020  PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import paddle
import paddle_sdaa
from paddle import ParamAttr
from paddle.nn import Linear
from paddle.regularizer import L2Decay
from .tsn_head import TSNHead
from ..registry import HEADS

from ..weight_init import weight_init_


@HEADS.register()
class ppTSMHead(TSNHead):
    """ ppTSM Head
    Args:
        num_classes (int): The number of classes to be classified.
        in_channels (int): The number of channles in input feature.
        loss_cfg (dict): Config for building config. Default: dict(name='CrossEntropyLoss').
        drop_ratio(float): drop ratio. Default: 0.8.
        std(float): Std(Scale) value in normal initilizar. Default: 0.001.
        kwargs (dict, optional): Any keyword argument to initialize.
    """
    def __init__(
            self,
            num_classes,
            in_channels,  # NOTE: 2048 for >= R50, 512 for <= R34
            drop_ratio=0.8,
            std=0.01,
            data_format="NCHW",
            num_seg=8,
            **kwargs):

        super().__init__(num_classes,
                         in_channels,
                         drop_ratio=drop_ratio,
                         std=std,
                         data_format=data_format,
                         **kwargs)

        self.fc = Linear(self.in_channels,
                         self.num_classes,
                         weight_attr=ParamAttr(learning_rate=5.0,
                                               regularizer=L2Decay(1e-4)),
                         bias_attr=ParamAttr(learning_rate=10.0,
                                             regularizer=L2Decay(0.0)))
        self.stdv = std
        self.num_seg = num_seg

    def init_weights(self):
        """Initiate the FC layer parameters"""
        weight_init_(self.fc, 'Normal', 'fc_0.w_0', 'fc_0.b_0', std=self.stdv)

    def forward(self, x, num_seg=None):
        """Define how the head is going to run.
        Args:
            x (paddle.Tensor): The input data.
            num_segs (int): Number of segments.
        Returns:
            score: (paddle.Tensor) The classification scores for input samples.
        """

        #XXX: check dropout location!
        # [N * num_segs, in_channels, 7, 7]
        x = self.avgpool2d(x)
        # [N * num_segs, in_channels, 1, 1]
        if self.dropout is not None:
            x = self.dropout(x)
            # [N * num_seg, in_channels, 1, 1]
        num_seg = num_seg if num_seg is not None else self.num_seg
        x = paddle.reshape(x, [-1, num_seg, x.shape[1]])
        # [N, num_seg, in_channels]
        x = paddle.mean(x, axis=1)
        # [N, in_channels]
        x = paddle.reshape(x, shape=[-1, self.in_channels])
        # [N, in_channels]
        score = self.fc(x)
        # [N, num_class]
        #x = F.softmax(x)  #NOTE remove
        return score
