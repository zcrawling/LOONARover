import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch
import gcs_pc


def test_duplicate_auto_and_stop_marker(tmp_path):
    async def scenario():
        process = Mock(returncode=None)
        docker = Mock(returncode=0, wait=AsyncMock(return_value=0))
        with patch.object(gcs_pc.shutil, 'which', return_value='/bin/gnome-terminal'), \
             patch.object(gcs_pc.asyncio, 'create_subprocess_exec', AsyncMock(side_effect=[process,docker])) as spawn:
            manager = gcs_pc.BrainTerminal(Mock(), tmp_path)
            await manager.start()
            session = manager.session
            await manager.start()
            assert spawn.await_count == 1
            assert (session/'owner.json').exists()
            (session/'exited').touch()
            await manager.stop()
            assert (session/'stop').exists()
            assert manager.session is None
            assert spawn.call_args.args[:3] == ('docker','rm','-f')
            await manager.stop()
            assert spawn.await_count == 2
    asyncio.run(scenario())


def test_stop_before_terminal_launch_never_starts_brain(tmp_path):
    (tmp_path/'owner.json').write_text(json.dumps({'pid':123,'container':'test-owned'}))
    (tmp_path/'stop').touch()
    with patch.object(gcs_pc.signal,'signal'), patch.object(gcs_pc.subprocess,'Popen') as spawn, \
         patch.object(gcs_pc.subprocess,'run'):
        gcs_pc.terminal(tmp_path)
    spawn.assert_not_called()
    assert (tmp_path/'exited').exists()


def test_terminal_close_interrupts_and_removes_owned_container(tmp_path):
    (tmp_path/'owner.json').write_text(json.dumps({'pid':123,'container':'test-owned'}))
    child=Mock(pid=456)
    child.poll.return_value=None
    def stop_on_sleep(_): (tmp_path/'stop').touch()
    with patch.object(gcs_pc.signal,'signal'), patch.object(gcs_pc.os,'kill'), \
         patch.object(gcs_pc.os,'killpg') as kill, \
         patch.object(gcs_pc.time,'sleep',side_effect=stop_on_sleep), \
         patch.object(gcs_pc.subprocess,'Popen',return_value=child), \
         patch.object(gcs_pc.subprocess,'run') as run:
        gcs_pc.terminal(tmp_path)
    kill.assert_called_once_with(456,gcs_pc.signal.SIGINT)
    assert run.call_args.args[0]==['docker','rm','-f','test-owned']
    assert (tmp_path/'exited').exists()
