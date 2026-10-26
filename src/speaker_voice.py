"""Laptop-side OH2P voice transport. Known SSH host; official TTS; no credential logs."""
import argparse
import hashlib
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(os.environ.get('OH2P_STATE_DIR', str(Path.home()/'.config/oh2p-mcp'))).expanduser()
SSH=['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=5',
     '-o','StrictHostKeyChecking=yes','oh2p']

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def settings():
    p=ROOT/'voice-secrets.json'
    assert not p.is_symlink() and p.stat().st_uid==os.getuid() and p.stat().st_mode & 0o077==0,'Insecure configuration permissions'
    return json.loads(p.read_text())

def synthesize(text):
    assert 0<len(text)<=300,'Text length limit'
    cfg=settings()['tts']
    assert cfg['baseUrl']=='https://api.elevenlabs.io'
    voice=urllib.parse.quote(cfg['voiceId'],safe='')
    body={'text':text,'model_id':cfg['model'],'voice_settings':{
        'stability':cfg.get('stability',.5),'similarity_boost':cfg.get('similarityBoost',.75)}}
    req=urllib.request.Request(cfg['baseUrl']+'/v1/text-to-speech/'+voice+'?output_format=mp3_44100_128',
        data=json.dumps(body,ensure_ascii=False).encode(),headers={
            'Content-Type':'application/json','Accept':'audio/mpeg','xi-api-key':cfg['apiKey']})
    opener=urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req,timeout=45) as res:
            data=res.read(8*1024*1024+1)
            assert res.status==200 and 100<len(data)<=8*1024*1024,'Invalid audio response'
    except urllib.error.HTTPError as e:
        try:
            detail=json.loads(e.read(4096)).get('detail',{})
            code=detail.get('status','') if isinstance(detail,dict) else ''
        except Exception: code=''
        raise RuntimeError('TTS HTTP '+str(e.code)+' '+str(code)) from None
    except urllib.error.URLError as e:
        raise RuntimeError('TTS network connection failed: '+type(e.reason).__name__) from None
    return data

def play(data):
    proc=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-i','pipe:0',
        '-filter:a','volume=0.5','-ar','48000','-ac','2','-f','s16le','pipe:1'],input=data,capture_output=True,timeout=20)
    if proc.returncode: raise RuntimeError('Audio decode failed')
    if not 0<len(proc.stdout)<=48000*4*120: raise RuntimeError('Audio length out of bounds')
    from music_control import Music
    Music().control('pause')  # Caller owns playback.lock; native music yields to speech.
    played=subprocess.run(SSH+['aplay -q -D Playback -t raw -f S16_LE -r 48000 -c 2'],
        input=proc.stdout,capture_output=True,timeout=130)
    if played.returncode: raise RuntimeError('Speaker playback failed: '+str(played.returncode))
    return len(proc.stdout)/192000
