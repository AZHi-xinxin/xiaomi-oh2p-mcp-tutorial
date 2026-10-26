"""Real DSP tests with generated signals only; no room recordings."""
import unittest
import numpy as np
from speaker_aec import Echo, SpeechCapture, RATE, FRAME


def rms(x):
    return float(np.sqrt(np.mean(np.asarray(x, dtype=float) ** 2)))


class AcousticTests(unittest.TestCase):
    def test_silence_and_reference_not_mixed_into_mic(self):
        capture = SpeechCapture()
        try:
            raw = np.zeros((800, 4), dtype='<i4')
            self.assertEqual(capture.process(raw.tobytes()), bytes(1600))
            raw[:, 3] = np.random.default_rng(8).integers(-1000000000, 1000000000, 800)
            for _ in range(30):
                self.assertEqual(capture.process(raw.tobytes()), bytes(1600))
        finally:
            capture.close()

    def test_invalid_shape_and_close(self):
        capture = SpeechCapture()
        for raw in [b'', bytes(16), bytes(2559)]:
            with self.assertRaises(ValueError): capture.process(raw)
        capture.close(); capture.close()
        with self.assertRaises(RuntimeError): capture.process(bytes(2560))

    def test_echo_reduction_and_double_talk_preserves_independent_voice(self):
        rng = np.random.default_rng(42)
        n = RATE * 12
        reference = np.convolve(rng.normal(0, 5500, n), [.25, .5, .25], 'same')
        echo = .65*np.roll(reference, 40) + .24*np.roll(reference, 180) - .12*np.roll(reference, 580)
        voice = np.convolve(rng.normal(0, 1500, n), [.2, .6, .2], 'same')
        voice[:RATE*6] = 0
        mic = np.rint(echo + voice).astype(np.int16)
        reference = np.rint(reference).astype(np.int16)
        processor = Echo()
        try:
            cleaned = np.concatenate([processor.process(mic[i:i+FRAME], reference[i:i+FRAME])
                                      for i in range(0,n,FRAME)]).astype(float)
        finally: processor.close()
        quiet = slice(RATE*3,RATE*5)
        suppression = 20*np.log10(rms(echo[quiet])/max(rms(cleaned[quiet]),1))
        self.assertGreater(suppression, 18)
        talking = slice(RATE*7,RATE*11)
        correlation = np.corrcoef(cleaned[talking], voice[talking])[0,1]
        level_ratio = rms(cleaned[talking])/rms(voice[talking])
        print({'synthetic_echo_suppression_db':round(float(suppression),1),
               'double_talk_voice_correlation':round(float(correlation),3),
               'double_talk_level_ratio':round(level_ratio,3)})
        self.assertGreater(correlation, .85)
        self.assertGreater(level_ratio,.75)
        self.assertLess(level_ratio,1.3)

    def test_clean_speech_and_limiter(self):
        processor = SpeechCapture()
        try:
            t = np.arange(RATE)/RATE
            speech = (3000000*np.sin(2*np.pi*300*t)).astype(np.int32)
            raw = np.zeros((RATE,4),dtype='<i4'); raw[:,0] = speech
            cleaned = np.concatenate([np.frombuffer(processor.process(raw[i:i+800].tobytes()),dtype='<i2')
                                      for i in range(0,RATE,800)])
            self.assertGreater(rms(cleaned[3200:]),5000)
            self.assertLess(abs(cleaned.astype(float)).max(),30001)
            raw[:,0] = speech*30
            for i in range(0,RATE,800):
                cleaned = np.frombuffer(processor.process(raw[i:i+800].tobytes()),dtype='<i2')
                self.assertLessEqual(abs(cleaned.astype(float)).max(),30000)
            self.assertEqual(processor.input_clipped_samples,0)
        finally: processor.close()


if __name__ == '__main__': unittest.main()
