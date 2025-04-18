# BSD 3- Clause License Copyright (c) 2023, Tecorigin Co., Ltd. All rights
# reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software
# without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY,OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)  ARISING IN ANY
# WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY
# OF SUCH DAMAGE.
import colorednoise as cn
import random
import numpy as np
from sklearn.metrics import mean_squared_error
import paddle
import librosa
import pyworld
import soundfile

from utils_1 import params2sos
from scipy.signal import sosfilt

Qmin, Qmax = 2, 5


def add_noise(wav, noise_ratio=0.7, brown_noise_ratio=1.):
    beta = random.random() * 2  # the exponent
    y = cn.powerlaw_psd_gaussian(beta, wav.shape[0])
    m = np.sqrt(mean_squared_error(wav, np.zeros_like(y)))

    if beta >= 0 and beta <= 1.5:
        wav += (noise_ratio * random.random()) * m * y
    else:
        wav += (brown_noise_ratio * random.random()) * m * y
    return wav


def add_noise_slice(wav, sr, duration, add_factor=0.50, noise_ratio=0.7, brown_noise_ratio=1.):
    slice_length = int(duration * sr)
    n_frames = int(wav.shape[-1] // slice_length)
    slice_length_noise = int(slice_length * add_factor)
    for n in range(n_frames):
        left, right = int(n * slice_length), int((n + 1) * slice_length)
        offset = random.randint(left, right - slice_length_noise)
        if wav[offset:offset + slice_length_noise].shape[0] != 0:
            wav[offset:offset + slice_length_noise] = add_noise(wav[offset:offset + slice_length_noise],
                                                                noise_ratio=noise_ratio,
                                                                brown_noise_ratio=brown_noise_ratio)
    return wav


def add_mel_mask(mel, iszeropad=False, esp=1e-5):
    if iszeropad:
        return paddle.ones_like(mel) * esp
    else:
        return (random.random() * 0.9 + 0.1) * paddle.randn(mel.shape,dtype=mel.dtype)


def add_mel_mask_slice(mel, sr, duration, hop_size=512, add_factor=0.3, vertical_offset=True, vertical_factor=0.05,
                       iszeropad=True, islog=True, block_num=5, esp=1e-5):
    if islog:
        mel = paddle.exp(mel)
    slice_length = int(duration * sr) // hop_size
    n_frames = int(mel.shape[-1] // slice_length)
    n_mels = mel.shape[-2]
    for n in range(n_frames):
        line_num = n_mels // block_num
        for i in range(block_num):
            now_vertical_factor = vertical_factor + random.random() * 0.1
            now_add_factor = add_factor + random.random() * 0.1
            slice_length_noise = int(slice_length * now_add_factor)
            if vertical_offset:
                v_offset = int(random.uniform(line_num * i, line_num * (i + 1) - now_vertical_factor))
                n_v_down = v_offset
                n_v_up = int(v_offset + now_vertical_factor * n_mels)
            else:
                n_v_down = 0
                n_v_up = n_mels
            left, right = int(n * slice_length), int((n + 1) * slice_length)
            offset = int(random.uniform(left, right - slice_length_noise))
            if mel[n_v_down:n_v_up, offset:offset + slice_length_noise].shape[-1] != 0:
                mel[n_v_down:n_v_up, offset:offset + slice_length_noise] = add_mel_mask(
                    mel[n_v_down:n_v_up, offset:offset + slice_length_noise], iszeropad, esp)
    if islog:
        mel = paddle.log(paddle.clip(mel, min=esp))
    return mel


def random_eq(wav, sr):
    rng = np.random.default_rng()
    z = rng.uniform(0, 1, size=(10,))
    Q = Qmin * (Qmax / Qmin) ** z
    G = rng.uniform(-12, 12, size=(10,))
    Fc = np.exp(np.linspace(np.log(60), np.log(7600), 10))
    sos = params2sos(G, Fc, Q, sr)
    wav = sosfilt(sos, wav)
    peak = np.abs(wav).max()
    if peak > 0.98:
        wav = 0.98 * wav / peak
    return wav


def worldSynthesize(wav, target_sr=44100, hop_length=512, fft_size=2048, f0_in=None):
    f0, t = pyworld.dio(wav.astype(np.double), fs=target_sr, frame_period=1000 * hop_length / target_sr)
    f0 = pyworld.stonemask(wav.astype(np.double), f0, t, target_sr)
    if f0 is not None:
        f0 = f0_in.astype(np.double)
    ap = pyworld.d4c(wav.astype(np.double), f0, t, target_sr, fft_size=fft_size)
    sp = pyworld.cheaptrick(wav.astype(np.double), f0, t, target_sr, fft_size=fft_size)
    synthesized = pyworld.synthesize(f0, sp, ap, target_sr, frame_period=1000 * hop_length / target_sr)

    peak = np.abs(synthesized).max()
    synthesized = 0.98 * synthesized / peak

    return synthesized, f0


#  soundfile.write(f'world_{wav_name}.wav', synthesized, target_sr)
#  np.save(f"f0_{wav_name}.npy",f0)


def add_noise_snb(wav, snb, beta):
    # 将信噪比转换为信号与噪声的能量比例
    snb = 10 ** (snb / 10)
    noise = cn.powerlaw_psd_gaussian(beta, wav.shape[0])
    rms_signal = np.sqrt(np.mean(wav ** 2))
    rms_noise = np.sqrt(np.mean(noise ** 2))
    wav = wav + noise * (rms_signal / rms_noise) / snb
    return wav


def add_noise_slice_snb(wav, sr, duration, add_factor=0.50, snb=0.7, beta=1.0):
    slice_length = int(duration * sr)
    n_frames = int(wav.shape[-1] // slice_length)
    slice_length_noise = int(slice_length * add_factor)
    for n in range(n_frames):
        left, right = int(n * slice_length), int((n + 1) * slice_length)
        offset = random.randint(left, right - slice_length_noise)
        if wav[offset:offset + slice_length_noise].shape[0] != 0:
            wav[offset:offset + slice_length_noise] = add_noise_snb(wav[offset:offset + slice_length_noise], snb, beta)
    return wav


def add_pub_noise_snb(wav, snb):
    # 将信噪比转换为信号与噪声的能量比例
    import os
    noise_path = r'path/to/noise/data/dir'
    noise_list = os.listdir(noise_path)
    noise_path = os.path.join(noise_path, random.choice(noise_list))
    snb = 10 ** (snb / 10)
    noise, sr = librosa.load(noise_path, sr=16000)
    if len(wav) > len(noise):
        noise = np.tile(noise, len(wav) // len(noise) + 1)
    if len(wav) < len(noise):
        noise = noise[:len(wav)]
    rms_signal = np.sqrt(np.mean(wav ** 2))
    rms_noise = np.sqrt(np.mean(noise ** 2))
    wav = wav + noise * (rms_signal / rms_noise) / snb
    return wav


def add_pub_noise_snb2(wav, snb):
    # 将信噪比转换为信号与噪声的能量比例
    import os
    noise_path = r'path/to/noise/data/dir'
    noise_list = os.listdir(noise_path)
    noise_path = os.path.join(noise_path, random.choice(noise_list))
    snb = 10 ** (snb / 10)
    noise, sr = librosa.load(noise_path, sr=16000)
    if len(wav) > len(noise):
        noise = np.tile(noise, len(wav) // len(noise) + 1)
    if len(wav) < len(noise):
        offset = int(random.choice(range(len(noise) - len(wav))))
        noise = noise[offset:offset + len(wav)]
    rms_signal = np.sqrt(np.mean(wav ** 2))
    rms_noise = np.sqrt(np.mean(noise ** 2))
    wav = wav + noise * (rms_signal / rms_noise) / snb
    return wav
