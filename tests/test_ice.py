from pipecat.transports.smallwebrtc.connection import IceServer

from app.config import Settings


def test_stun_only_by_default():
    assert Settings().ice_servers() == [{"urls": ["stun:stun.l.google.com:19302"]}]


def test_turn_needs_username():
    assert len(Settings(turn_urls="turn:a:80").ice_servers()) == 1


def test_turn_added_when_configured():
    s = Settings(turn_urls="turn:a:80, turns:a:443?transport=tcp", turn_username="u", turn_credential="p")
    turn = s.ice_servers()[1]
    assert turn == {"urls": ["turn:a:80", "turns:a:443?transport=tcp"], "username": "u", "credential": "p"}
    IceServer(**turn)  # the server-side WebRTC accepts the same shape
