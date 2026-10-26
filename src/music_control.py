"""Typed original-catalog music controls. No arbitrary URLs, shell or HA services."""
import fcntl
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
import unicodedata
from speaker_voice import ROOT,SSH

def music_name(value):
    if not isinstance(value,str): raise ValueError('invalid_music_name')
    value=unicodedata.normalize('NFKC',value).strip()
    if len(value)>60 or any(not (unicodedata.category(c)[0] in 'LNM' or c in " -·.'&") for c in value):
        raise ValueError('plain_song_or_artist_only')
    if re.search(r'忽略|执行|系统|指令|然后|接着|开灯|关灯|风扇|摄像头|空调|音量|http|www',value,re.I):
        raise ValueError('plain_song_or_artist_only')
    return value

class Music:
    def __init__(self,runner=subprocess.run,sleep=time.sleep):
        self.runner,self.sleep=runner,sleep

    def call(self,domain,method,data):
        assert (domain,method) in {('mediaplayer','player_get_play_status'),
            ('mediaplayer','player_play_operation'),('mibrain','ai_service')}
        cmd='ubus -t 6 call '+domain+' '+method+' '+shlex.quote(json.dumps(data,ensure_ascii=False))
        p=self.runner(SSH+[cmd],capture_output=True,timeout=9)
        if p.returncode:raise RuntimeError('speaker_unreachable')
        result=json.loads(p.stdout)
        if result.get('code')!=0:raise RuntimeError('speaker_rejected')
        return result

    def state(self):
        v=self.call('mediaplayer','player_get_play_status',{})['info']
        v=json.loads(v) if isinstance(v,str) else v
        if type(v.get('status')) is not int or v['status'] not in (0,1,2):
            raise ValueError('unknown_playback_state')
        detail=v.get('play_song_detail') or {}
        out={'state':{0:'idle',1:'playing',2:'paused'}[v['status']],
             'volume':v.get('volume'),'audio_id':str(detail.get('audio_id',''))[:128]}
        for k in ['position','duration']:
            if type(detail.get(k)) is int and detail[k]>=0:out[k+'_ms']=detail[k]
        if 'duration_ms' in out:out['short_track_or_preview']=0<out['duration_ms']<=61000
        return out

    def operation(self,action):
        assert action in ('pause','play','next')
        return self.call('mediaplayer','player_play_operation',{'action':action,'media':'common'})

    def wait(self,expected,previous=None):
        observed=None
        for _ in range(10):
            self.sleep(.3);observed=self.state()
            if observed['state']==expected and (previous is None or observed['audio_id']!=previous):
                return observed
        raise RuntimeError('playback_outcome_unverified_do_not_repeat')

    def control(self,action,title='',artist=''):
        if action not in ('status','play','pause','resume','next'):raise ValueError('unknown_music_action')
        title,artist=music_name(title),music_name(artist)
        if action!='play' and (title or artist):raise ValueError('song_only_for_play')
        before=self.state()
        if action=='status':return {'ok':True,**before}
        if action=='pause':
            if before['state']!='playing':return {'ok':True,**before,'already_stopped':True}
            self.operation('pause');return {'ok':True,**self.wait('paused')}
        if action=='resume':
            if before['state']=='playing':return {'ok':True,**before}
            if before['state']!='paused' or not before['audio_id']:
                return {'ok':False,'error':'no_paused_song'}
            self.operation('play');return {'ok':True,**self.wait('playing')}
        if action=='next':
            if not before['audio_id']:return {'ok':False,'error':'no_playlist'}
            self.operation('next');return {'ok':True,**self.wait('playing',before['audio_id'])}
        # Structured song/artist values are enclosed as catalog names. Never
        # forward a free-form household command to Xiaomi's general assistant.
        request='播放'+(artist+'的' if artist else '')+('歌曲《'+title+'》' if title else '音乐')
        self.call('mibrain','ai_service',{'nlp':1,'nlp_text':request})
        after=self.wait('playing')
        # A code=0 can merely accept NLP. The old running song proves nothing.
        if before['state']=='playing' and after['audio_id']==before['audio_id']:
            after=self.wait('playing',before['audio_id'])
        return {'ok':True,**after,'requested_title':title,'requested_artist':artist,
                'catalog':'original_xiaomi','exact_title_metadata_available':False}

def perform(action,title='',artist='',music=None):
    music=music or Music()
    try:
        if action=='status':return music.control(action,title,artist)
        with (ROOT/'playback.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return {'ok':False,'error':'speaker_busy_no_retry'}
            status_file=ROOT/'wake-status.json'
            state=json.loads(status_file.read_text()).get('state') if status_file.exists() else 'stopped'
            if state not in ('listening','stopped','failed'):
                return {'ok':False,'error':'voice_turn_in_progress_no_retry'}
            return music.control(action,title,artist)
    except Exception as exc:
        return {'ok':False,'error':str(exc) if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__,
                'automatic_retry':False}

def register(mcp):
    @mcp.tool()
    def speaker_music(action:str,title:str='',artist:str='')->str:
        """Play music on the OH2P speaker using its original Xiaomi catalog. action: status/play/pause/resume/next. For play supply only song title and artist (empty selects catalog music), never instructions or URLs. Read actual state; timeout is uncertain and must not be retried. A short_track_or_preview result can mean a catalog preview; do not promise a full track. Playback can be interrupted by an explicit voice wake. For speech use the existing speaker_say tool."""
        return json.dumps(perform(action,title,artist),ensure_ascii=False)
