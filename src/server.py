"""Standalone OH2P MCP example. Requires an already flashed, SSH-accessible speaker."""
import fcntl
import json
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
import uvicorn

from auth import BearerGate
from speaker_voice import ROOT, settings, synthesize, play
from music_control import register


def build():
    cfg = settings()
    token = cfg.get('mcp_token', '')
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError('generate a private MCP token of at least 32 ASCII characters')
    mcp = FastMCP('oh2p-speaker', stateless_http=True, json_response=True,
                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    register(mcp)

    @mcp.tool()
    def speaker_say(text: str) -> str:
        """Speak at most 300 characters on the configured OH2P using the owner's TTS voice.

        Text goes to the configured ElevenLabs voice service; playback is on the
        physical speaker. Native music pauses first. An error can mean playback
        outcome is unknown: do not automatically replay it.
        """
        if not text.strip() or len(text) > 300:
            return json.dumps({'ok': False, 'error': 'text_length_1_to_300'})
        with (ROOT / 'playback.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return json.dumps({'ok': False, 'error': 'speaker_busy_no_retry'})
            try:
                seconds = play(synthesize(text))
                return json.dumps({'ok': True, 'played_seconds': round(seconds, 2)})
            except Exception:
                return json.dumps({'ok': False, 'error': 'speech_failed_or_outcome_unknown',
                                   'automatic_retry': False})

    return mcp, BearerGate(mcp.streamable_http_app(), token)


if __name__ == '__main__':
    os.umask(0o077)
    _, app = build()
    uvicorn.run(app, host='127.0.0.1', port=8770, access_log=False)
