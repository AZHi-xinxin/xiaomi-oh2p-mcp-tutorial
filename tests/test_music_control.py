import json
import unittest
from unittest.mock import Mock
from music_control import Music,music_name

class MusicTests(unittest.TestCase):
    def test_names_cannot_be_commands_or_network_targets(self):
        self.assertEqual(music_name('我怀念的'),'我怀念的')
        self.assertEqual(music_name('孙燕姿'),'孙燕姿')
        for n in ['https://evil.invalid/a','我怀念的;关灯','然后开灯','好歌\n别的指令',{'title':'a'}]:
            with self.subTest(n=n),self.assertRaises(ValueError):music_name(n)

    def test_readback_is_minimal_and_does_not_expose_streams(self):
        m=Music();m.call=Mock(return_value={'info':json.dumps({'status':1,'volume':40,
            'play_song_detail':{'audio_id':'track','position':20,'duration':60000,'url':'SECRET'}})})
        s=m.state();self.assertTrue(s['short_track_or_preview']);self.assertNotIn('SECRET',json.dumps(s))

    def test_pause_resume_verified_and_idle_cannot_resume(self):
        m=Music(sleep=lambda _:None);m.state=Mock(side_effect=[{'state':'playing'}, {'state':'paused','audio_id':'a'}]);m.operation=Mock()
        self.assertTrue(m.control('pause')['ok']);m.operation.assert_called_once_with('pause')
        m.state=Mock(return_value={'state':'idle','audio_id':''});m.operation.reset_mock()
        self.assertFalse(m.control('resume')['ok']);m.operation.assert_not_called()

    def test_nlp_ack_is_not_playback_success_and_is_never_retried(self):
        m=Music(sleep=lambda _:None);m.state=Mock(return_value={'state':'idle','audio_id':''});m.call=Mock(return_value={'code':0})
        with self.assertRaises(RuntimeError):m.control('play','我怀念的','孙燕姿')
        m.call.assert_called_once()
        self.assertEqual(m.call.call_args.args,('mibrain','ai_service',{'nlp':1,'nlp_text':'播放孙燕姿的歌曲《我怀念的》'}))

    def test_existing_playing_song_does_not_prove_new_request_worked(self):
        m=Music(sleep=lambda _:None);m.state=Mock(return_value={'state':'playing','audio_id':'old'});m.call=Mock(return_value={'code':0})
        with self.assertRaises(RuntimeError):m.control('play','我怀念的')
        m.call.assert_called_once()

    def test_uncertain_write_is_not_replayed(self):
        m=Music();m.state=Mock(return_value={'state':'playing'});m.operation=Mock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):m.control('pause')
        m.operation.assert_called_once()
