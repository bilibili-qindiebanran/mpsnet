import math
import keras
from keras import ops
from keras.layers import Layer
from keras.initializers import Constant


def _l2_normalize(x, axis):
    # Keras 3 没有 ops.l2_normalize，这里显式实现
    return x / ops.sqrt(ops.maximum(ops.sum(ops.square(x), axis=axis, keepdims=True),
                                    keras.backend.epsilon()))


class AdaCos(Layer):
    """AdaCos: 自适应缩放余弦损失层（Keras 3 实现）。

    训练时根据非目标类的指数均值 B_avg 与目标类角度的中位数 theta_med
    动态更新缩放因子 s；推理时只使用当前的 s 做缩放。
    """

    def __init__(self,
                 n_classes,
                 is_dynamic=True,
                 initializer=None,
                 regularizer=None,
                 **kwargs):

        super(AdaCos, self).__init__(**kwargs)
        self.n_classes = n_classes
        self.is_dynamic = is_dynamic
        self.initializer = initializer
        self.regularizer = regularizer
        self.init_s = math.sqrt(2) * math.log(n_classes - 1)

    def get_config(self):

        config = super().get_config()
        config.update({
            'n_classes': self.n_classes,
            'is_dynamic': self.is_dynamic,
            'regularizer': self.regularizer
        })
        return config

    def build(self, input_shape):
        # input_shape 为 (特征维度,), (标签维度,) 组成的序列
        super(AdaCos, self).build(input_shape[0])

        embedding_dim = int(input_shape[0][-1])
        self.W = self.add_weight(name='W',
                                 shape=(embedding_dim, self.n_classes),
                                 initializer=self.initializer,
                                 trainable=True,
                                 regularizer=self.regularizer)
        if self.is_dynamic:
            self.s = self.add_weight(name='s',
                                     shape=(),
                                     initializer=Constant(self.init_s),
                                     trainable=False,
                                     aggregation='mean')

    def call(self, inputs, training=None):
        x, y = inputs
        is_symbolic = isinstance(x, keras.KerasTensor)

        # 标签统一成 int32 的一维张量
        y = ops.cast(ops.reshape(y, [-1]), 'int32')

        # 归一化特征与权重，计算余弦相似度
        x = _l2_normalize(x, axis=1)
        w = _l2_normalize(self.W, axis=0)
        logits = ops.matmul(x, w)

        training = bool(training) if training is not None else False

        # Fixed AdaCos：s 固定为初始值
        if not self.is_dynamic:
            return ops.softmax(self.init_s * logits)

        # 推理阶段没有标签可用来更新 s；符号构图阶段没有真实数值，同样直接使用当前 s
        if not training or is_symbolic:
            return ops.softmax(self.s * logits)

        # 动态更新 s
        eps = keras.backend.epsilon()
        theta = ops.arccos(ops.clip(logits, -1.0 + eps, 1.0 - eps))
        one_hot = ops.one_hot(y, num_classes=self.n_classes)
        b_avg = ops.where(one_hot < 1.0,
                          ops.exp(self.s * logits),
                          ops.zeros_like(logits))
        b_avg = ops.mean(ops.sum(b_avg, axis=1))

        theta_class = ops.take(theta, y, axis=1)
        theta_med = ops.median(theta_class)

        self.s.assign(ops.log(b_avg) / ops.cos(ops.minimum(math.pi / 4, theta_med)))

        # 缩放后的 logits
        return ops.softmax(self.s * logits)

    def compute_output_shape(self, input_shape):
        # Keras 3 对多输入层传入的是「各输入的 shape」组成的序列，取特征输入那一个
        if isinstance(input_shape, (list, tuple)) and isinstance(input_shape[0], (list, tuple)):
            input_shape = input_shape[0]
        return (input_shape[0], self.n_classes)
