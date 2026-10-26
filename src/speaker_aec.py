"""OH2P synchronous mic/reference echo cancellation, entirely in local RAM.

Capture is four interleaved S32_LE channels at 16 kHz. On the verified 1.62.2
device channels 0..2 are microphones; channel 3 is the playback reference.
Never downmix that reference into the human speech channel.
"""
import ctypes as C
import numpy as np

RATE = 16000
FRAME = 160


class Echo:
    def __init__(self):
        self.lib = C.CDLL('libspeexdsp.so.1')
        lib = self.lib
        lib.speex_echo_state_init.argtypes = [C.c_int, C.c_int]
        lib.speex_echo_state_init.restype = C.c_void_p
        lib.speex_echo_state_destroy.argtypes = [C.c_void_p]
        lib.speex_echo_state_destroy.restype = None
        lib.speex_echo_ctl.argtypes = [C.c_void_p, C.c_int, C.c_void_p]
        lib.speex_echo_ctl.restype = C.c_int
        lib.speex_echo_cancellation.argtypes = [C.c_void_p] * 4
        lib.speex_echo_cancellation.restype = None
        self.state = lib.speex_echo_state_init(FRAME, 3200)
        if not self.state:
            raise RuntimeError('aec_init_failed')
        rate = C.c_int(RATE)
        if lib.speex_echo_ctl(self.state, 24, C.byref(rate)) != 0:
            self.close()
            raise RuntimeError('aec_sample_rate_failed')

    def process(self, mic, reference):
        mic = np.ascontiguousarray(mic, dtype=np.int16)
        reference = np.ascontiguousarray(reference, dtype=np.int16)
        if mic.shape != (FRAME,) or reference.shape != (FRAME,):
            raise ValueError('aec_frame_size')
        if not self.state:
            raise RuntimeError('aec_closed')
        output = np.empty(FRAME, dtype=np.int16)
        self.lib.speex_echo_cancellation(
            self.state, mic.ctypes.data, reference.ctypes.data, output.ctypes.data)
        return output

    def close(self):
        if self.state:
            self.lib.speex_echo_state_destroy(self.state)
            self.state = None


class SpeechCapture:
    def __init__(self):
        self.echo = Echo()
        self.gain = 16.0
        self.frames = 0
        self.input_clipped_samples = 0

    def process(self, raw):
        if not raw or len(raw) % (FRAME * 4 * 4):
            raise ValueError('aec_interleaved_frame_size')
        channels = np.frombuffer(raw, dtype='<i4').reshape(-1, 4)
        # The former >>8 conversion clipped ~42% of music mic samples. Leave
        # headroom before cancellation; amplify the cleaned signal afterwards.
        source = channels[:, 0].astype(np.int64) >> 12
        self.input_clipped_samples += int(np.count_nonzero((source > 32767) | (source < -32768)))
        mic = np.clip(source, -32768, 32767).astype(np.int16)
        # Full-range S32 reference cannot clip, even if music volume is raised.
        reference = (channels[:, 3] >> 16).astype(np.int16)
        cleaned = np.concatenate([
            self.echo.process(mic[i:i + FRAME], reference[i:i + FRAME])
            for i in range(0, len(mic), FRAME)
        ]).astype(np.float32)
        peak = max(float(np.max(np.abs(cleaned))), 1.0)
        target = min(16.0, 30000.0 / peak)
        # Fast attenuation, gradual recovery. Never amplify beyond the original
        # quiet-room gain or let a close voice overload the keyword detector.
        recovery = 1.0 - np.exp(-len(mic) / RATE)
        self.gain = target if target < self.gain else self.gain + (target - self.gain) * recovery
        self.frames += len(mic) // FRAME
        return np.rint(cleaned * self.gain).astype('<i2').tobytes()

    def close(self):
        self.echo.close()
